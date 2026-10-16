import json,sys,tempfile,threading,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from backend.service import Service
from backend import workbench,history_compaction

class Workbench(unittest.TestCase):
 def test_codex_shared_launch_works_without_turn_controls(self):
  from types import SimpleNamespace
  from backend.agents import Codex
  process=SimpleNamespace(stdout=[],stderr=[])
  with patch('backend.agents.spawn',return_value=process),patch('backend.agents.threading.Thread.start'):
   result,events,errors=Codex('fixture-runtime',Path(self.tmp.name)).launch()
  self.assertIs(result,process)
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.s=Service(ROOT,Path(self.tmp.name)/'data',Path(self.tmp.name)/'archive',connect=False)
  self.s.store.set_setting('daily_autosave',False);self.cid=self.s.store.conversations()[0]['id']
 def tearDown(self):self.s.close();self.s.store.db.close();self.tmp.cleanup()
 def source(self):
  prefs={**self.s.preferences(self.cid),'access_mode':'discussion'}
  job,_=self.s.store.create_job(self.cid,'both',1,'original','ORIGINAL_GOAL',{'models':prefs,'route':'both','rounds':1})
  self.s.store.update_job(job['id'],'failed')
  source=self.s.store.message(self.cid,'assistant','codex','CODEX_PRIOR_DELIVERY','completed',{'job_id':job['id'],'round':1})
  mid=self.s.store.message(self.cid,'assistant','codebuddy','PARTIAL_REVIEW','failed',{'job_id':job['id'],'round':1,'plan':[{'step':'已修改文件','status':'completed'},{'step':'复核文件','status':'in_progress'}], 'tool_events':[{'id':'write','name':'Write','status':'completed','changes':[{'path':'a.py'}]}]})
  return job,source,mid
 def test_resume_idempotent_and_preserves_source_permissions(self):
  _,source,mid=self.source()
  self.s.store.set_setting('models:'+self.cid,{**self.s.preferences(self.cid),'access_mode':'full'})
  with patch.object(self.s,'dispatch'):
   first=self.s.resume({'conversation_id':self.cid,'message_id':mid});second=self.s.resume({'conversation_id':self.cid,'message_id':mid})
  self.assertEqual(first['id'],second['id'])
  c=self.s.job_conversation(first);primary=c['messages'][-1]
  self.assertEqual(primary['meta']['models']['access_mode'],'discussion')
  self.assertEqual(primary['meta']['resume_cursor'],{'agent':'codebuddy','round':1})
  receipt={};text=self.s.prompt(c,'codebuddy',1,receipt)
  self.assertIn('ORIGINAL_GOAL',text);self.assertIn('CODEX_PRIOR_DELIVERY',text);self.assertIn('PARTIAL_REVIEW',text)
  self.assertIn('不重放已完成写入',text);self.assertEqual(receipt['handoff_source_message_id'],source)
 def test_resume_runs_only_failed_actor_and_does_not_repeat_codex(self):
  _,_,mid=self.source();calls=[]
  class Agent:
   def __init__(self,*args):pass
   def run(self,prompt,*args,**kwargs):calls.append(prompt);return '复核完成，原修改未重放。',{}
   def models(self):return []
   def quota(self):return {}
  with patch.object(self.s,'dispatch'):job=self.s.resume({'conversation_id':self.cid,'message_id':mid})
  with patch('backend.service.Codex',Agent),patch('backend.service.CodeBuddy',Agent):self.s.run_job(job,threading.Event())
  self.assertEqual(len(calls),1);self.assertIn('当前发言者：codebuddy',calls[0])
  reply=self.s.store.conversation(self.cid)['messages'][-1]
  self.assertEqual(reply['meta']['context_manifest']['agent'],'codebuddy')
 def test_wrong_room_and_completed_reply_cannot_resume(self):
  _,source,mid=self.source();other=self.s.store.create_conversation()['id']
  for cid,message in [(other,mid),(self.cid,source)]:
   with self.assertRaises(ValueError):self.s.resume({'conversation_id':cid,'message_id':message})
 def test_repeated_failure_keeps_original_peer_handoff(self):
  _,source,mid=self.source()
  with patch.object(self.s,'dispatch'):first=self.s.resume({'conversation_id':self.cid,'message_id':mid})
  self.s.store.update_job(first['id'],'failed')
  failed=self.s.store.message(self.cid,'assistant','codebuddy','SECOND_PARTIAL','failed',{'job_id':first['id'],'round':1,'collaboration':{'source_message_id':source,'source_agent':'codex'}})
  with patch.object(self.s,'dispatch'):again=self.s.resume({'conversation_id':self.cid,'message_id':failed})
  receipt={};prompt=self.s.prompt(self.s.job_conversation(again),'codebuddy',1,receipt)
  self.assertIn('CODEX_PRIOR_DELIVERY',prompt);self.assertEqual(receipt['handoff_source_message_id'],source)
 def test_compaction_protects_resume_source_without_changing_real_job_status(self):
  old,_,mid=self.source()
  with patch.object(self.s,'dispatch'):job=self.s.resume({'conversation_id':self.cid,'message_id':mid})
  with patch('backend.history_compaction.plan',return_value=[]) as plan:self.s.compact_history(job,threading.Event())
  self.assertEqual(plan.call_args.args[1][old['id']],'protected_resume_source')
  self.assertEqual(self.s.store.one('SELECT status FROM jobs WHERE id=?',(old['id'],))['status'],'failed')
 def test_context_receipt_hash_and_attachment_scope(self):
  job,_,_=self.source();r={};c=self.s.job_conversation(job)
  text=self.s.prompt(c,'codex',1,r)
  import hashlib
  self.assertEqual(r['prompt_sha256'],hashlib.sha256(text.encode()).hexdigest());self.assertEqual(r['prompt_chars'],len(text))
  r=workbench.context_receipt(c,'codebuddy',1,[],[{'name':'image','kind':'image','content':'placeholder'}],'TEXT',None,None)
  self.assertFalse(r['references'][0]['vision_sent'])
 def test_token_pressure_includes_tools_and_preserves_whole_recent_jobs(self):
  messages=[];jobs={}
  for i in range(9):
   job=str(i);jobs[job]='completed'
   for role in ('user','assistant'):messages.append({'id':job+role,'role':role,'agent':'codex','status':'completed','content':'短消息','meta':{'job_id':job,'tool_events':[{'id':'log','output':'x'*10000}] if role=='assistant' else []}})
  chosen=history_compaction.plan(messages,jobs,'current')
  self.assertTrue(chosen);self.assertLess(len(chosen),len(messages));self.assertTrue(all(sum(m['meta']['job_id']==j for m in chosen) in (0,2) for j in jobs))
  self.assertIn('tools',json.loads(history_compaction.batches(chosen)[1].splitlines()[0]) if len(history_compaction.batches(chosen))>1 else json.loads(history_compaction.batches(chosen)[0].splitlines()[0]))
 def test_runtime_distinguishes_process_and_tool_activity(self):
  class Process:
   def poll(self):return None
  class Control:process=Process()
  r=workbench.runtime_status({'controls':Control()},{'id':'m','meta':{'runtime':{'last_event_at':'time'},'tool_events':[{'id':'a','name':'Shell','status':'running'}]}})
  self.assertTrue(r['process_alive']);self.assertEqual(r['active_tools'][0]['name'],'Shell');self.assertEqual(r['last_event_at'],'time')

if __name__=='__main__':unittest.main()
