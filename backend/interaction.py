"""Thread-safe delivery receipts for updates to an active model turn."""
import queue
import threading


class TurnUpdates:
    def __init__(self, receipt):
        self.queue = queue.Queue()
        self.receipt = receipt
        self.pending = {}
        self.lock = threading.RLock()
        self.closed = False
        self.questions = None
        self.resources = None
        self.process = None

    def submit(self, message_id, text):
        with self.lock:
            if self.closed:
                return False
            self.pending[message_id] = text
            self.queue.put((message_id, text))
            return True

    def drain(self):
        while True:
            try:
                yield self.queue.get_nowait()
            except queue.Empty:
                return

    def resolve(self, message_id, accepted, reason=''):
        with self.lock:
            if message_id not in self.pending:
                return
            self.pending.pop(message_id)
        self.receipt(message_id, 'accepted' if accepted else 'queued', reason)

    def close(self, completed=False):
        with self.lock:
            self.closed = True
            pending = list(self.pending)
            self.pending.clear()
        for message_id in pending:
            self.receipt(message_id, 'queued' if completed else 'failed', '当前回答已结束' if completed else '当前回答停止或失败，补充未确认送达')
