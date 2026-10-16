"""Keep active coding tasks running; bound silent idle waits separately."""
import time


class ExecutionWindow:
    def __init__(self, timeout, full_access, clock=time.monotonic):
        self.timeout, self.full_access, self.clock = timeout, full_access, clock
        self.started = self.last_activity = clock()
        self.active_tools = set()
        self.paused_at=None;self.waited=0

    def pause(self):
        if self.paused_at is None:self.paused_at=self.clock()

    def resume(self):
        if self.paused_at is not None:
            self.waited+=self.clock()-self.paused_at;self.paused_at=None;self.activity()

    def activity(self):
        self.last_activity = self.clock()

    def tool(self, id, status):
        self.activity()
        if status in ('running', 'preparing', 'inProgress'):
            self.active_tools.add(id)
        else:
            self.active_tools.discard(id)

    def expired(self):
        if self.paused_at is not None:return False
        if not self.full_access:
            return self.clock() - self.started-self.waited >= self.timeout
        return not self.active_tools and self.clock() - self.last_activity >= self.timeout
