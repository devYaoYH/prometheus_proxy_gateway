# Proxying Prometheus metrics to Push Gateway

```
Desktop Application --> Proxy Server --> Prometheus Pushgateway <-- Prometheus Metrics Server
```

## Why?

Client logs can be noisy and direct access to the gateway server may not be available from the client-side (due to e.g. security authorization requirements).

Adding a proxy server layer allows us to perform the following:
1. Guard against malformed traffic requests
2. Perform error checking and validation on metrics

## Objective

**Allow client applications to perform metric pushes into Prometheus Gateway server via a proxy server that we own.**

## Design

### Custom request handler

### What gets sent as metrics?

Example trace in Prometheus metrics format

```
# HELP sample_requests_total Total number of requests processed
# TYPE sample_requests_total counter
sample_requests_total{endpoint="/api/users",method="GET"} 1.0
sample_requests_total{endpoint="/api/users",method="POST"} 2.0
sample_requests_total{endpoint="/api/products",method="GET"} 3.0
# HELP sample_requests_created Total number of requests processed
# TYPE sample_requests_created gauge
sample_requests_created{endpoint="/api/users",method="GET"} 1.746471551877036e+09
sample_requests_created{endpoint="/api/users",method="POST"} 1.746471551877043e+09
sample_requests_created{endpoint="/api/products",method="GET"} 1.746471551877047e+09
# HELP sample_cpu_usage_percent Current CPU usage in percent
# TYPE sample_cpu_usage_percent gauge
sample_cpu_usage_percent 39.42813246935317
# HELP sample_memory_usage_bytes Current memory usage in bytes
# TYPE sample_memory_usage_bytes gauge
sample_memory_usage_bytes{instance="app-server-1"} 2.90548674e+08
# HELP sample_request_duration_seconds Request duration in seconds
# TYPE sample_request_duration_seconds histogram
sample_request_duration_seconds_bucket{endpoint="/api/users",le="0.05"} 0.0
sample_request_duration_seconds_bucket{endpoint="/api/users",le="0.1"} 0.0
sample_request_duration_seconds_bucket{endpoint="/api/users",le="0.25"} 1.0
sample_request_duration_seconds_bucket{endpoint="/api/users",le="0.5"} 1.0
sample_request_duration_seconds_bucket{endpoint="/api/users",le="1.0"} 1.0
sample_request_duration_seconds_bucket{endpoint="/api/users",le="2.5"} 1.0
sample_request_duration_seconds_bucket{endpoint="/api/users",le="5.0"} 1.0
sample_request_duration_seconds_bucket{endpoint="/api/users",le="10.0"} 1.0
sample_request_duration_seconds_bucket{endpoint="/api/users",le="+Inf"} 1.0
sample_request_duration_seconds_count{endpoint="/api/users"} 1.0
sample_request_duration_seconds_sum{endpoint="/api/users"} 0.1477690413594246
sample_request_duration_seconds_bucket{endpoint="/api/products",le="0.05"} 0.0
sample_request_duration_seconds_bucket{endpoint="/api/products",le="0.1"} 0.0
sample_request_duration_seconds_bucket{endpoint="/api/products",le="0.25"} 0.0
sample_request_duration_seconds_bucket{endpoint="/api/products",le="0.5"} 0.0
sample_request_duration_seconds_bucket{endpoint="/api/products",le="1.0"} 1.0
sample_request_duration_seconds_bucket{endpoint="/api/products",le="2.5"} 1.0
sample_request_duration_seconds_bucket{endpoint="/api/products",le="5.0"} 1.0
sample_request_duration_seconds_bucket{endpoint="/api/products",le="10.0"} 1.0
sample_request_duration_seconds_bucket{endpoint="/api/products",le="+Inf"} 1.0
sample_request_duration_seconds_count{endpoint="/api/products"} 1.0
sample_request_duration_seconds_sum{endpoint="/api/products"} 0.6612882476396624
# HELP sample_request_duration_seconds_created Request duration in seconds
# TYPE sample_request_duration_seconds_created gauge
sample_request_duration_seconds_created{endpoint="/api/users"} 1.7464715518770628e+09
sample_request_duration_seconds_created{endpoint="/api/products"} 1.746471552025109e+09
# HELP sample_request_latency_seconds Request latency in seconds
# TYPE sample_request_latency_seconds summary
sample_request_latency_seconds_count 1.0
sample_request_latency_seconds_sum 0.17788633378222585
# HELP sample_request_latency_seconds_created Request latency in seconds
# TYPE sample_request_latency_seconds_created gauge
sample_request_latency_seconds_created 1.746471551876989e+09
# HELP sample_job_last_success_unixtime Last time the batch job successfully finished
# TYPE sample_job_last_success_unixtime gauge
sample_job_last_success_unixtime 1.7464715532050078e+09
# HELP sample_job_duration_seconds Duration of the batch job in seconds
# TYPE sample_job_duration_seconds gauge
sample_job_duration_seconds 1.3280010223388672
```

## Implementation

### Authorization guardrails

### Error checking & Metrics Validation
