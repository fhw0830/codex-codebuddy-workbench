import io
import json
import queue
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from backend.user_questions import QuestionBroker,normalize_questions,validate_answers,text_question
from backend.interaction import TurnUpdates
from backend.agents import Codex,CodeBuddy
from backend.execution_limits import ExecutionWindow
from backend.service import Service
from backend.collaboration import resolve_strategy

QUESTIONS=[{'id':'hardware','question':'控制板型号是什么？','options':[{'label':'A','description':'方案A'},{'label':'B','description':'方案B'}]}]

class Lines:
    def __init__(self):self.queue=queue.Queue()
    def __iter__(self):return self
    def __next__(self):
        event=self.queue.get(timeout=4)
        if event is None:raise StopIteration
        return json.dumps(event)+'\n'

class Process:
    pid=999999
    def __init__(self):self.stdin=io.StringIO();self.stdout=Lines();self.stderr=io.StringIO()
    def poll(self):return 0

class QuestionAgent:
    asked=threading.Event();question_id=None
    def __init__(self,*args):pass
    def models(self):return []
    def quota(self):return {}
    def run(self,prompt,model,emit,cancel,controls=None,**options):
        self.__class__.question_id=controls.questions.open('fixture-native',QUESTIONS)
        self.__class__.asked.set()
        until=time.monotonic()+3
        while time.monotonic()<until:
            for id,key,values in controls.questions.drain():
                controls.questions.ack(id);return '收到实际答案 '+values['hardware'][0],{'synthetic':True}
            if cancel.is_set():raise RuntimeError('fixture stopped')
            time.sleep(.01)
        raise RuntimeError('fixture answer missing')

class UserQuestions(unittest.TestCase):
    def test_no_default_answer_and_custom_response_is_allowed(self):
        rows=normalize_questions(QUESTIONS)
        with self.assertRaises(ValueError):validate_answers(rows,{})
        self.assertEqual(validate_answers(rows,{'hardware':'用户自己填写型号'})['hardware'],['用户自己填写型号'])
        with self.assertRaises(ValueError):normalize_questions([{'id':'secret','question':'密码','isSecret':True}])

    def test_broker_returns_only_human_submission_and_is_idempotent(self):
        events=[];broker=QuestionBroker(events.append);id=broker.open(42,QUESTIONS)
        self.assertEqual(list(broker.drain()),[]);self.assertEqual(broker.open(42,QUESTIONS),id)
        self.assertTrue(broker.submit(id,{'hardware':['B']}));self.assertFalse(broker.submit(id,{'hardware':['A']}))
        self.assertEqual(list(broker.drain()),[(id,42,{'hardware':['B']})]);broker.ack(id)
        self.assertEqual(events[-1]['state'],'answered')

    def test_ended_or_cancelled_prompt_has_truthful_state(self):
        events=[];broker=QuestionBroker(events.append);broker.open('key',QUESTIONS);broker.close(True)
        self.assertEqual(events[-1]['state'],'followup')
        broker=QuestionBroker(events.append);broker.open('key',QUESTIONS);broker.close(False)
        self.assertEqual(events[-1]['state'],'cancelled')

    def test_mcp_bridge_keeps_unicode_and_requires_scoped_token(self):
        events=[];broker=QuestionBroker(events.append)
        with tempfile.TemporaryDirectory() as folder:
            s=Service(ROOT,Path(folder)/'data',Path(folder)/'archive',connect=False)
            try:
                s.question_bridges['fixture-token']=broker
                with self.assertRaises(ValueError):s.question_bridge({'token':'wrong','action':'open','questions':QUESTIONS})
                q=s.question_bridge({'token':'fixture-token','action':'open','questions':QUESTIONS})
                self.assertTrue(broker.has_blocking)
                broker.submit(q['id'],{'hardware':['中文型号甲']})
                value=s.question_bridge({'token':'fixture-token','action':'poll','question_id':q['id']})
                self.assertEqual(value['answers']['hardware'],['中文型号甲'])
                self.assertFalse(broker.has_blocking)
            finally:s.close();s.store.db.close()

    def test_discussion_allows_only_question_discovery_and_its_tool_result(self):
        from backend.codebuddy_stream import StreamState
        from backend.agents import tool_record
        state=StreamState(lambda text:None,None,None,tool_record,False)
        state.tool({'id':'ask','type':'tool_use','name':'ToolSearch'},'running')
        state.tool({'id':'ask','type':'toolResult','output':'question schema'},'completed')
        with self.assertRaises(RuntimeError):state.tool({'id':'write','name':'Write','input':{}},'running')

    def test_wait_for_human_is_not_generation_timeout(self):
        at=[0];window=ExecutionWindow(180,False,lambda:at[0]);at[0]=10;window.pause();at[0]=10000
        self.assertFalse(window.expired());window.resume();at[0]=10169;self.assertFalse(window.expired())
        at[0]=10170;self.assertTrue(window.expired())

    def test_prose_question_is_offered_without_fabricated_choices(self):
        self.assertTrue(text_question('补水阀控制板是什么型号？它是否支持断线关阀？'))
        self.assertIsNone(text_question('已经查完，结果正常。'))

    def test_question_in_forwardable_template_or_quoted_record_does_not_pause_task(self):
        text='下面是转发模板：\n\n```text\nA. 车辆信息\n\nD. 主板是否支持超时关阀？请提供型号。\n```\n\n转发后将资料给我即可。'
        self.assertIsNone(text_question(text))
        self.assertIsNone(text_question('> 历史记录：需要你提供什么型号？\n\n这项已经解决。'))
        self.assertTrue(text_question('需要你确认现场条件：是否有人观察？\n\n```text\n模板问题\n```'))

    def test_native_codex_rpc_answer_uses_actual_question_ids(self):
        process=Process();events=queue.Queue();opened=threading.Event();callbacks=[];outcomes=[]
        broker=QuestionBroker(lambda request:(callbacks.append(request),opened.set()))
        controls=TurnUpdates(lambda *args:None);controls.questions=broker
        client=Codex('unused',ROOT)
        def exchange(process,events,method,params,id,cancel):
            return ({'thread':{'id':'native-thread'}} if method=='thread/start' else {'turn':{'id':'native-turn'}} if method=='turn/start' else {},[])
        with patch.object(client,'launch',return_value=(process,events,[])),patch.object(client,'exchange',side_effect=exchange),patch('backend.agents.stop_process'):
            thread=threading.Thread(target=lambda:outcomes.append(client.run('fixture','model',lambda text:None,threading.Event(),controls=controls)))
            thread.start();events.put({'id':77,'method':'item/tool/requestUserInput','params':{'questions':QUESTIONS,'isBlocking':True}})
            self.assertTrue(opened.wait(2));id=callbacks[0]['id'];broker.submit(id,{'hardware':['B']})
            until=time.monotonic()+2
            while '"id": 77' not in process.stdin.getvalue() and time.monotonic()<until:time.sleep(.01)
            packets=[json.loads(line) for line in process.stdin.getvalue().splitlines()]
            self.assertEqual(next(p for p in packets if p.get('id')==77)['result'],{'answers':{'hardware':{'answers':['B']}}})
            events.put({'method':'item/agentMessage/delta','params':{'itemId':'reply','delta':'已接到答案'}})
            events.put({'method':'turn/completed','params':{'turn':{'status':'completed'}}});thread.join(2)
            self.assertEqual(outcomes[0][0],'已接到答案')

    def test_native_codebuddy_permission_reply_only_answers_ask_user(self):
        process=Process();opened=threading.Event();callbacks=[];outcomes=[]
        broker=QuestionBroker(lambda request:(callbacks.append(request),opened.set()));controls=TurnUpdates(lambda *args:None);controls.questions=broker
        with tempfile.TemporaryDirectory() as folder,patch('backend.agents.spawn',return_value=process):
            thread=threading.Thread(target=lambda:outcomes.append(CodeBuddy({'node':'node','codebuddy':'unused'},Path(folder)).run('fixture','model',lambda text:None,threading.Event(),full_access=True,controls=controls)))
            thread.start();process.stdout.queue.put({'type':'control_request','request_id':'ask-1','request':{'subtype':'can_use_tool','tool_name':'AskUserQuestion','input':{'questions':QUESTIONS}}})
            self.assertTrue(opened.wait(2));broker.submit(callbacks[0]['id'],{'hardware':['用户型号']})
            until=time.monotonic()+2
            while 'control_response' not in process.stdin.getvalue() and time.monotonic()<until:time.sleep(.01)
            packets=[json.loads(line) for line in process.stdin.getvalue().splitlines()]
            response=next(p for p in packets if p.get('type')=='control_response')['response']
            self.assertEqual(response['request_id'],'ask-1');self.assertTrue(response['response']['allowed'])
            self.assertEqual(response['response']['updatedInput']['answers'],{'控制板型号是什么？':'用户型号'})
            process.stdout.queue.put({'type':'result','subtype':'success','result':'已接到答案','num_turns':1});process.stdout.queue.put(None);thread.join(2)
            self.assertEqual(outcomes[0][0],'已接到答案')

    def test_service_persists_answer_as_same_job_supplement_not_replacing_goal(self):
        with tempfile.TemporaryDirectory() as folder,patch('backend.service.Codex',QuestionAgent):
            s=Service(ROOT,Path(folder)/'data',Path(folder)/'archive',connect=False);QuestionAgent.asked.clear()
            try:
                s.store.set_setting('daily_autosave',False);id=s.store.conversations()[0]['id']
                job=s.enqueue({'conversation_id':id,'content':'ORIGINAL_TASK','route':'codex','client_key':'q-service'})
                self.assertTrue(QuestionAgent.asked.wait(2))
                request=s.conversation(id)['input_requests'][0]
                with self.assertRaises(ValueError):s.answer_question({'conversation_id':'wrong','question_id':request['id'],'answers':{'hardware':'B'}})
                s.answer_question({'conversation_id':id,'question_id':request['id'],'answers':{'hardware':'用户型号'}})
                until=time.monotonic()+3
                while s.conversation(id)['job']['status']=='running' and time.monotonic()<until:time.sleep(.01)
                c=s.job_conversation(job);prompt=s.prompt(c,'codex',1)
                self.assertIn('ORIGINAL_TASK',prompt.split('[当前用户请求：必须优先遵守]')[-1]);self.assertIn('用户型号',prompt)
                self.assertEqual(s.conversation(id)['input_requests'][0]['state'],'answered')
            finally:s.close();s.store.db.close()

    def test_strategy_requires_explicit_first_then_second_and_never_reads_attachments(self):
        self.assertEqual(resolve_strategy('帮我修复并安装'),'direct')
        self.assertEqual(resolve_strategy('第一轮先讨论，第二轮再开始操作'),'discuss_first')
        self.assertEqual(resolve_strategy('先讨论一轮，第二轮再操作'),'discuss_first')
        self.assertEqual(resolve_strategy('讨论一轮，第二轮开始做'),'discuss_first')
        self.assertEqual(resolve_strategy('只讨论，不修改'),'direct')
        self.assertEqual(resolve_strategy('问题','discuss_first'),'discuss_first')

    def test_first_round_read_only_then_execute_keeps_user_selected_permission(self):
        class PhaseAgent:
            flags=[]
            def __init__(self,*args):pass
            def models(self):return []
            def quota(self):return {}
            def run(self,prompt,model,emit,cancel,full_access=False,read_only_tools=False,**options):
                self.flags.append((full_access,read_only_tools,prompt));return '阶段夹具结果',{'synthetic':True}
        for permission,expected in [('full',[(False,True),(False,True),(True,False),(True,False)]),('discussion',[(False,False)]*4)]:
            with tempfile.TemporaryDirectory() as folder,patch('backend.service.Codex',PhaseAgent),patch('backend.service.CodeBuddy',PhaseAgent):
                s=Service(ROOT,Path(folder)/'data',Path(folder)/'archive',connect=False);PhaseAgent.flags=[]
                try:
                    id=s.store.conversations()[0]['id'];s.store.set_setting('daily_autosave',False)
                    prefs=s.preferences(id);prefs['access_mode']=permission;s.store.set_setting('models:'+id,prefs)
                    job=s.enqueue({'conversation_id':id,'content':'第一轮讨论，第二轮开始操作','route':'both','rounds':1,'client_key':'phase'})
                    self.assertEqual(job['rounds'],2)
                    until=time.monotonic()+3
                    while s.conversation(id)['job']['status'] in ('queued','running') and time.monotonic()<until:time.sleep(.01)
                    self.assertEqual([(a,b) for a,b,_ in PhaseAgent.flags],expected)
                    self.assertIn('首轮只读讨论',PhaseAgent.flags[0][2])
                finally:s.close();s.store.db.close()

if __name__=='__main__':unittest.main()
