# Configuration Guide

This guide provides detailed information on configuring the AVI Load Balancer to Kentik integration.

## Environment Variables

### Required Variables

| Variable | Description | Example | Notes |
|----------|-------------|---------|-------|
| `AVI_CONTROLLER_IP` | AVI Controller IP/FQDN | `192.168.1.100` | Must be accessible from Telegraf |
| `AVI_USERNAME` | AVI API Username | `admin` | Must have API access permissions |
| `AVI_PASSWORD` | AVI API Password | `SecurePass123!` | Store securely in production |
| `AVI_DEVICE_NAME` | Device name tag sent to Kentik | `avi-controller-01` | Applied as the `device_name` tag |
| `KENTIK_API_EMAIL` | Kentik account email | `user@company.com` | Associated with API token |
| `KENTIK_API_TOKEN` | Kentik API token | `abc123...` | Generate from Kentik dashboard |

### Optional Variables

| Variable | Description | Default | Notes |
|----------|-------------|---------|-------|
| `KENTIK_API_ENDPOINT` | Kentik API endpoint | `https://grpc.api.kentik.com/kmetrics/v202207/metrics/api/v2/write?bucket=&org=&precision=ns` | Regional endpoints available |
| `ENVIRONMENT` | Environment tag | `production` | Used for metric tagging |
| `LOCATION` | Location tag | `datacenter-1` | Used for metric tagging |
| `AVI_INSECURE_SKIP_VERIFY` | Skip TLS certificate verification for AVI API | `true` | Set to `false` for production PKI |
| `AVI_TENANT_SCOPE_MODE` | Tenant scoping mechanism | `auto` | `auto`, `header_uuid`, `header_name`, `query_uuid`, `query_name` |
| `AVI_REQUEST_TIMEOUT_SECONDS` | Per-request timeout for collector | `15` | Upper bound for each API request |
| `AVI_TOTAL_TIMEOUT_SECONDS` | Total collector runtime timeout | `50` | Prevents hanging beyond one interval |

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

Telegraf uses a single `[[inputs.exec]]` entry to run `avi-tenant-metrics.py`.
The script performs session login once (`POST /login`), discovers tenants
dynamically (`GET /api/tenant`), then polls the four analytics endpoints once
per tenant in the same run:

```toml
[[inputs.exec]]
  commands = ["python3 /etc/telegraf/avi-tenant-metrics.py"]
  timeout = "55s"
  data_format = "influx"
```

### Metric Parsing

The collector script parses `results[].series[]` from AVI responses and emits
final Influx line protocol directly. It keeps the same wide output shape as the
previous pipeline: one record per entity per collection cycle, with normalized
field names (`.` replaced by `_`, and `controller_stats.` trimmed for controller
fields).

### Global Tags

All metrics include global tags:

```toml
[global_tags]
  vendor = "VMware"
  product = "AVI_Load_Balancer"
  environment = "${ENVIRONMENT}"
  location = "${LOCATION}"
  device_name = "${AVI_DEVICE_NAME}"
  ip_address = "${AVI_CONTROLLER_IP}"
```

## Data Sent to Kentik

Metrics are delivered to Kentik as InfluxDB **line protocol** (`data_format = "influx"`).
The collector script emits a **wide format** directly: each metric name becomes
its own field, and all metrics for a single entity are merged into **one record**.
So every collection cycle produces exactly one record per entity.

### Measurements

Measurement names follow an OpenConfig-style path:

| Measurement | AVI entity | Source metric family |
|-------------|-----------|----------------------|
| `/devices/avi/controller` | Controller (cluster) | `controller_stats.*` |
| `/devices/avi/virtualservice` | Virtual services | `l4_server.*`, `l7_server.*` |
| `/devices/avi/pool` | Server pools | `l4_server.*` |
| `/devices/avi/serviceengine` | Service engines | `se_stats.*`, `se_if.*` |

### Tags (on every record)

| Tag | Source | Example |
|-----|--------|---------|
| `device_name` | `${AVI_DEVICE_NAME}` | `avi-controller-01` |
| `ip_address` | `${AVI_CONTROLLER_IP}` | `198.47.119.104` |
| `entity_uuid` | AVI series header | `virtualservice-web-app-uuid-1234` |
| `pool_uuid` | AVI series header (when present) | `pool-web-app-uuid-9876` |
| `serviceengine_uuid` | AVI series header (when present) | `serviceengine-uuid-4567` |
| `tenant_uuid` | AVI series header (when present) | `tenant-admin-uuid-0001` |
| `tenant_name` | AVI tenant API/header (when present) | `admin` |
| `environment` | `${ENVIRONMENT}` | `production` |
| `location` | `${LOCATION}` | `datacenter-east` |
| `vendor` | static | `VMware` |
| `product` | static | `AVI_Load_Balancer` |
| `host` | Telegraf collector hostname | `telegraf-01` |

### Fields per measurement

**`/devices/avi/controller`** — the `controller_stats.` prefix is stripped (the
measurement already identifies the controller). 30 fields:

- Health: `avg_cpu_usage`, `avg_mem_usage`, `avg_disk_usage`, `avg_disk_read_bytes`, `avg_disk_write_bytes`
- Inventory (avg/max): `avg_num_active_vs`, `max_num_active_vs`, `avg_num_ses`, `max_num_ses`, `avg_num_se_cores`, `max_num_se_cores`, `avg_num_service_cores`, `max_num_service_cores`, `avg_num_sockets`, `max_num_sockets`, `avg_num_backend_servers`, `max_num_backend_servers`
- Throughput/traffic: `avg_total_se_throughput`, `max_total_se_throughput`, `sum_total_se_bytes`, `sum_total_vs_bytes`, `sum_total_vs_client_bytes`, `sum_total_vs_usage`
- License usage (%): `max_num_active_vs_lic_usage`, `max_num_ses_lic_usage`, `max_num_sockets_lic_usage`, `max_num_service_cores_lic_usage`, `max_se_cores_lic_usage`, `max_se_throughput_lic_usage`, `max_be_servers_lic_usage`

**`/devices/avi/virtualservice`** (the `l4_server`/`l7_server` prefix is retained
to disambiguate L4/L7; dots become underscores):

- `l4_server_avg_complete_conns`, `l4_server_avg_new_established_conns`, `l4_server_avg_pool_complete_conns`, `l4_server_avg_pool_new_established_conns`, `l7_server_avg_complete_responses`, `l7_server_avg_client_complete_requests`

**`/devices/avi/pool`**:

- `l4_server_avg_complete_conns`, `l4_server_avg_new_established_conns`, `l4_server_avg_pool_open_conns`, `l4_server_sum_connection_errors`

**`/devices/avi/serviceengine`**:

- `se_stats_avg_cpu_usage`, `se_stats_avg_mem_usage`, `se_stats_avg_disk_usage`, `se_if_avg_bandwidth`

### Example record (line protocol)

```
/devices/avi/controller,device_name=avi-controller-01,entity_uuid=controller-uuid-1234-primary,environment=production,host=telegraf-01,ip_address=198.47.119.104,location=datacenter-east,product=AVI_Load_Balancer,vendor=VMware avg_cpu_usage=5,avg_mem_usage=75,avg_disk_usage=19 1787796840000000000
```

> Note: on a controller with no configured virtual services / pools / service
> engines, only `/devices/avi/controller` records are produced — the other three
> endpoints return no entities until workloads are deployed.

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

To collect additional metrics, update the `METRIC_IDS` lists in
`avi-tenant-metrics.py`:

Available AVI metrics include:
- `l4_server.avg_bandwidth` - Average bandwidth
- `l7_server.avg_client_data_transfer_time` - Data transfer time
- `dos_attacks.sum_dos_attacks` - DDoS attack counts
- `l7_server.sum_server_errors` - Server error counts

### Filtering Data

To collect specific virtual services or pools, add filter parameters in the
collector's request-building logic (`fetch_endpoint` in `avi-tenant-metrics.py`):

```python
params["entity_uuid"] = "specific-vs-uuid"
```

### Adjusting Time Range

Modify the collector request params (`step`) to change the aggregation window:

- `step=60` - 1-minute aggregation
- `step=300` - 5-minute aggregation (default)
- `step=3600` - 1-hour aggregation

## Performance Tuning

### High-Volume Environments

For environments with many virtual services:

1. **Increase timeouts**:
   ```bash
   AVI_REQUEST_TIMEOUT_SECONDS=20
   AVI_TOTAL_TIMEOUT_SECONDS=55
   ```

2. **Adjust batching**:
   ```toml
   metric_batch_size = 5000
   metric_buffer_limit = 50000
   ```

3. **Tenant scope mode**:
   Set `AVI_TENANT_SCOPE_MODE` to match your AVI controller version if `auto`
   does not return tenant-scoped data.

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

Test the collector directly (recommended):

```bash
AVI_CONTROLLER_IP=localhost:8443 \
AVI_USERNAME=admin \
AVI_PASSWORD=admin123 \
AVI_INSECURE_SKIP_VERIFY=true \
python3 avi-tenant-metrics.py
```

Or test AVI API connectivity manually (log in first, then reuse the session cookie):

```bash
curl -k -c cookies.txt -X POST "https://${AVI_CONTROLLER_IP}/login" \
  -H "Content-Type: application/json" \
  -d "{\"username\":\"${AVI_USERNAME}\",\"password\":\"${AVI_PASSWORD}\"}"
curl -k -b cookies.txt \
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
