import unittest,json,tempfile
from unittest.mock import patch
from pathlib import Path
from datetime import datetime
from backend.token_usage import Usage,normalize
from backend.codebuddy_stream import StreamState

class TokenUsageTests(unittest.TestCase):
    def test_native_cli_input_includes_cache(self):
        raw={'input_tokens':3414,'output_tokens':35,'cache_creation_input_tokens':3414,'cache_read_input_tokens':0}
        self.assertEqual(normalize(raw)['total'],3449)
        self.assertEqual(normalize({'inputTokens':0,'outputTokens':35,'cacheCreationInputTokens':3414})['total'],3449)

    def test_snapshots_deduplicate_and_placeholder_does_not_erase(self):
        u=Usage()
        for n in [10,20,20]:u.add('call1',{'prompt_tokens':100,'completion_tokens':n})
        u.add('call1',{'input_tokens':0,'output_tokens':0})
        u.add('call2',{'prompt_tokens':50,'completion_tokens':5})
        self.assertEqual(u.summary(2)['total'],175)
        self.assertFalse(u.summary(2)['partial'])

    def test_final_is_aggregate_not_added_to_calls(self):
        u=Usage();u.add('one',{'input_tokens':100,'output_tokens':20})
        u.event({'type':'result','usage':{'input_tokens':150,'output_tokens':25,'cache_read_input_tokens':80,'cache_creation_input_tokens':70}})
        s=u.summary(2)
        self.assertEqual(s['total'],175);self.assertEqual(s['cache_read'],80)
        self.assertEqual(s['scope'],'result');self.assertFalse(s['partial'])

    def test_unknown_zero_invalid_and_partial(self):
        u=Usage();self.assertIsNone(u.summary())
        self.assertEqual(normalize({'input_tokens':-1,'output_tokens':True}),{})
        u.add('one',{'prompt_tokens':0,'completion_tokens':0})
        self.assertEqual(u.summary(2)['total'],0);self.assertTrue(u.summary(2)['partial'])
        self.assertNotIn('reasoning',u.summary())

    def test_partial_cache_bucket_cannot_create_false_cache_hit_rate(self):
        u=Usage();u.add('a',{'prompt_tokens':100,'completion_tokens':10,'cached_tokens':90})
        u.add('b',{'prompt_tokens':100,'completion_tokens':10})
        summary=u.summary(2)
        self.assertEqual(summary['total'],220)
        self.assertNotIn('cache_read',summary)

    def test_request_identity_not_root_id_and_alias_merge(self):
        u=Usage()
        def ev(msg,model):return {'type':'assistant','_requestId':'shared-root','_messageId':msg,'_meta':{'codebuddy.ai/modelRequestId':model},'message':{'usage':{'input_tokens':10,'output_tokens':2}}}
        u.add('m1',{'input_tokens':9,'output_tokens':1})
        u.event(ev('a','m1'));u.event(ev('b','m2'));u.event(ev('b','m2'))
        self.assertEqual(u.summary(2)['total'],24)
        self.assertEqual(u.summary(2)['reported_requests'],2)
        u.event({**ev('child','m3'),'parent_tool_use_id':'subagent'})
        self.assertEqual(u.summary(2)['total'],24)

    def test_stream_reports_usage_before_model_error(self):
        updates=[];s=StreamState(lambda _:None,None,updates.append,lambda a,b:a,True)
        with self.assertRaises(RuntimeError):s.consume({'type':'result','subtype':'error','is_error':True,'usage':{'input_tokens':12,'output_tokens':3}})
        self.assertEqual(updates[-1]['token_usage']['total'],15)

    def test_receipts_strict_pid_request_and_message_dedup(self):
        with tempfile.TemporaryDirectory() as folder:
            home=Path(folder);logs=home/'.codebuddy/logs'/datetime.now().strftime('%Y-%m-%d');logs.mkdir(parents=True)
            def line(pid,request,msg,n):return f'[pid={pid}] qua.end: '+json.dumps({'conversation_request_id':request,'message_id':msg,'prompt_tokens':str(n),'completion_tokens':'2','total_tokens':str(n+2)})
            (logs/'fixture__test.log').write_text('\n'.join([line(5,'mine','a',10),line(5,'mine','a',10),line(6,'mine','b',900),line(5,'other','c',800),line(5,'mine','d',20)]),encoding='utf-8')
            u=Usage()
            with patch('backend.token_usage.Path.home',return_value=home):u.receipts(5,Path('fixture'),{'mine'})
            self.assertEqual(u.summary(2)['total'],34)
            self.assertEqual(u.summary(2)['reported_requests'],2)

if __name__=='__main__':unittest.main()
