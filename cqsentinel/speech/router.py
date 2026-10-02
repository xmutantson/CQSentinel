"""Route asynchronous backend results to their owning request.

Only this adapter drains a backend queue. Cancelled/expired requests are forgotten,
so late results cannot be attached to a later recording.
"""

import threading


class TranscriptionRouter:
    def __init__(self, backend):
        self.backend = backend
        self._lock = threading.Lock()
        self._pending = set()
        self._results = {}

    def transcribe_async(self, **kwargs):
        with self._lock:
            request_id = self.backend.transcribe_async(**kwargs)
            self._pending.add(request_id)
            return request_id

    def get_result_for(self, request_id):
        with self._lock:
            # Bound each poll so a busy backend cannot monopolize its caller.
            for _ in range(100):
                result = self.backend.get_result(timeout=0)
                if result is None:
                    break
                if result.request_id in self._pending:
                    self._results[result.request_id] = result
            result = self._results.pop(request_id, None)
            if result is not None:
                self._pending.discard(request_id)
            return result

    def cancel(self, request_id):
        with self._lock:
            self._pending.discard(request_id)
            self._results.pop(request_id, None)
