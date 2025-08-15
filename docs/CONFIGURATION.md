# Configuration Guide

This guide provides detailed information on configuring the AVI Load Balancer to Kentik integration.

## Environment Variables

### Required Variables

| Variable | Description | Example | Notes |
|----------|-------------|---------|-------|
| `AVI_CONTROLLER_IP` | AVI Controller IP/FQDN | `192.168.1.100` | Must be accessible from Telegraf |
| `AVI_USERNAME` | AVI API Username | `admin` | Must have API access permissions |
| `AVI_PASSWORD` | AVI API Password | `SecurePass123!` | Store securely in production |
| `KENTIK_API_EMAIL` | Kentik account email | `user@company.com` | Associated with API token |
| `KENTIK_API_TOKEN` | Kentik API token | `abc123...` | Generate from Kentik dashboard |

### Optional Variables

| Variable | Description | Default | Notes |
|----------|-------------|---------|-------|
| `KENTIK_API_ENDPOINT` | Kentik API endpoint | `https://api.kentik.com/api/v5/write/influx` | Regional endpoints available |
| `ENVIRONMENT` | Environment tag | `production` | Used for metric tagging |
| `LOCATION` | Location tag | `datacenter-1` | Used for metric tagging |

## Telegraf Configuration

### Collection Settings

```toml
[agent]
  interval = "60s"              # How often to collect metrics
  metric_batch_size = 1000      # Batch size for outputs  
  metric_buffer_limit = 10000   # Buffer size
  flush_interval = "10s"        # How often to send to outputs
```

### AVI API Configuration

Each AVI endpoint is configured as an HTTP input:

```toml
[[inputs.http]]
  name_override = "avi_virtualservice_metrics"
  urls = ["https://${AVI_CONTROLLER_IP}/api/analytics/metrics/virtualservice?..."]
  method = "GET"
  timeout = "30s"
  username = "${AVI_USERNAME}"
  password = "${AVI_PASSWORD}"
  insecure_skip_verify = true  # Set to false for production with proper certs
  data_format = "json_v2"
```

### Metric Parsing

JSON response parsing is configured using `json_v2` format:

```toml
[[inputs.http.json_v2]]
  measurement_name = "avi_virtualservice"
  
  # Extract tags from JSON
  [[inputs.http.json_v2.tag]]
    path = "series.#.tags.virtualservice_name"
    type = "string"  
    rename = "vs_name"
  
  # Extract metrics as fields
  [[inputs.http.json_v2.field]]
    path = "series.#.data.#.value"
    type = "float"
    rename = "connections_avg_complete"
```

### Global Tags

All metrics include global tags:

```toml
[global_tags]
  vendor = "VMware"
  product = "AVI_Load_Balancer"
  environment = "${ENVIRONMENT}"
  location = "${LOCATION}"
```

## TLS Configuration

### Development/Testing

For testing with self-signed certificates:

```toml
insecure_skip_verify = true
```

### Production

For production deployments:

```toml
tls_ca = "/path/to/ca.pem"
tls_cert = "/path/to/cert.pem"  
tls_key = "/path/to/key.pem"
insecure_skip_verify = false
```

## Kentik Output Configuration

```toml
[[outputs.http]]
  url = "${KENTIK_API_ENDPOINT}"
  data_format = "influx"
  method = "POST"
  timeout = "30s"
  
  [outputs.http.headers]
    X-CH-Auth-Email = "${KENTIK_API_EMAIL}"
    X-CH-Auth-API-Token = "${KENTIK_API_TOKEN}"  
    Content-Type = "application/influx"
```

## Customizing Metrics

### Adding New Metrics

To collect additional metrics, modify the `metric_id` parameter in the API URLs:

Available AVI metrics include:
- `l4_server.avg_bandwidth` - Average bandwidth
- `l7_server.avg_client_data_transfer_time` - Data transfer time
- `dos_attacks.sum_dos_attacks` - DDoS attack counts
- `l7_server.sum_server_errors` - Server error counts

### Filtering Data

To collect specific virtual services or pools, add filters to the API URL:

```toml
urls = ["https://${AVI_CONTROLLER_IP}/api/analytics/metrics/virtualservice?metric_id=...&entity_uuid=specific-vs-uuid"]
```

### Adjusting Time Range

Modify the `step` parameter to change the aggregation window:

- `step=60` - 1-minute aggregation
- `step=300` - 5-minute aggregation (default)
- `step=3600` - 1-hour aggregation

## Performance Tuning

### High-Volume Environments

For environments with many virtual services:

1. **Increase timeouts**:
   ```toml
   timeout = "60s"
   ```

2. **Adjust batching**:
   ```toml
   metric_batch_size = 5000
   metric_buffer_limit = 50000
   ```

3. **Parallel collection**:
   Configure separate inputs for different metric types

### Resource Optimization

Monitor Telegraf resource usage and adjust:

- Memory: Increase if seeing buffer overflows
- CPU: Scale horizontally if CPU becomes bottleneck
- Network: Ensure sufficient bandwidth to AVI and Kentik

## Validation

### Configuration Validation

Test configuration syntax:

```bash
telegraf --config telegraf.conf --test
```

### Connectivity Testing

Test AVI API connectivity:

```bash
curl -u "${AVI_USERNAME}:${AVI_PASSWORD}" \
  "https://${AVI_CONTROLLER_IP}/api/analytics/metrics/virtualservice"
```

### Kentik API Testing

Test Kentik endpoint:

```bash
curl -X POST "${KENTIK_API_ENDPOINT}" \
  -H "X-CH-Auth-Email: ${KENTIK_API_EMAIL}" \
  -H "X-CH-Auth-API-Token: ${KENTIK_API_TOKEN}" \
  -H "Content-Type: application/influx" \
  --data-binary "test_metric value=1"
```
