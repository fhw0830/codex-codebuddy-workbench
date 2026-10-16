import io
import json
from pathlib import Path
import queue
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from backend.agents import CodeBuddy,tool_record
from backend.codebuddy_stream import StreamState
from backend.interaction import TurnUpdates


class BlockingLines:
    def __init__(self):self.queue=queue.Queue()
    def __iter__(self):return self
    def __next__(self):
        item=self.queue.get(timeout=3)
        if item is None:raise StopIteration
        return json.dumps(item)+'\n'


class FakeProcess:
    pid=999999
    def __init__(self):self.stdin=io.StringIO();self.stdout=BlockingLines();self.stderr=io.StringIO()
    def poll(self):return 0


class StreamingInteraction(unittest.TestCase):
    def test_tools_are_received_before_cli_completion_not_after_eof(self):
        process=FakeProcess();seen=threading.Event();outcomes=[]
        with tempfile.TemporaryDirectory() as folder,patch('backend.agents.spawn',return_value=process):
            def worker():
                try:outcomes.append(CodeBuddy({'node':'node','codebuddy':'cli'},Path(folder)).run('fixture','model',lambda text:None,threading.Event(),full_access=True,on_tool=lambda record:seen.set()))
                except Exception as exc:outcomes.append(exc)
            thread=threading.Thread(target=worker);thread.start()
            process.stdout.queue.put({'type':'assistant','message':{'role':'assistant','content':[{'type':'tool_use','id':'call1','name':'Read','input':{'file_path':'fixture.txt'}}]}})
            self.assertTrue(seen.wait(2),'tool record did not arrive while the process was still running')
            self.assertTrue(thread.is_alive());self.assertEqual(outcomes,[])
            process.stdout.queue.put({'type':'result','subtype':'success','result':'done','num_turns':1})
            process.stdout.queue.put(None);thread.join(timeout=2)
            self.assertEqual(outcomes[0][0],'done')

    def test_partial_text_is_not_duplicated_and_reasoning_is_never_exposed(self):
        emits=[];tools=[];progress=[]
        state=StreamState(emits.append,tools.append,progress.append,tool_record,True)
        for event in [
            {'type':'stream_event','_messageId':'m1','event':{'delta':{'type':'thinking_delta','thinking':'HIDDEN_SENTINEL'}}},
            {'type':'stream_event','_messageId':'m1','event':{'delta':{'type':'text_delta','text':'hello'}}},
            {'type':'assistant','_messageId':'m1','message':{'content':[{'type':'text','text':'hello'}]}},
            {'type':'assistant','message':{'content':[{'type':'thinking','thinking':'HIDDEN_SENTINEL'}]}},
        ]:state.consume(event)
        self.assertEqual(emits[-1],'hello')
        self.assertNotIn('HIDDEN_SENTINEL',json.dumps(emits+tools+progress)+json.dumps(state.metadata))

    def test_stream_tool_start_and_result_are_one_call_and_keep_the_name(self):
        records=[];state=StreamState(lambda text:None,records.append,None,tool_record,True)
        state.consume({'type':'stream_event','event':{'type':'content_block_start','content_block':{'type':'tool_use','id':'call','name':'Read','input':{}}}})
        state.consume({'type':'assistant','message':{'content':[{'type':'tool_use','id':'call','name':'Read','input':{'file_path':'fixture.txt'}}]}})
        state.consume({'type':'user','message':{'content':[{'type':'tool_result','tool_use_id':'call','content':'contents'}]}})
        self.assertEqual(state.tool_calls,1);self.assertEqual(records[-1]['name'],'Read');self.assertEqual(records[-1]['status'],'completed')

    def test_native_todo_plan_remains_specific(self):
        progress=[];state=StreamState(lambda text:None,None,progress.append,tool_record,True)
        state.consume({'type':'assistant','message':{'content':[{'type':'tool_use','id':'plan','name':'TodoWrite','input':{'todos':[{'content':'检查 recovery.py 持久化','status':'in_progress'},{'content':'验证重启恢复用例','status':'pending'}]}}]}})
        self.assertEqual(next(p['plan'] for p in progress if 'plan' in p)[0]['step'],'检查 recovery.py 持久化')

    def test_turn_update_receipts_are_once_and_fallback_is_not_lost(self):
        receipts=[];updates=TurnUpdates(lambda *args:receipts.append(args))
        self.assertTrue(updates.submit('first','补充范围'))
        self.assertEqual(list(updates.drain()),[('first','补充范围')])
        updates.resolve('first',True);updates.resolve('first',True)
        updates.submit('race','刚好完成');updates.close(completed=True)
        self.assertEqual([r[1] for r in receipts],['accepted','queued'])
        self.assertFalse(updates.submit('closed','x'))


if __name__=='__main__':unittest.main()
