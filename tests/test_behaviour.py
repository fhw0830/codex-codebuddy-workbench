"""Behavioural regressions in isolated temp directories; no real agents or robots."""
import json
import base64
import io
import queue
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
from backend.store import Store, clean, uid, now
from backend.agents import Cancelled

class FakeAgent:
    mode='ok'
    calls=[]
    efforts=[]
    image_counts=[]
    access_modes=[]
    started=threading.Event()
    release=threading.Event()
    def __init__(self,*args):
        pass
    def models(self):
        return [{'id':'gpt-6.1-sol','name':'synthetic'},{'id':'deepseek-v4.1-flash','name':'synthetic'},{'id':'glm-5.3','name':'synthetic'}]
    def quota(self):
        return {'rateLimits':None}
    def run(self,prompt,model,emit,cancel,timeout=180,effort=None,images=None,full_access=False,on_tool=None,on_progress=None,controls=None,read_only_tools=False):
        self.calls.append((prompt,model))
        self.efforts.append(effort)
        self.image_counts.append(len(images or []))
        self.access_modes.append(full_access)
        if full_access and on_tool:
            on_tool({'id':'synthetic-tool','name':'synthetic-command','command':'fixture only','status':'completed','exit_code':0})
        emit('合成测试：部分文本')
        self.started.set()
        if self.mode=='fail':
            raise RuntimeError('合成测试：服务端返回额度错误')
        if self.mode in ('wait','gate'):
            while not self.release.wait(.01):
                if cancel.is_set():
                    raise Cancelled('合成测试：取消')
        if cancel.is_set():
            raise Cancelled('合成测试：取消')
        return '合成测试回复',{'requested_model':model,'credit':1.25,'tool_calls':0,'synthetic':True}

class Behaviour(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        tmp=Path(self.temp.name)
        self.archive=tmp/'archive';self.archive.mkdir()
        self.patchers=[patch('backend.service.Codex',FakeAgent),patch('backend.service.CodeBuddy',FakeAgent)]
        for p in self.patchers:p.start()
        FakeAgent.mode='ok';FakeAgent.calls=[];FakeAgent.efforts=[];FakeAgent.image_counts=[];FakeAgent.access_modes=[];FakeAgent.started.clear();FakeAgent.release.clear()
        self.service=Service(ROOT,tmp/'data',self.archive,connect=False)
        self.service.store.set_setting('daily_autosave',False)
        self.id=self.service.store.conversations()[0]['id']
    def tearDown(self):
        FakeAgent.release.set()
        self.service.close()
        self.service.store.db.close()
        for p in self.patchers:p.stop()
        self.temp.cleanup()
    def send(self,**changes):
        request={'conversation_id':self.id,'content':'测试需求','route':'both','rounds':1,'client_key':uid()}
        request.update(changes)
        return self.service.enqueue(request)
    def wait(self):
        until=time.monotonic()+4
        while time.monotonic()<until:
            c=self.service.conversation(self.id)
            if c['job'] and c['job']['status'] not in ('queued','running'):return c
            time.sleep(.01)
        self.fail('synthetic job did not complete')
    def test_duplicate_submit_does_not_repeat_model_or_user_message(self):
        key=uid();first=self.send(client_key=key);self.wait();second=self.send(client_key=key)
        self.assertEqual(first['id'],second['id'])
        self.assertEqual(len(FakeAgent.calls),2)
        self.assertEqual(sum(m['role']=='user' for m in self.service.conversation(self.id)['messages']),1)
    def test_duplicate_key_cannot_attach_to_another_room(self):
        key=uid();self.send(client_key=key);self.wait()
        other=self.service.store.create_conversation()
        with self.assertRaises(ValueError):self.send(client_key=key,conversation_id=other['id'])
        self.assertEqual(self.service.conversation(other['id'])['messages'],[])
    def test_busy_room_rejects_second_submit(self):
        FakeAgent.mode='wait';job=self.send();self.assertTrue(FakeAgent.started.wait(2))
        with self.assertRaises(ValueError):self.send()
        self.service.stop(job['id']);self.assertEqual(self.wait()['job']['status'],'interrupted')
    def test_cancellation_preserves_partial_and_stops_next_actor(self):
        FakeAgent.mode='wait';job=self.send();self.assertTrue(FakeAgent.started.wait(2));self.service.stop(job['id'])
        c=self.wait();answers=[m for m in c['messages'] if m['role']=='assistant']
        self.assertEqual(len(FakeAgent.calls),1);self.assertEqual(answers[0]['status'],'interrupted')
        self.assertIn('部分文本',answers[0]['content'])
    def test_upstream_error_not_misreported_as_success(self):
        FakeAgent.mode='fail';self.send();c=self.wait()
        self.assertEqual(c['job']['status'],'failed');self.assertEqual(c['messages'][-1]['status'],'failed')
        self.assertEqual(len(FakeAgent.calls),1)
    def test_restarting_does_not_auto_repeat_stale_job(self):
        path=Path(self.temp.name)/'restart.sqlite3';a=Store(path);c=a.create_conversation()
        job,_=a.create_job(c['id'],'both',1,uid(),'unfinished',{})
        message=a.message(c['id'],'assistant','codex','partial','streaming')
        a.update_job(job['id'],'running');a.db.close();b=Store(path)
        self.assertEqual(b.conversation(c['id'])['job']['status'],'interrupted')
        self.assertEqual(b.conversation(c['id'])['messages'][-1]['content'],'partial')
        self.assertEqual(b.conversation(c['id'])['messages'][-1]['status'],'interrupted');b.db.close()
    def test_rooms_keep_their_own_history_and_models(self):
        other=self.service.store.create_conversation()
        self.service.health['codebuddy']['models']=FakeAgent().models()
        original_model=self.service.preferences(self.id)['codebuddy_model']
        self.service.set_preferences(other['id'],{'codebuddy_model':'glm-5.3'})
        self.send(route='codebuddy');self.wait()
        self.assertEqual(self.service.conversation(other['id'])['messages'],[])
        self.assertEqual(self.service.preferences(self.id)['codebuddy_model'],original_model)
        self.assertEqual(self.service.preferences(other['id'])['codebuddy_model'],'glm-5.3')
    def test_requirements_frozen_for_both_actors_in_current_turn(self):
        self.service.store.update_conversation(self.id,{'brief':'固定原需求SENTINEL'})
        FakeAgent.mode='gate';self.send();self.assertTrue(FakeAgent.started.wait(2))
        self.service.store.update_conversation(self.id,{'brief':'后续新需求CHANGED'})
        FakeAgent.release.set();self.wait()
        self.assertEqual(len(FakeAgent.calls),2)
        self.assertTrue(all('固定原需求SENTINEL' in prompt for prompt,_ in FakeAgent.calls))
        self.assertFalse(any('后续新需求CHANGED' in prompt for prompt,_ in FakeAgent.calls))
    def test_credit_updates_not_double_counted_and_unknown_not_zero(self):
        id=self.service.store.message(self.id,'assistant','codebuddy','reply',meta={'credit':1.25})
        self.service.store.update_message(id,'reply','completed',{'credit':1.25})
        self.service.store.update_message(id,'reply','completed',{'credit':1.25})
        self.service.store.message(self.id,'assistant','codebuddy','unknown',meta={})
        c=self.service.conversation(self.id)
        self.assertEqual(c['credit_sum'],1.25);self.assertEqual(c['reported_credits'],1);self.assertEqual(c['unreported_credits'],1)
    def test_context_references_cannot_escape_archive(self):
        (Path(self.temp.name)/'outside.md').write_text('secret',encoding='utf-8')
        with self.assertRaises(ValueError):self.service.document('../outside.md')
        with self.assertRaises(ValueError):self.service.document(str(ROOT/'README.md'))
    def test_plain_and_json_credentials_are_redacted(self):
        self.assertNotIn('VALUEVERYSECRET',clean('{"apiKey": "VALUEVERYSECRET"}'))
        self.assertNotIn('VALUEVERYSECRET',clean('Authorization: Bearer VALUEVERYSECRET'))
        self.assertNotIn('VALUEVERYSECRET',clean('password=VALUEVERYSECRET'))
        self.assertNotIn('hidden-body',clean('-----BEGIN PRIVATE KEY-----hidden-body-----END PRIVATE KEY-----'))
    def test_fork_carries_requirements_history_open_tasks_and_model(self):
        self.service.store.update_conversation(self.id,{'brief':'原需求'})
        self.service.store.message(self.id,'user','user','原始讨论')
        self.service.store.set_setting('models:'+self.id,{'codex_model':'gpt-6.1-sol','codebuddy_model':'glm-5.3'})
        for status in ('todo','done'):
            self.service.store.execute('INSERT INTO tasks VALUES(?,?,?,?,?,?,?)',(uid(),self.id,status,'user',status,now(),now()))
        c=self.service.fork(self.id)
        self.assertIn('原需求',c['brief']);self.assertIn('原始讨论',c['brief'])
        self.assertEqual([t['status'] for t in c['tasks']],['todo']);self.assertEqual(c['preferences']['codebuddy_model'],'glm-5.3')
    def test_archive_failure_does_not_reclassify_successful_reply(self):
        with patch.object(self.service,'daily_log',side_effect=OSError('temporary archive error')):
            self.send();c=self.wait()
        self.assertEqual(c['job']['status'],'completed')
        self.assertTrue(all(m['status']=='completed' for m in c['messages']))
        self.assertTrue(self.service.store.rows("SELECT * FROM events WHERE kind='archive_error'"))
    def test_daily_archives_have_exactly_two_owner_folders(self):
        self.service.store.set_setting('daily_autosave',True);self.send();self.wait()
        day=next(self.archive.iterdir())
        self.assertEqual(sorted(p.name for p in day.iterdir() if p.is_dir()),['CodeBuddy','Codex'])
        self.assertTrue(any((day/'Codex').glob('网页对话_*.md')))
        self.assertTrue(any((day/'CodeBuddy').glob('网页对话_*.md')))
        self.assertTrue((day/'00_每日合作总览.md').exists())

    def test_effort_is_validated_and_frozen_for_current_job(self):
        self.service.health['codex']['models']=[{'id':'gpt-6.1-sol','reasoningEfforts':[{'reasoningEffort':e} for e in ('low','high')]}]
        self.service.set_preferences(self.id,{'codex_effort':'high'})
        with self.assertRaises(ValueError):self.service.set_preferences(self.id,{'codex_effort':'unknown'})
        FakeAgent.mode='gate';self.send();self.assertTrue(FakeAgent.started.wait(2))
        self.service.set_preferences(self.id,{'codex_effort':'low'})
        FakeAgent.release.set();self.wait()
        self.assertEqual(FakeAgent.efforts,[ 'high',None ])
        self.assertEqual(self.service.preferences(self.id)['codex_effort'],'low')

    def test_delta_events_are_append_only_with_utf16_offsets(self):
        id=self.service.store.message(self.id,'assistant','codex','','streaming')
        self.service.store.update_message(id,'第一段🙂')
        self.service.store.update_message(id,'第一段🙂第二段')
        events=self.service.store.rows("SELECT payload FROM events WHERE kind='message_delta'")
        self.assertEqual(json.loads(events[-1]['payload'])['base_length'],5)
        self.assertEqual(json.loads(events[-1]['payload'])['delta'],'第二段')
        self.service.store.update_message(id,'替换后的内容')
        self.assertEqual(self.service.store.rows('SELECT kind FROM events ORDER BY seq DESC LIMIT 1')[0]['kind'],'message')

    def test_uploaded_text_is_read_and_carried_to_followup(self):
        doc=self.service.upload({'name':'drag-test.txt','data':base64.b64encode('UPLOAD_SENTINEL'.encode()).decode()})
        self.send(route='codex',attachments=[{'upload_id':doc['upload_id']}]);self.wait()
        self.send(route='codex',content='followup');self.wait()
        self.assertTrue(all('UPLOAD_SENTINEL' in prompt for prompt,_ in FakeAgent.calls))

    def test_image_is_passed_to_codex_and_not_text_only_codebuddy(self):
        from PIL import Image
        buffer=io.BytesIO();Image.new('RGB',(10,10),'red').save(buffer,format='PNG')
        doc=self.service.upload({'name':'fixture.png','data':base64.b64encode(buffer.getvalue()).decode()})
        self.assertEqual(doc['kind'],'image')
        with self.assertRaises(ValueError):self.send(attachments=[{'upload_id':doc['upload_id']}])
        self.send(route='codex',attachments=[{'upload_id':doc['upload_id']}]);self.wait()
        self.assertEqual(FakeAgent.image_counts,[1])
        self.send(route='codebuddy',content='讨论之前的文字描述');self.wait()
        self.assertEqual(FakeAgent.image_counts,[1,0])
        self.assertIn('视觉内容未传给CodeBuddy',FakeAgent.calls[-1][0])

    def test_upload_credentials_and_fake_images_rejected(self):
        for name in ('auth.json','fake.png'):
            with self.assertRaises(ValueError):self.service.upload({'name':name,'data':base64.b64encode(b'not an image').decode()})
        with self.assertRaises(ValueError):self.service.upload_path('../outside')

    def test_full_access_is_frozen_for_both_actors_and_trace_is_kept(self):
        self.service.set_preferences(self.id,{'access_mode':'full','workdir':self.temp.name})
        FakeAgent.mode='gate';self.send();self.assertTrue(FakeAgent.started.wait(2))
        self.service.set_preferences(self.id,{'access_mode':'discussion'})
        FakeAgent.release.set();conversation=self.wait()
        self.assertEqual(FakeAgent.access_modes,[True,True])
        for message in conversation['messages'][1:]:
            self.assertEqual(message['meta']['access_mode'],'full')
            self.assertEqual(message['meta']['tool_events'][0]['exit_code'],0)
        self.assertEqual(self.service.preferences(self.id)['access_mode'],'discussion')

    def test_invalid_permissions_and_missing_workdir_rejected(self):
        with self.assertRaises(ValueError):self.service.set_preferences(self.id,{'access_mode':'invented'})
        with self.assertRaises(ValueError):self.service.set_preferences(self.id,{'workdir':str(Path(self.temp.name)/'missing')})

    def test_full_access_conversations_answer_independently_without_tool_reservations(self):
        self.service.set_preferences(self.id,{'access_mode':'full','workdir':self.temp.name})
        other=self.service.store.create_conversation()['id']
        self.service.set_preferences(other,{'access_mode':'full','workdir':self.temp.name})
        FakeAgent.mode='gate';self.send(route='codex');self.assertTrue(FakeAgent.started.wait(2))
        second=self.send(route='codex',conversation_id=other)
        until=time.monotonic()+2
        while len(FakeAgent.access_modes)<2 and time.monotonic()<until:time.sleep(.01)
        self.assertEqual(FakeAgent.access_modes,[True,True])
        self.service.stop(second['id']);FakeAgent.release.set();self.wait()
        until=time.monotonic()+3
        while time.monotonic()<until:
            if self.service.conversation(other)['job']['status']=='interrupted':break
            time.sleep(.01)
        self.assertEqual(FakeAgent.access_modes,[True,True])

if __name__=='__main__':unittest.main(verbosity=2)
