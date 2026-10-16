"""Exercise native event/RPC ordering without a model or robot connection."""
import io
import json
from pathlib import Path
import queue
import sys
import threading
import unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from backend.agents import Codex
from backend.interaction import TurnUpdates
from backend.resource_locks import ResourceCoordinator,ResourceSession


class ReleaseRPC(unittest.TestCase):
    def run_events(self,events):
        process=type('Process',(),{'stdin':io.StringIO(),'poll':lambda self:0})()
        session=ResourceSession(ResourceCoordinator(),'fixture',ROOT,threading.Event(),lambda row:None)
        session.request({'action':'declare','code_paths':[str(ROOT)]})
        controls=TurnUpdates(lambda *args:None);controls.resources=session
        records=[]
        def ledger(record):
            records.append(record)
            if record['type']=='commandExecution':
                if record['status']=='running':session.active_operations.add(record['id'])
                else:session.active_operations.discard(record['id'])
        def exchange(process,queue,method,params,id,cancel):
            if method=='thread/start':return {'thread':{'id':'thread'}},[]
            if method=='turn/start':return {'turn':{'id':'turn'}},events
            return {},[]
        with patch.object(Codex,'launch',return_value=(process,queue.Queue(),[])),patch.object(Codex,'exchange',side_effect=exchange),patch('backend.agents.stop_process'):
            result=Codex({},ROOT).run('fixture','model',lambda text:None,threading.Event(),full_access=True,controls=controls,on_tool=ledger)
        packets=[json.loads(line) for line in process.stdin.getvalue().splitlines()]
        return result,session,records,{p['id']:p['result'] for p in packets if 'result' in p}

    @staticmethod
    def command(method,status=None):
        item={'id':'command-1','type':'commandExecution','command':'synthetic command'}
        if status is not None:item['status']=status
        return {'method':method,'params':{'item':item}}

    @staticmethod
    def release(id,arguments=None):
        return {'id':id,'method':'item/tool/call','params':{'tool':'coordinate_resources','arguments':arguments or {'action':'release'}}}

    @staticmethod
    def finish():
        return [{'method':'item/completed','params':{'item':{'type':'agentMessage','id':'answer','text':'done','phase':'final_answer'}}},
                {'method':'turn/completed','params':{'turn':{'status':'completed'}}}]

    def test_completed_without_status_allows_release_and_final_answer(self):
        result,session,records,packets=self.run_events([self.command('item/started'),self.command('item/completed'),self.release(77)]+self.finish())
        self.assertEqual(result[0],'done');self.assertEqual(records[-1]['status'],'completed')
        self.assertEqual(session.active_operations,set());self.assertEqual(session.manager.leases,{})
        self.assertTrue(packets[77]['success'])

    def test_early_release_is_nonfatal_retains_lease_then_can_retry(self):
        result,session,records,packets=self.run_events([self.command('item/started'),self.release(77),self.command('item/completed'),self.release(78)]+self.finish())
        self.assertEqual(result[0],'done');self.assertFalse(packets[77]['success'])
        blocked=json.loads(packets[77]['contentItems'][0]['text'])
        self.assertTrue(blocked['resources_retained']);self.assertEqual(blocked['active_operation_ids'],['command-1'])
        self.assertTrue(packets[78]['success']);self.assertEqual(session.manager.leases,{})

    def test_invalid_resource_arguments_do_not_abort_the_turn(self):
        result,session,records,packets=self.run_events([self.release(77,{'action':'declare','code_paths':[]})]+self.finish())
        self.assertEqual(result[0],'done');self.assertFalse(packets[77]['success']);self.assertTrue(session.manager.leases)

if __name__=='__main__':unittest.main()
