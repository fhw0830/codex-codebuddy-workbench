"""Measure plan-state transitions, rather than inventing historical durations."""
import time
from .store import now


class PlanClock:
    def __init__(self, clock=time.monotonic, wall=now):
        self.clock, self.wall = clock, wall
        self.items, self.timers = [], {}

    def update(self, plan):
        at=self.clock()
        visible={item['step'] for item in plan}
        for key,timer in self.timers.items():
            if key not in visible and timer['start'] is not None:
                timer['accumulated']+=at-timer['start']
                timer.update(start=None,finished_at=self.wall())
        for item in plan:
            key=item['step']
            timer=self.timers.setdefault(key,{'accumulated':0.0,'start':None,'started_at':None,'finished_at':None,'measured':False})
            if item['status']=='in_progress' and timer['start'] is None:
                timer.update(start=at,started_at=self.wall(),finished_at=None,measured=True)
            elif item['status']!='in_progress' and timer['start'] is not None:
                timer['accumulated']+=at-timer['start']
                timer.update(start=None,finished_at=self.wall())
        self.items=[dict(item) for item in plan]
        return self.snapshot()

    def snapshot(self, frozen=False):
        at=self.clock()
        result=[]
        for item in self.items:
            timer=self.timers[item['step']]
            elapsed=timer['accumulated']+(at-timer['start'] if timer['start'] is not None else 0)
            result.append({**item,'elapsed_s':round(elapsed,2) if timer['measured'] else None,
                'accumulated_s':round(timer['accumulated'],2),'started_at':timer['started_at'],
                'finished_at':timer['finished_at'],'timing_live':timer['start'] is not None and not frozen})
        return result
