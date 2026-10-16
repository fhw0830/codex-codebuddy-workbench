import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from backend.service import Service
from backend.agents import Cancelled


class GateAgent:
    entered=threading.Event()
    release=threading.Event()
    calls=[]
    updates=[]
    reject=False
    def __init__(self,*args):pass
    def run(self,prompt,model,emit,cancel,controls=None,on_progress=None,**options):
        self.calls.append(prompt)
        self.entered.set()
        while not self.release.wait(.01):
            if cancel.is_set():raise Cancelled('fixture cancelled')
            for id,text in controls.drain():
                self.updates.append(text)
                controls.resolve(id,not self.reject,'fixture rejected' if self.reject else '')
        if on_progress:on_progress({'phase':'planning','plan':[{'step':'读取 fixture.py','status':'completed'},{'step':'核对用例','status':'pending'}]})
        controls.close(completed=True)
        return 'fixture completed',{'tool_calls':0,'synthetic':True}
    def models(self):return []
    def quota(self):return {}


class Followups(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        root=Path(self.temp.name)
        self.service=Service(ROOT,root/'data',root/'archive',connect=False)
        self.service.store.set_setting('daily_autosave',False)
        self.id=self.service.store.conversations()[0]['id']
        GateAgent.calls=[];GateAgent.updates=[];GateAgent.entered.clear();GateAgent.release.clear();GateAgent.reject=False
        self.patches=[patch('backend.service.Codex',GateAgent),patch('backend.service.CodeBuddy',GateAgent)]
        for p in self.patches:p.start()
    def tearDown(self):
        GateAgent.release.set();self.service.close();self.service.store.db.close()
        for p in self.patches:p.stop()
        self.temp.cleanup()
    def send(self,text,**fields):
        return self.service.enqueue({'conversation_id':self.id,'content':text,'route':'codex','client_key':text,**fields})
    def wait_for(self,predicate):
        deadline=time.monotonic()+3
        while time.monotonic()<deadline:
            if predicate():return
            time.sleep(.01)
        self.fail('fixture did not reach expected state')
    def test_queue_is_ordered_and_future_prompts_do_not_enter_the_active_task(self):
        self.send('FIRST_TASK');self.assertTrue(GateAgent.entered.wait(2))
        second=self.send('SECOND_TASK',send_mode='queue');third=self.send('THIRD_TASK',send_mode='queue')
        self.assertEqual(len(GateAgent.calls),1)
        self.assertNotIn('SECOND_TASK',GateAgent.calls[0]);self.assertNotIn('THIRD_TASK',GateAgent.calls[0])
        self.assertEqual(len(self.service.conversation(self.id)['queue']),2)
        GateAgent.release.set()
        self.wait_for(lambda:self.service.store.one('SELECT status FROM jobs WHERE id=?',(third['id'],))['status']=='completed')
        self.assertEqual(len(GateAgent.calls),3)
        self.assertNotIn('THIRD_TASK',GateAgent.calls[1]);self.assertIn('fixture completed',GateAgent.calls[1])
        self.assertIn('SECOND_TASK',GateAgent.calls[1].split('[当前用户请求：必须优先遵守]')[-1])
        self.assertIn('THIRD_TASK',GateAgent.calls[2].split('[当前用户请求：必须优先遵守]')[-1])
        users=[m for m in self.service.conversation(self.id)['messages'] if m['role']=='user']
        for message in users:
            timing=message['meta']['timing']
            self.assertEqual(timing['status'],'completed')
            self.assertIsNotNone(timing['finished_at'])
            self.assertGreaterEqual(timing['elapsed_s'],0)
            self.assertGreaterEqual(timing['wait_s'],0)
    def test_cancelled_queue_is_never_executed(self):
        self.send('FIRST_TASK');self.assertTrue(GateAgent.entered.wait(2))
        queued=self.send('NEVER_EXECUTE',send_mode='queue');self.service.stop(queued['id']);GateAgent.release.set()
        self.wait_for(lambda:not self.service.conversation(self.id)['job']['status'] in ('queued','running'))
        self.assertEqual(len(GateAgent.calls),1)
        self.assertEqual(self.service.conversation(self.id)['messages'][2]['meta']['delivery']['state'],'cancelled')
    def test_steer_is_acknowledged_without_restarting_or_repeating_the_agent(self):
        self.send('FIRST_TASK');self.assertTrue(GateAgent.entered.wait(2))
        update=self.service.steer({'conversation_id':self.id,'content':'ONLY_SUPPLEMENT','client_key':'update1'})
        self.wait_for(lambda:next(m for m in self.service.conversation(self.id)['messages'] if m['id']==update['id'])['meta']['delivery']['state']=='accepted')
        receipt=next(m for m in self.service.conversation(self.id)['messages'] if m['id']==update['id'])
        self.assertEqual(receipt['meta']['delivery']['state'],'accepted');self.assertEqual(len(GateAgent.calls),1)
        target=next(m for m in self.service.conversation(self.id)['messages'] if m['role']=='assistant')
        self.assertEqual(receipt['meta']['in_reply_to'],target['id'])
        same=self.service.steer({'conversation_id':self.id,'content':'ONLY_SUPPLEMENT','client_key':'update1'})
        self.assertEqual(same['id'],update['id']);self.assertEqual(GateAgent.updates,['ONLY_SUPPLEMENT'])
    def test_native_rejected_steer_becomes_a_real_queue_item(self):
        GateAgent.reject=True;self.send('FIRST_TASK');self.assertTrue(GateAgent.entered.wait(2))
        update=self.service.steer({'conversation_id':self.id,'content':'RACE_SUPPLEMENT','client_key':'update2'})
        self.wait_for(lambda:bool(self.service.conversation(self.id)['queue']))
        GateAgent.release.set()
        self.wait_for(lambda:len(GateAgent.calls)==2)
        self.assertEqual(sum(m['id']==update['id'] for m in self.service.conversation(self.id)['messages']),1)
        self.assertIn('RACE_SUPPLEMENT',GateAgent.calls[1])

    def queued(self,text):
        job=self.send(text,send_mode='queue')
        message=next(m for m in self.service.conversation(self.id)['messages'] if m['meta'].get('job_id')==job['id'])
        return job,message

    def test_queue_edit_keeps_order_and_delete_never_leaks_into_later_prompt(self):
        self.send('FIRST_TASK');self.assertTrue(GateAgent.entered.wait(2))
        _,message=self.queued('OLD_TEXT');_,deleted=self.queued('DELETE_SECRET_TASK')
        self.service.queued_action({'conversation_id':self.id,'message_id':message['id'],'action':'edit','content':'EDITED_TEXT'})
        self.service.queued_action({'conversation_id':self.id,'message_id':deleted['id'],'action':'delete'})
        last=self.send('LAST_TASK',send_mode='queue');GateAgent.release.set()
        self.wait_for(lambda:self.service.store.one('SELECT status FROM jobs WHERE id=?',(last['id'],))['status']=='completed')
        self.assertEqual(len(GateAgent.calls),3)
        self.assertIn('EDITED_TEXT',GateAgent.calls[1]);self.assertNotIn('OLD_TEXT',GateAgent.calls[1])
        self.assertTrue(all('DELETE_SECRET_TASK' not in p for p in GateAgent.calls))

    def test_guidance_reuses_one_message_and_never_executes_as_second_task(self):
        self.send('FIRST_TASK');self.assertTrue(GateAgent.entered.wait(2))
        _,message=self.queued('GUIDE_CURRENT_TASK')
        self.service.queued_action({'conversation_id':self.id,'message_id':message['id'],'action':'guide'})
        self.wait_for(lambda:'GUIDE_CURRENT_TASK' in GateAgent.updates)
        GateAgent.release.set();self.wait_for(lambda:not self.service.conversation(self.id)['job']['status'] in ('queued','running'))
        self.assertEqual(len(GateAgent.calls),1)
        self.assertEqual(sum(m['id']==message['id'] for m in self.service.conversation(self.id)['messages']),1)
        with self.assertRaises(ValueError):self.service.queued_action({'conversation_id':self.id,'message_id':message['id'],'action':'delete'})

    def test_queue_actions_cannot_change_active_task_or_other_conversation(self):
        self.send('FIRST_TASK');self.assertTrue(GateAgent.entered.wait(2))
        root=self.service.conversation(self.id)['messages'][0]
        with self.assertRaises(ValueError):self.service.queued_action({'conversation_id':self.id,'message_id':root['id'],'action':'edit','content':'CHANGE_ACTIVE'})
        _,pending=self.queued('PENDING')
        other=self.service.store.create_conversation()['id']
        with self.assertRaises(ValueError):self.service.queued_action({'conversation_id':other,'message_id':pending['id'],'action':'delete'})
        self.assertFalse(self.service.cancel_flags[self.service.conversation(self.id)['job']['id']].is_set())


if __name__=='__main__':unittest.main()
