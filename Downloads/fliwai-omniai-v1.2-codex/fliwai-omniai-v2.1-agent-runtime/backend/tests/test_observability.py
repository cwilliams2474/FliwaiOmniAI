from app.observability import RequestMetrics


def test_request_metrics_normalizes_ids_and_counts_errors():
    metrics = RequestMetrics()
    metrics.observe('GET', '/tickets/123', 200, 0.1)
    metrics.observe('POST', '/tickets/987', 503, 0.3)
    snapshot = metrics.snapshot()
    assert snapshot['requests_total'] == 2
    assert snapshot['errors_total'] == 1
    assert snapshot['by_route']['/tickets/:id'] == 2
    assert snapshot['by_status']['503'] == 1
    assert snapshot['average_latency_ms'] == 200.0


def test_prometheus_output_contains_core_metrics():
    metrics = RequestMetrics()
    metrics.observe('GET', '/health/live', 200, 0.01)
    text = metrics.prometheus()
    assert 'omniai_http_requests_total 1' in text
    assert 'omniai_http_responses_total{status="200"} 1' in text
