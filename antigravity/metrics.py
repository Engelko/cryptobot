import time
from collections import defaultdict
from threading import Lock

class MetricsCollector:
    def __init__(self):
        self._lock = Lock()
        self._counters = defaultdict(int)
        self._timings = defaultdict(list)
        self._gauges = {}
    
    def increment(self, name: str, value: int = 1, tags: dict = None):
        with self._lock:
            key = self._make_key(name, tags)
            self._counters[key] += value
    
    def timing(self, name: str, value: float, tags: dict = None):
        with self._lock:
            key = self._make_key(name, tags)
            self._timings[key].append(value)
            if len(self._timings[key]) > 1000:
                self._timings[key] = self._timings[key][-1000:]
    
    def gauge(self, name: str, value: float, tags: dict = None):
        with self._lock:
            key = self._make_key(name, tags)
            self._gauges[key] = value
    
    def get_metrics(self) -> dict:
        with self._lock:
            return {
                'counters': dict(self._counters),
                'timings': {k: {
                    'count': len(v),
                    'avg': sum(v) / len(v) if v else 0,
                    'p95': sorted(v)[int(len(v) * 0.95)] if v else 0
                } for k, v in self._timings.items()},
                'gauges': dict(self._gauges)
            }
    
    def _make_key(self, name: str, tags: dict) -> str:
        if tags:
            tag_str = ','.join(f"{k}={v}" for k, v in sorted(tags.items()))
            return f"{name}:{tag_str}"
        return name

metrics = MetricsCollector()
