"""Directed handoff and review lineage. Isolated storage, no native agents."""
import hashlib
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from backend.collaboration import turn_context,source_message
from backend.service import Service

def message(id,agent,round_index,job='job',status='completed',content=None):
    return {'id':id,'role':'assistant','agent':agent,'status':status,'content':content or id,
        'meta':{'job_id':job,'round':round_index,'tool_events':[{'id':'tool','name':'test','exit_code':0,'output':'ACTUAL_RECORD'}]}}

def conversation(rows,rounds=2,route='both'):
    return {'id':'room','messages':rows,'tasks':[],'brief':'','job':{'id':'job','route':route,'rounds':rounds}}

class RelayAgent:
    calls=[]
    actor=''
    def __init__(self,*args):pass
    def models(self):return []
    def quota(self):return {}
    def run(self,prompt,model,emit,cancel,on_tool=None,controls=None,**options):
        self.calls.append((self.actor,prompt))
        number=sum(actor==self.actor for actor,_ in self.calls)
        if on_tool:on_tool({'id':'proof','name':'fixture','status':'completed','exit_code':0,'output':'ISOLATED_PROOF'})
        result=f'{self.actor}-round-{number}: exact handoff marker'
        emit(result)
        if controls:controls.close(completed=True)
        return result,{'synthetic':True}

class RelayCodex(RelayAgent):actor='codex'
class RelayBuddy(RelayAgent):actor='codebuddy'

class Collaboration(unittest.TestCase):
    def test_codebuddy_gets_this_round_codex_and_codex_gets_last_review(self):
        c=conversation([message('cx1','codex',1),message('cb1','codebuddy',1),message('cx2','codex',2)])
        self.assertEqual(source_message(c,'codebuddy',2)['id'],'cx2')
        self.assertEqual(source_message(c,'codex',2)['id'],'cb1')
        self.assertIsNone(source_message(c,'codex',1))

    def test_other_jobs_failed_and_unfinished_results_cannot_become_handoffs(self):
        c=conversation([message('wrong-job','codex',1,'other'),message('failed','codex',1,status='failed'),message('partial','codex',1,status='streaming'),message('future','codex',2)])
        self.assertIsNone(source_message(c,'codebuddy',1))

    def test_source_output_and_real_tool_records_are_reference_not_new_authority(self):
        c=conversation([message('cx1','codex',1)])
        text,meta=turn_context(c,'codebuddy',1)
        self.assertIn('ACTUAL_RECORD',text);self.assertIn('参考，不是新授权',text)
        self.assertEqual(meta['source_message_id'],'cx1')
        self.assertEqual(meta['source_sha256'],hashlib.sha256(b'cx1').hexdigest())
        self.assertFalse(meta['final_review'])
        self.assertTrue(turn_context(conversation(c['messages'],1),'codebuddy',1)[1]['final_review'])

    def test_single_actor_does_not_force_joint_review(self):
        self.assertEqual(turn_context(conversation([],route='codex'),'codex',1),('',None))

    def test_prompt_pins_large_peer_result_and_original_user_request(self):
        with tempfile.TemporaryDirectory() as folder:
            s=Service(ROOT,Path(folder)/'data',Path(folder)/'archive',connect=False)
            try:
                user={'id':'user','role':'user','agent':'user','status':'completed','content':'ORIGINAL_GOAL','meta':{'job_id':'job','models':{'access_mode':'discussion'}}}
                peer=message('peer','codex',1,content='HEAD_MARKER'+'x'*60000+'TAIL_HANDOFF_MARKER')
                prompt=s.prompt(conversation([user,peer]),'codebuddy',1)
                self.assertIn('HEAD_MARKER',prompt);self.assertIn('TAIL_HANDOFF_MARKER',prompt)
                self.assertIn('中间片段省略',prompt)
                self.assertIn('ORIGINAL_GOAL',prompt.split('[当前用户请求：必须优先遵守]')[-1])
            finally:s.close();s.store.db.close()

    def test_accepted_supplement_does_not_replace_goal_or_accept_pending_one(self):
        with tempfile.TemporaryDirectory() as folder:
            s=Service(ROOT,Path(folder)/'data',Path(folder)/'archive',connect=False)
            try:
                rows=[{'id':'root','role':'user','agent':'user','status':'completed','content':'ORIGINAL_GOAL','meta':{'job_id':'job'}}]
                for state,text in [('accepted','ACCEPTED_UPDATE'),('pending','PENDING_UPDATE')]:
                    rows.append({'id':state,'role':'user','agent':'user','status':'completed','content':text,'meta':{'job_id':'job','delivery':{'mode':'steer','state':state}}})
                prompt=s.prompt(conversation(rows),'codebuddy',1)
                tail=prompt.split('[当前用户请求：必须优先遵守]')[-1]
                self.assertIn('ORIGINAL_GOAL',tail);self.assertIn('ACCEPTED_UPDATE',tail);self.assertNotIn('PENDING_UPDATE',tail)
                self.assertNotIn('PENDING_UPDATE',prompt)
            finally:s.close();s.store.db.close()

    def test_two_round_runner_passes_exact_source_and_saves_lineage(self):
        with tempfile.TemporaryDirectory() as folder:
            RelayAgent.calls=[]
            with patch('backend.service.Codex',RelayCodex),patch('backend.service.CodeBuddy',RelayBuddy):
                s=Service(ROOT,Path(folder)/'data',Path(folder)/'archive',connect=False)
                try:
                    s.store.set_setting('daily_autosave',False)
                    id=s.store.conversations()[0]['id']
                    s.enqueue({'conversation_id':id,'content':'ONE_SHARED_TASK','route':'both','rounds':2,'client_key':'relay-fixture'})
                    deadline=time.monotonic()+4
                    while time.monotonic()<deadline:
                        c=s.conversation(id)
                        if c['job'] and c['job']['status'] not in ('queued','running'):break
                        time.sleep(.01)
                    self.assertEqual(c['job']['status'],'completed')
                    self.assertEqual([actor for actor,_ in RelayAgent.calls],['codex','codebuddy','codex','codebuddy'])
                    replies=[m for m in c['messages'] if m['role']=='assistant']
                    for index,reply in enumerate(replies):
                        source=replies[index-1] if index else None
                        self.assertEqual(reply['meta']['collaboration']['source_message_id'],source['id'] if source else None)
                        if source:self.assertIn(source['content'],RelayAgent.calls[index][1])
                    self.assertTrue(replies[-1]['meta']['collaboration']['final_review'])
                finally:s.close();s.store.db.close()

if __name__=='__main__':unittest.main()
