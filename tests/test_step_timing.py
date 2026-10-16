import sys
import unittest
import tempfile
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from backend.step_timing import PlanClock
from backend.store import Store


class StepTiming(unittest.TestCase):
    def test_times_each_actual_step_and_never_invents_unseen_history(self):
        at=[0];timer=PlanClock(lambda:at[0],lambda:'fixture-wall')
        rows=timer.update([{'step':'读取文件','status':'in_progress'},{'step':'测试','status':'pending'}])
        self.assertEqual(rows[0]['elapsed_s'],0);self.assertIsNone(rows[1]['elapsed_s'])
        at[0]=9.5;rows=timer.update([{'step':'读取文件','status':'completed'},{'step':'测试','status':'in_progress'}])
        self.assertEqual(rows[0]['elapsed_s'],9.5)
        at[0]=14;rows=timer.snapshot(frozen=True)
        self.assertEqual(rows[1]['elapsed_s'],4.5);self.assertFalse(rows[1]['timing_live'])
        self.assertEqual(rows[1]['status'],'in_progress')
    def test_already_completed_step_has_no_fabricated_zero_seconds(self):
        rows=PlanClock().update([{'step':'旧完成项','status':'completed'}])
        self.assertIsNone(rows[0]['elapsed_s'])
    def test_reentering_a_step_accumulates_only_active_time(self):
        at=[0];timer=PlanClock(lambda:at[0],lambda:'fixture-wall')
        timer.update([{'step':'复核','status':'in_progress'}]);at[0]=3
        timer.update([{'step':'复核','status':'pending'}]);at[0]=10
        timer.update([{'step':'复核','status':'in_progress'}]);at[0]=14
        self.assertEqual(timer.snapshot()[0]['elapsed_s'],7)
    def test_removed_step_stops_its_timer(self):
        at=[0];timer=PlanClock(lambda:at[0],lambda:'fixture-wall')
        timer.update([{'step':'已替换步骤','status':'in_progress'}]);at[0]=3
        timer.update([]);at[0]=100
        rows=timer.update([{'step':'已替换步骤','status':'completed'}])
        self.assertEqual(rows[0]['elapsed_s'],3)
    def test_restart_does_not_keep_question_timer_running_or_fabricate_duration(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'fixture.sqlite3';store=Store(path)
            conv=store.create_conversation();job,_=store.create_job(conv['id'],'codex',1,'restart-timing','fixture',{})
            store.update_job(job['id'],'running')
            store.message(conv['id'],'user','user','fixture','completed',{'job_id':job['id'],'delivery':{'state':'started'},'timing':{'started_at':'fixture','elapsed_s':None,'wait_s':0}})
            store.db.close();store=Store(path)
            meta=json.loads(store.rows('SELECT meta FROM messages')[-1]['meta'])
            self.assertEqual(meta['delivery']['state'],'interrupted')
            self.assertEqual(meta['timing']['status'],'interrupted')
            self.assertIsNone(meta['timing']['elapsed_s']);store.db.close()


if __name__=='__main__':unittest.main()
