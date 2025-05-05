#!/usr/bin/env python3
"""
Sample Prometheus client application that implements various metrics
and pushes them to a Pushgateway running on localhost:9091
"""

import time
import json
import base64
import random
from urllib.request import (
    BaseHandler, build_opener, Request, HTTPHandler
)
from typing import Any, Callable, Optional, Sequence, Tuple, Union, List
from prometheus_client import (
    CollectorRegistry, Counter, Gauge, Histogram, Summary,
    push_to_gateway, pushadd_to_gateway, delete_from_gateway,
    push_to_proxy_gateway
)

# URL for the Pushgateway
PUSHGATEWAY_URL = 'localhost:9091'
PROXY_GATEWAY_URL = 'http://localhost:6000/push_metrics'

# Create a registry to collect metrics
registry = CollectorRegistry()

# Create various metric types
# Counter - counts something, value can only increase
request_counter = Counter(
    'sample_requests_total',
    'Total number of requests processed',
    ['method', 'endpoint'],
    registry=registry
)

# Gauge - a value that can go up and down
cpu_usage = Gauge(
    'sample_cpu_usage_percent',
    'Current CPU usage in percent',
    registry=registry
)

memory_usage = Gauge(
    'sample_memory_usage_bytes',
    'Current memory usage in bytes',
    ['instance'],
    registry=registry
)

# Histogram - tracks distribution of values
request_duration = Histogram(
    'sample_request_duration_seconds',
    'Request duration in seconds',
    ['endpoint'],
    registry=registry,
    buckets=(0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10)
)

# Summary - similar to histogram but calculates quantiles on client side
request_latency = Summary(
    'sample_request_latency_seconds',
    'Request latency in seconds',
    registry=registry
)

def simulate_requests():
    """Simulate some requests and update metrics"""
    # Increment counter with different labels
    request_counter.labels(method='GET', endpoint='/api/users').inc()
    request_counter.labels(method='POST', endpoint='/api/users').inc(2)
    request_counter.labels(method='GET', endpoint='/api/products').inc(3)
    
    # Update gauges
    cpu_percent = random.uniform(0, 100)
    cpu_usage.set(cpu_percent)
    
    memory_bytes = random.randint(100000000, 500000000)  # 100MB to 500MB
    memory_usage.labels(instance='app-server-1').set(memory_bytes)
    
    # Record histogram values
    with request_duration.labels(endpoint='/api/users').time():
        # Simulate work that takes random time
        time.sleep(random.uniform(0.05, 0.5))
    
    # Record a specific duration for another endpoint
    request_duration.labels(endpoint='/api/products').observe(
        random.uniform(0.1, 2.0)
    )
    
    # Record latency with summary
    with request_latency.time():
        time.sleep(random.uniform(0.01, 0.2))


def proxy_handler(
        url: str,
        method: str,
        timeout: Optional[float],
        headers: List[Tuple[str, str]],
        data: bytes,
) -> Callable[[], None]:
    """Default handler that implements HTTP/HTTPS connections.

    Used by the push_to_gateway functions. Can be re-used by other handlers."""

    return _make_proxy_handler(url, method, timeout, headers, data, HTTPHandler)


def _make_proxy_handler(
        url: str,
        method: str,
        timeout: Optional[float],
        headers: Sequence[Tuple[str, str]],
        data: bytes,
        base_handler: Union[BaseHandler, type],
) -> Callable[[], None]:
    """Proxy handler to forward requests to the Pushgateway"""
    def handle() -> None:
        print(f"[Proxy handler] Sending data to {url} with method {method}")
        # Encode the original binary data as base64 to safely include in JSON
        encoded_data = base64.b64encode(data).decode('utf-8')
        
        # Create a payload containing both target URL and encoded data
        payload = {
            "target_url": url,
            "method": method,
            "headers": dict(headers),  # Convert headers to a dictionary
            "data": encoded_data,
            "timeout": timeout,
        }
        
        # Convert the payload to JSON and encode as bytes
        proxy_data = json.dumps(payload).encode('utf-8')
        
        print("[Proxy handler] Proxying data through:", PROXY_GATEWAY_URL)
        print("[Proxy handler] Payload to send:", proxy_data)

        # Send the packed data to the proxy endpoint
        request = Request(PROXY_GATEWAY_URL, data=proxy_data)
        request.add_header('Content-Type', 'application/json')
        
        # Use POST when sending to the proxy
        request.get_method = lambda: "POST"
        
        resp = build_opener(base_handler).open(request, timeout=timeout)

        print(f"[Proxy handler] Response from proxy: {resp.code} {resp.msg}")
        
        # Check for errors in the response
        if resp.code >= 400:
            raise OSError(f"Error communicating with proxy: {resp.code} {resp.msg}")
    
    return handle


def push_metrics_to_gateway():
    """Push the metrics to the Pushgateway"""
    try:
        # Using push_to_gateway will replace metrics for this job
        # Any existing metrics with same job name will be replaced
        push_to_gateway(
            PUSHGATEWAY_URL,
            job='sample_python_batch_job',
            registry=registry,
            handler=proxy_handler
        )
        print(f"Successfully pushed metrics to {PUSHGATEWAY_URL}")
    except Exception as e:
        print(f"Failed to push metrics: {e}")

def cleanup_metrics():
    """Delete metrics from the Pushgateway"""
    try:
        delete_from_gateway(
            PUSHGATEWAY_URL,
            job='sample_python_batch_job'
        )
        print(f"Successfully deleted metrics from {PUSHGATEWAY_URL}")
    except Exception as e:
        print(f"Failed to delete metrics: {e}")

def main():
    """Main function that simulates a batch job with metrics"""
    print("Starting sample Prometheus client application...")
    
    # Optionally cleanup previous metrics
    # cleanup_metrics()
    
    # Create a job_last_success_time metric to track when job was last successful
    job_last_success = Gauge(
        'sample_job_last_success_unixtime', 
        'Last time the batch job successfully finished',
        registry=registry
    )
    
    # Create a job_duration metric to track how long the job took
    job_duration = Gauge(
        'sample_job_duration_seconds',
        'Duration of the batch job in seconds',
        registry=registry
    )
    
    # Start timing the job
    start_time = time.time()
    
    try:
        # Simulate the batch job
        print("Running batch job and collecting metrics...")
        for i in range(1):
            print(f"Iteration {i+1}/5...")
            simulate_requests()
            time.sleep(1)  # Wait a second between iterations
        
        # Record job success time
        job_last_success.set_to_current_time()
        
        # Record job duration
        job_duration.set(time.time() - start_time)
        
        # Push all metrics to the Pushgateway
        push_metrics_to_gateway()
        
        print("Batch job completed successfully!")
    except Exception as e:
        print(f"Batch job failed: {e}")
        # Even on failure, push what we have to the gateway
        # This allows monitoring systems to detect failures
        push_metrics_to_gateway()

if __name__ == "__main__":
    main()