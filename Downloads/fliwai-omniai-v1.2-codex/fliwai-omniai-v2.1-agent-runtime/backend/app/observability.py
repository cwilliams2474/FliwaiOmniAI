import time
from collections import Counter
from dataclasses import dataclass, field
from threading import Lock


@dataclass
class RequestMetrics:
    started_at: float = field(default_factory=time.time)
    requests_total: int = 0
    errors_total: int = 0
    total_latency_seconds: float = 0.0
    by_method: Counter = field(default_factory=Counter)
    by_status: Counter = field(default_factory=Counter)
    by_route: Counter = field(default_factory=Counter)
    lock: Lock = field(default_factory=Lock)

    def observe(self, method: str, path: str, status_code: int, latency_seconds: float) -> None:
        route = self._normalize_path(path)
        with self.lock:
            self.requests_total += 1
            self.total_latency_seconds += max(0.0, latency_seconds)
            self.by_method[method.upper()] += 1
            self.by_status[str(status_code)] += 1
            self.by_route[route] += 1
            if status_code >= 500:
                self.errors_total += 1

    @staticmethod
    def _normalize_path(path: str) -> str:
        parts = []
        for part in path.strip('/').split('/'):
            parts.append(':id' if part.isdigit() else part)
        return '/' + '/'.join(parts) if parts else '/'

    def snapshot(self) -> dict:
        with self.lock:
            average_ms = (self.total_latency_seconds / self.requests_total * 1000) if self.requests_total else 0.0
            return {
                'uptime_seconds': int(time.time() - self.started_at),
                'requests_total': self.requests_total,
                'errors_total': self.errors_total,
                'average_latency_ms': round(average_ms, 2),
                'by_method': dict(self.by_method),
                'by_status': dict(self.by_status),
                'by_route': dict(self.by_route),
            }

    def prometheus(self) -> str:
        snapshot = self.snapshot()
        lines = [
            '# HELP omniai_uptime_seconds Process uptime in seconds.',
            '# TYPE omniai_uptime_seconds gauge',
            f"omniai_uptime_seconds {snapshot['uptime_seconds']}",
            '# HELP omniai_http_requests_total HTTP requests processed.',
            '# TYPE omniai_http_requests_total counter',
            f"omniai_http_requests_total {snapshot['requests_total']}",
            '# HELP omniai_http_errors_total HTTP 5xx responses.',
            '# TYPE omniai_http_errors_total counter',
            f"omniai_http_errors_total {snapshot['errors_total']}",
            '# HELP omniai_http_average_latency_milliseconds Average request latency.',
            '# TYPE omniai_http_average_latency_milliseconds gauge',
            f"omniai_http_average_latency_milliseconds {snapshot['average_latency_ms']}",
        ]
        for status, count in sorted(snapshot['by_status'].items()):
            lines.append(f'omniai_http_responses_total{{status="{status}"}} {count}')
        for method, count in sorted(snapshot['by_method'].items()):
            lines.append(f'omniai_http_methods_total{{method="{method}"}} {count}')
        return '\n'.join(lines) + '\n'


request_metrics = RequestMetrics()
