import io
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from backend.agents import CodeBuddy,tool_record

class Process:
    def __init__(self,events):
        self.stdin=io.StringIO();self.stdout=io.StringIO(json.dumps(events));self.stderr=io.StringIO()
    def poll(self):return 0

class ToolProtocol(unittest.TestCase):
    def events(self):
        return [
            {'type':'reasoning','content':'HIDDEN_REASONING_SENTINEL','providerData':{'traceId':'request1','rawUsage':{'credit':.1}}},
            {'type':'function_call','callId':'call1','name':'Read','arguments':'{"file_path":"fixture.txt"}',
                'providerData':{'traceId':'request1','rawUsage':{'credit':.1}}},
            {'type':'function_call_result','callId':'call1','name':'Read','status':'completed','output':{'type':'text','text':'fixture contents'}},
            {'type':'message','role':'assistant','content':[{'type':'output_text','text':'done'}],
                'providerData':{'traceId':'request2','rawUsage':{'credit':.2}}},
            {'type':'result','subtype':'success','result':'done','is_error':False,'num_turns':2}
        ]
    def test_native_function_call_records_are_linked_and_credit_deduplicated(self):
        records=[]
        with tempfile.TemporaryDirectory() as folder,patch('backend.agents.spawn',return_value=Process(self.events())):
            result,meta=CodeBuddy({'node':'node','codebuddy':'cbc'},Path(folder)).run('fixture','model',lambda text:None,threading.Event(),full_access=True,on_tool=records.append)
        self.assertEqual(result,'done');self.assertEqual(meta['tool_calls'],1)
        self.assertEqual(records[0]['id'],records[1]['id']);self.assertEqual(records[1]['output'],'fixture contents')
        self.assertAlmostEqual(meta['credit'],.3);self.assertFalse(meta['credit_is_partial'])
        self.assertNotIn('HIDDEN_REASONING_SENTINEL',json.dumps(meta)+json.dumps(records))
    def test_discussion_still_rejects_tools(self):
        with tempfile.TemporaryDirectory() as folder,patch('backend.agents.spawn',return_value=Process(self.events())):
            with self.assertRaises(RuntimeError):CodeBuddy({'node':'node','codebuddy':'cbc'},Path(folder)).run('fixture','model',lambda text:None,threading.Event())
    def test_tool_input_and_output_are_readable_and_redacted(self):
        record=tool_record({'type':'function_call','callId':'same','name':'Read','arguments':'{"file_path":"fixture.txt"}',
            'output':{'type':'text','text':'apiKey=VALUEVERYSECRET'}})
        self.assertEqual(record['file_path'],'fixture.txt');self.assertNotIn('VALUEVERYSECRET',record['output'])

if __name__=='__main__':unittest.main()
