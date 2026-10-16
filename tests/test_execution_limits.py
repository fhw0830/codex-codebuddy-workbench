import sys
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from backend.execution_limits import ExecutionWindow


class ExecutionLimits(unittest.TestCase):
    def test_full_access_progress_survives_old_hard_limit(self):
        clock=[0];window=ExecutionWindow(1800,True,lambda:clock[0])
        clock[0]=1799;window.activity();clock[0]=1900
        self.assertFalse(window.expired())
        clock[0]=3600;self.assertTrue(window.expired())
    def test_long_running_tool_is_not_killed_and_idle_after_completion_is_bounded(self):
        clock=[0];window=ExecutionWindow(1800,True,lambda:clock[0])
        window.tool('build','running');clock[0]=7200;self.assertFalse(window.expired())
        window.tool('build','completed');clock[0]=8999;self.assertFalse(window.expired())
        clock[0]=9000;self.assertTrue(window.expired())
    def test_discussion_keeps_its_total_limit_even_with_activity(self):
        clock=[0];window=ExecutionWindow(180,False,lambda:clock[0])
        clock[0]=179;window.activity();clock[0]=180
        self.assertTrue(window.expired())


if __name__=='__main__':unittest.main()
