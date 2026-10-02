"""Route asynchronous backend results to their owning request.

Only this adapter drains a backend queue. Cancelled/expired requests are forgotten,
so late results cannot be attached to a later recording.
"""

import threading


class TranscriptionRouter:
    def __init__(self, backend):
        self.backend = backend
        self._lock = threading.Lock()
        self._submit_lock = threading.Lock()
        self._submitting = False
        self._pending = set()
        self._results = {}

    def transcribe_async(self, **kwargs):
        # Backends must provide bounded/nonblocking submission. Never hold the
        # routing lock across it: Stop/cancel must remain available.
        with self._submit_lock:
            with self._lock:
                # Release completed/abandoned backend work even when a previous
                # full input queue rejected submission before any result polling.
                self._drain_results()
                self._submitting = True
            try:
                request_id = self.backend.transcribe_async(**kwargs)
                with self._lock:
                    self._pending.add(request_id)
                return request_id
            finally:
                with self._lock:
                    self._submitting = False

    def _drain_results(self):
        """Called with the routing lock held; submission IDs must be registered."""
        # Bound each poll and don't consume an immediate result before its owner
        # has registered the request ID.
        for _ in range(0 if self._submitting else 100):
            result = self.backend.get_result(timeout=0)
            if result is None:
                break
            if result.request_id in self._pending:
                self._results[result.request_id] = result

    def get_result_for(self, request_id):
        with self._lock:
            self._drain_results()
            result = self._results.pop(request_id, None)
            if result is not None:
                self._pending.discard(request_id)
            return result

    def cancel(self, request_id):
        with self._lock:
            self._pending.discard(request_id)
            self._results.pop(request_id, None)
