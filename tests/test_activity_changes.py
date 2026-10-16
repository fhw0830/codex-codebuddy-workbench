import json
from pathlib import Path
import sys,tempfile,threading,time,unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from backend.agents import tool_record
from backend.activity import Activity
from backend.service import Service
from backend.codebuddy_stream import StreamState

class Changes(unittest.TestCase):
    def test_native_500_is_identified_without_losing_partial_text(self):
        emitted=[]
        stream=StreamState(emitted.append,lambda x:None,lambda x:None,tool_record,True)
        stream.consume({'type':'assistant','message':{'role':'assistant','content':[{'type':'text','text':'500 internal server error (trace/session)'}]}})
        with self.assertRaisesRegex(RuntimeError,'模型请求返回500'):
            stream.consume({'type':'result','subtype':'error_during_execution','is_error':True})
        self.assertTrue(any('500 internal server error' in text for text in emitted))
    def test_native_diff_keeps_path_kind_and_actual_lines(self):
        row=tool_record({'id':'edit','type':'fileChange','status':'completed','changes':[{'path':'demo.py','kind':{'type':'update'},'diff':'@@ -1 +1 @@\n-old\n+new'}]})
        self.assertEqual(row['changes'][0]['diff'],'@@ -1 +1 @@\n-old\n+new');self.assertEqual(row['changes'][0]['scope'],'tool')
    def test_codebuddy_edit_has_snippet_diff_and_write_does_not_invent_old_content(self):
        edit=tool_record({'id':'e','name':'Edit','input':{'file_path':'demo.py','old_string':'old','new_string':'new'}},'running')
        self.assertIn('\n-old\n+new',edit['changes'][0]['diff']);self.assertEqual(edit['changes'][0]['scope'],'snippet')
        write=tool_record({'id':'w','name':'Write','input':{'file_path':'demo.py','content':'new'}},'running')
        self.assertNotIn('diff',write['changes'][0]);self.assertEqual(write['changes'][0]['scope'],'submitted')
    def test_shell_diff_is_recognized_but_plain_command_is_not_a_change(self):
        row=tool_record({'id':'x','type':'commandExecution','aggregatedOutput':'diff --git a/demo.py b/demo.py\n--- a/demo.py\n+++ b/demo.py\n@@ -1 +1 @@\n-old\n+new'})
        self.assertEqual(row['changes'][0]['path'],'demo.py')
        self.assertNotIn('changes',tool_record({'id':'x','type':'commandExecution','command':'python update.py','output':'done'}))
    def test_activity_updates_keep_the_first_call_position(self):
        a=Activity();a.text({'id':'first','text':'先检查'});a.tool({'id':'tool','status':'running'});a.text({'id':'last','text':'完成'});a.tool({'id':'tool','status':'completed'});a.question('q')
        rows=a.snapshot();self.assertEqual([x['type'] for x in rows],['text','tool','text','question']);self.assertEqual(rows[1]['tool']['status'],'completed')
    def test_real_service_persists_public_sequence_and_final_answer(self):
        class Agent:
            def __init__(self,*a):pass
            def models(self):return []
            def quota(self):return {}
            def run(self,prompt,model,emit,cancel,on_progress=None,on_tool=None,**options):
                on_progress({'activity':{'id':'one','type':'text','text':'先检查文件'}})
                emit('先检查文件');on_tool({'id':'read','name':'Read','type':'tool_use','status':'completed'})
                on_progress({'activity':{'id':'two','type':'text','text':'检查完成'}});emit('检查完成');return '检查完成',{}
        with tempfile.TemporaryDirectory() as folder,patch('backend.service.Codex',Agent):
            s=Service(ROOT,Path(folder)/'data',Path(folder)/'archive',connect=False);s.store.set_setting('daily_autosave',False)
            try:
                c=s.store.conversations()[0]['id'];s.enqueue({'conversation_id':c,'route':'codex','content':'合成任务','client_key':'fixture'})
                until=time.monotonic()+3
                while s.conversation(c)['job']['status'] in ('queued','running') and time.monotonic()<until:time.sleep(.01)
                answer=s.conversation(c)['messages'][-1];self.assertEqual(answer['status'],'completed')
                self.assertEqual([e['type'] for e in answer['meta']['activity']],['text','tool','text']);self.assertEqual(answer['content'],'检查完成')
            finally:s.close();s.store.db.close()

if __name__=='__main__':unittest.main()
