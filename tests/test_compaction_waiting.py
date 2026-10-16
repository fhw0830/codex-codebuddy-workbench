import json
from pathlib import Path
import sys,tempfile,threading,time,unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from backend.service import Service
from backend.store import Store
from backend import history_compaction as hc
from backend.user_questions import QuestionBroker

class Compaction(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.data=Path(self.tmp.name)/'data'
        self.s=Service(ROOT,self.data,Path(self.tmp.name)/'archive',connect=False)
        self.s.store.set_setting('daily_autosave',False);self.id=self.s.store.conversations()[0]['id']
        self.messages=[]
        for i in range(10):
            job,_=self.s.store.create_job(self.id,'codex',1,'old-'+str(i),'要求'+str(i),{},True)
            self.s.store.update_job(job['id'],'completed')
            mid=self.s.store.message(self.id,'assistant','codex',('证据'+str(i))*1100,meta={'job_id':job['id']})
            self.messages.append(mid)
        self.job,_=self.s.store.create_job(self.id,'codex',1,'current','CURRENT_TASK_MUST_REMAIN',{},True)
        self.s.store.update_job(self.job['id'],'running')
    def tearDown(self):self.s.close();self.s.store.db.close();self.tmp.cleanup()
    def test_ai_summary_replaces_only_old_terminal_jobs_and_can_recover_exact_originals(self):
        prompts=[]
        class Agent:
            def __init__(self,*args):pass
            def run(self,prompt,*args,**kw):
                prompts.append(prompt);return '已确认：模式2绕到104站点后的1米。仅修改原分支，尚未实际验收。用户要求保留反复绕障及等待10秒规则，不修改无关逻辑。未完成事项：核查日志并取得用户回答。',{'tool_calls':0}
        future,_=self.s.store.create_job(self.id,'codex',1,'future','FUTURE_TASK_MUST_REMAIN',{},True)
        original=self.s.store.conversation(self.id);old_summary='已确认的早期要求'
        with patch('backend.service.Codex',Agent):self.s.compact_history(self.job,threading.Event())
        c=self.s.store.conversation(self.id);self.assertEqual(c['compression']['state'],'completed')
        archived=self.s.compaction_archive(c['compactions'][0]['id']);ids={m['id'] for m in archived['messages']}
        self.assertTrue(ids);self.assertEqual(archived['messages'],[m for m in original['messages'] if m['id'] in ids])
        self.assertTrue(all(m['id'] not in ids for m in c['messages']))
        self.assertTrue(any(m['content']=='CURRENT_TASK_MUST_REMAIN' for m in c['messages']))
        self.assertTrue(any(m['content']=='FUTURE_TASK_MUST_REMAIN' for m in c['messages']))
        prompt=self.s.prompt(self.s.job_conversation(self.job),'codebuddy',1)
        self.assertIn('模式2绕到104站点后的1米',prompt);self.assertNotIn('FUTURE_TASK_MUST_REMAIN',prompt)
        self.assertTrue(all('CURRENT_TASK_MUST_REMAIN' not in p and 'FUTURE_TASK_MUST_REMAIN' not in p for p in prompts))
        self.assertTrue(Path(self.s.store.one('SELECT archive_path FROM compactions')['archive_path']).is_file())
    def test_failed_or_cancelled_summary_never_removes_raw_messages(self):
        before=self.s.store.conversation(self.id)['messages']
        class Agent:
            def __init__(self,*args):pass
            def run(self,*args,**kwargs):raise TimeoutError('fixture summary timeout')
        with patch('backend.service.Codex',Agent):self.s.compact_history(self.job,threading.Event())
        self.assertEqual(before,self.s.store.conversation(self.id)['messages'])
        self.assertEqual(self.s.store.conversation(self.id)['compression']['state'],'failed')
    def test_repeated_compaction_passes_previous_summary_to_next_ai_call(self):
        results=[]
        class Agent:
            def __init__(self,*args):pass
            def run(self,prompt,*args,**kw):results.append(prompt);return '保留早期需求：'+('站点持续障碍等待10秒使用模式2去后1米，保持人工取消状态。'*4),{}
        with patch('backend.service.Codex',Agent):self.s.compact_history(self.job,threading.Event())
        summary=self.s.store.conversation(self.id)['compactions'][-1]['summary']
        for i in range(10):
            job,_=self.s.store.create_job(self.id,'codex',1,'more-'+str(i),'后续要求',{},True)
            self.s.store.update_job(job['id'],'completed');self.s.store.message(self.id,'assistant','codex','后续日志'*1300,meta={'job_id':job['id']})
        with patch('backend.service.Codex',Agent):self.s.compact_history(self.job,threading.Event())
        self.assertIn(summary,results[-1]);self.assertEqual(len(self.s.store.conversation(self.id)['compactions']),2)

class Waiting(unittest.TestCase):
    def test_prose_question_stops_peer_and_queue_until_answer_then_resumes_same_job(self):
        calls=[]
        class Agent:
            def __init__(self,*args):pass
            def models(self):return []
            def quota(self):return {}
            def run(self,prompt,*args,**kw):
                calls.append(prompt)
                if len(calls)==1:return '需要你提供控制板型号：它是什么型号？',{}
                return '已根据实际答案继续，原先完成的修改没有重复执行。',{}
        with tempfile.TemporaryDirectory() as folder,patch('backend.service.Codex',Agent),patch('backend.service.CodeBuddy',Agent):
            data=Path(folder)/'data';s=Service(ROOT,data,Path(folder)/'archive',connect=False)
            try:
                s.store.set_setting('daily_autosave',False);id=s.store.conversations()[0]['id']
                job=s.enqueue({'conversation_id':id,'content':'ORIGINAL_REPAIR','route':'both','client_key':'wait'})
                until=time.monotonic()+3
                while s.conversation(id)['job']['status']!='waiting_input' and time.monotonic()<until:time.sleep(.01)
                self.assertEqual(s.conversation(id)['job']['status'],'waiting_input')
                queued=s.enqueue({'conversation_id':id,'content':'NEXT_TASK','route':'codex','client_key':'next','send_mode':'queue'})
                time.sleep(.1);self.assertEqual(len(calls),1)
                request=s.conversation(id)['input_requests'][0]
                result=s.answer_question({'conversation_id':id,'question_id':request['id'],'answers':{'text':['控制板型号ABC']}})
                self.assertEqual(result['job_id'],job['id'])
                until=time.monotonic()+3
                while s.store.one('SELECT status FROM jobs WHERE id=?',(queued['id'],))['status']!='completed' and time.monotonic()<until:time.sleep(.01)
                self.assertEqual(len(calls),4)
                self.assertIn('控制板型号ABC',calls[1]);self.assertNotIn('NEXT_TASK',calls[1])
                self.assertEqual(s.store.one('SELECT status FROM jobs WHERE id=?',(job['id'],))['status'],'completed')
            finally:s.close();s.store.db.close()
    def test_restart_keeps_question_answerable_without_auto_replaying_task(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'db.sqlite';store=Store(path);id=store.create_conversation()['id']
            job,_=store.create_job(id,'codex',1,'q','任务',{},True);store.update_job(job['id'],'running')
            mid=store.message(id,'assistant','codex','需要你提供型号？',meta={'job_id':job['id'],'round':1})
            store.execute('INSERT INTO input_requests VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',('question',id,job['id'],mid,'codex','pending','[]','{}','codex',1,'now','now',None));store.db.close()
            reopened=Store(path)
            try:
                self.assertEqual(reopened.conversation(id)['job']['status'],'waiting_input')
                self.assertEqual(reopened.one('SELECT state FROM input_requests')['state'],'followup')
                self.assertTrue(reopened.conversations()[0]['waiting_input'])
            finally:reopened.db.close()
    def test_unexpected_native_exit_preserves_question_but_explicit_stop_cancels(self):
        changes=[];broker=QuestionBroker(changes.append);broker.open('one',[{'question':'请确认型号？'}]);broker.close(False,preserve=True)
        self.assertEqual(changes[-1]['state'],'followup')

if __name__=='__main__':unittest.main()
