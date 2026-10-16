import json,tempfile,unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from backend.codebuddy_stream import StreamState,reported_credits

class AutomaticCredit(unittest.TestCase):
 def test_zero_receipt_is_preserved_and_stream_replay_not_added(self):
  updates=[]
  state=StreamState(lambda _:None,None,updates.append,lambda a,b:a,True)
  event={'type':'system','_requestId':'mine','providerData':{'traceId':'call','rawUsage':{'credit':0}}}
  state.consume(event);state.consume(event)
  self.assertEqual(state.credits,[0])
  self.assertEqual([u['credit'] for u in updates if 'credit' in u],[0])

 def test_backend_zero_receipt_matches_pid_and_request(self):
  with tempfile.TemporaryDirectory() as folder:
   home=Path(folder);logs=home/'.codebuddy/logs'/datetime.now().strftime('%Y-%m-%d');logs.mkdir(parents=True)
   def line(pid,request,credit):return f'[pid={pid}] [SessionManager][credit] Credit received: rootRequestId={request}, source=raw_model_stream_event, credit={credit}'
   mine=line(5,'mine',0)
   (logs/'fixture__billing.log').write_text('\n'.join([mine,mine,line(6,'mine',800),line(5,'other',900)]),encoding='utf-8')
   with patch('backend.codebuddy_stream.Path.home',return_value=home):
    self.assertEqual(reported_credits(5,Path('fixture'),{'mine'}),[0.0])
    self.assertEqual(reported_credits(9,Path('fixture'),{'mine'}),[])

if __name__=='__main__':unittest.main()
