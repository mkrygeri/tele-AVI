# AVI Load Balancer to Kentik NMS Integration

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Docker](https://img.shields.io/badge/docker-%230db7ed.svg?style=flat&logo=docker&logoColor=white)](https://www.docker.com/)
[![Telegraf](https://img.shields.io/badge/telegraf-1.29+-blue.svg)](https://www.influxdata.com/time-series-platform/telegraf/)

A comprehensive Telegraf configuration for collecting metrics from VMware AVI Load Balancer (NSX Advanced Load Balancer) and sending them to Kentik NMS for network observability and analytics.

## 🚀 Features

- **Complete AVI Metrics Collection**: Virtual Services, Pools, Service Engines, and Controller metrics
- **Kentik NMS Integration**: Direct data pipeline to Kentik for network observability  
- **Production Ready**: Comprehensive configuration with proper tagging and error handling
- **Mock Testing Environment**: Full testing infrastructure for development and validation
- **Docker Support**: Containerized deployment with Docker Compose
- **Security**: TLS support and authentication handling

## 📊 Metrics Collected

### Virtual Services
- L4/L7 connection statistics
- Request/response metrics  
- Pool connection statistics

### Pools
- Connection statistics (complete, new, open)
- Connection error counts
- Pool health metrics

### Service Engines
- CPU, Memory, Disk utilization
- Network bandwidth metrics
- Performance statistics

### Controller
- Cluster health metrics
- Resource utilization  
- System statistics

## 🏗️ Architecture

```
AVI Load Balancer → Telegraf → Kentik NMS
     ↑                ↑           ↑
   REST API      JSON Parser  HTTP Output
```

## 🚀 Quick Start

### Prerequisites

- Docker and Docker Compose (or [OrbStack](https://orbstack.dev/) as alternative)
- AVI Load Balancer with API access
- Kentik NMS account and API credentials

### 1. Clone Repository

```bash
git clone https://github.com/mkrygeri/tele-AVI.git
cd tele-AVI
```

### 2. Configure Environment

Copy the example environment file and configure your settings:

```bash
cp .env.example .env
```

Edit `.env` with your AVI and Kentik credentials:

```bash
# AVI Load Balancer Configuration
AVI_CONTROLLER_IP=your-avi-controller.example.com
AVI_USERNAME=your-avi-username  
AVI_PASSWORD=your-avi-password
AVI_DEVICE_NAME=avi-controller-01

# Kentik NMS Configuration
KENTIK_API_ENDPOINT="https://grpc.api.kentik.com/kmetrics/v202207/metrics/api/v2/write?bucket=&org=&precision=ns"
KENTIK_API_EMAIL=your-email@example.com
KENTIK_API_TOKEN=your-kentik-api-token

# Environment Configuration
ENVIRONMENT=production
LOCATION=datacenter-1
```

### 3. Deploy

For production deployment:

```bash
make deploy
```

For testing with mock AVI server:

```bash
make dev-start
```

### 4. Validate

```bash
make validate
make status
make logs
```

## 🧪 Testing

This repository includes a complete mock testing environment:

### Quick Test

```bash
# Start mock environment and run tests
make test-all

# Or step by step
make mock-start  # Start mock AVI server
make mock-test   # Test API endpoints  
make logs-test   # View metrics collection
make mock-stop   # Clean up
```

### Mock Server Features

- **Realistic Data**: Time-series metrics with variance
- **Authentication**: AVI session login (`POST /login` → cookie); HTTP Basic Auth accepted as a fallback
- **HTTPS Support**: Self-signed certificates for testing
- **Full API Coverage**: All 4 AVI metric endpoints

## 📁 Repository Structure

```
tele-AVI/
├── README.md              # This file
├── telegraf.conf          # Main Telegraf configuration  
├── docker-compose.yml     # Production Docker setup
├── mock-avi-server.py     # Mock AVI Load Balancer API
├── Makefile              # Development commands
├── docs/                 # Detailed documentation
│   ├── CONFIGURATION.md  # Configuration guide
│   ├── DEPLOYMENT.md     # Production deployment  
│   └── TROUBLESHOOTING.md # Common issues
└── examples/             # Example configurations
```

## ⚙️ Configuration

### Environment Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `AVI_CONTROLLER_IP` | AVI Controller IP/FQDN | `192.168.1.100` |
| `AVI_USERNAME` | AVI API Username | `admin` |
| `AVI_PASSWORD` | AVI API Password | `SecurePass123!` |
| `AVI_DEVICE_NAME` | Device name tag sent to Kentik | `avi-controller-01` |
| `KENTIK_API_ENDPOINT` | Kentik API Endpoint | `https://grpc.api.kentik.com/kmetrics/v202207/metrics/api/v2/write?bucket=&org=&precision=ns` |
| `KENTIK_API_EMAIL` | Kentik Account Email | `user@company.com` |
| `KENTIK_API_TOKEN` | Kentik API Token | `your-api-token` |
| `ENVIRONMENT` | Deployment Environment | `production` |
| `LOCATION` | Physical Location | `us-west-1` |

### TLS Configuration

For production deployments with proper TLS certificates:

```toml
# Uncomment and configure in telegraf.conf
tls_ca = "/path/to/ca.pem"
tls_cert = "/path/to/cert.pem"
tls_key = "/path/to/key.pem"
insecure_skip_verify = false
```

## 🔍 Monitoring

### Metrics Output Format

Metrics are sent in InfluxDB Line Protocol. The pipeline produces a **wide-format**
record per entity: each metric name becomes its own field, all merged into one
record. Measurements use OpenConfig-style paths (`/devices/avi/<entity>`), and
field keys are dot-free (`.` → `_`):

```
/devices/avi/pool,device_name=avi-controller-01,entity_uuid=pool-web-app-uuid-1234,environment=production,ip_address=198.47.119.104,location=datacenter-1,product=AVI_Load_Balancer,vendor=VMware l4_server_avg_complete_conns=150.5,l4_server_avg_new_established_conns=25.2,l4_server_avg_pool_open_conns=63.1,l4_server_sum_connection_errors=0.4 1693756800000000000
```

### Global Tags

- `vendor`: VMware
- `product`: AVI_Load_Balancer
- `environment`: Configurable (dev/staging/prod)
- `location`: Configurable datacenter/region
- `device_name`: AVI device name (`${AVI_DEVICE_NAME}`)
- `ip_address`: AVI controller IP (`${AVI_CONTROLLER_IP}`)

## 📈 Production Deployment

### System Requirements

- **CPU**: 2+ cores
- **Memory**: 4GB+ RAM
- **Disk**: 10GB+ available space
- **Network**: Access to AVI Controller and Kentik APIs

### High Availability

For production HA deployments:

1. Deploy multiple Telegraf instances
2. Use external load balancer
3. Configure shared storage for logs
4. Set up monitoring alerts

### Performance Tuning

Key configuration parameters:

```toml
[agent]
  interval = "60s"           # Collection interval
  metric_batch_size = 1000   # Batch size for outputs
  metric_buffer_limit = 10000 # Buffer size
  flush_interval = "10s"     # Output flush interval
```

## 🛠️ Development

### Prerequisites

- Python 3.8+
- Docker/OrbStack  
- AVI Load Balancer (or use mock server)

### Setup Development Environment  

```bash
# Clone repository
git clone https://github.com/mkrygeri/tele-AVI.git
cd tele-AVI

# Setup environment
make setup

# Start development environment
make dev-start

# Run tests
make test-all
```

### Available Commands

```bash
make help          # Show all available commands
make setup         # Initial setup
make validate      # Validate configuration
make dev-start     # Start development environment  
make test-all      # Run comprehensive tests
make deploy        # Production deployment
make clean         # Clean up resources
```

## 🐛 Troubleshooting

### Common Issues

#### Telegraf Not Collecting Metrics
- Check AVI Controller connectivity
- Verify credentials in `.env`
- Review Telegraf logs: `make logs`

#### TLS Certificate Errors
- For testing: Use `insecure_skip_verify = true`
- For production: Configure proper certificate paths

#### Kentik Integration Issues
- Verify API endpoint and credentials
- Check network connectivity to Kentik
- Review HTTP output plugin configuration

See [TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) for detailed solutions.

## 📄 Documentation

- **[Configuration Guide](docs/CONFIGURATION.md)**: Detailed configuration reference
- **[Deployment Guide](docs/DEPLOYMENT.md)**: Production deployment instructions
- **[Troubleshooting](docs/TROUBLESHOOTING.md)**: Common issues and solutions
- **[Project Overview](PROJECT_OVERVIEW.md)**: Complete project documentation

## 🤝 Contributing

Contributions are welcome! Please read our [Contributing Guide](CONTRIBUTING.md) for details on our development process and how to submit pull requests.

## 🔒 Security

Please see our [Security Policy](SECURITY.md) for reporting vulnerabilities and security best practices.

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🏷️ Tags

`telegraf` `avi-load-balancer` `kentik` `nms` `monitoring` `observability` `vmware` `nsx` `docker` `influxdb`

---

**Built with ❤️ for network observability and monitoring**

### Virtual Service Metrics
- Average complete connections
- Average new established connections
- Average pool complete connections
- Average pool new established connections
- Average complete responses
- Average complete requests

### Pool Metrics
- Average complete connections
- Average new established connections
- Average open connections
- Sum of connection errors

### Service Engine Metrics
- Average CPU usage percentage
- Average memory usage percentage
- Average disk usage percentage
- Average bandwidth in bps

### Controller Metrics
- Average CPU usage percentage
- Average memory usage percentage
- Average disk usage percentage

## Prerequisites

1. **AVI Controller Access**
   - AVI Controller IP address or FQDN
   - Administrative username and password
   - Network connectivity to AVI Controller API (HTTPS port 443)

2. **Kentik Account**
   - Active Kentik NMS account
   - API token and email credentials
   - Access to Kentik's metrics ingestion endpoint

3. **Docker Environment**
   - Docker and Docker Compose installed
   - Sufficient resources for Telegraf container

## Quick Start

### Production Deployment

1. **Clone and Configure**
   ```bash
   git clone <your-repo>
   cd tele-AVI
   cp .env.example .env
   ```

2. **Edit Environment Variables**
   Edit the `.env` file with your specific configuration:
   ```bash
   # AVI Controller Configuration
   AVI_CONTROLLER_IP=your-avi-controller-ip
   AVI_USERNAME=your-avi-username
   AVI_PASSWORD=your-avi-password
   AVI_DEVICE_NAME=avi-controller-01
   
   # Kentik Configuration
   KENTIK_API_TOKEN=your-kentik-api-token
   KENTIK_API_EMAIL=your-kentik-email@company.com
   KENTIK_API_ENDPOINT="https://grpc.api.kentik.com/kmetrics/v202207/metrics/api/v2/write?bucket=&org=&precision=ns"
   
   # Environment Tags
   ENVIRONMENT=production
   LOCATION=your-datacenter-location
   ```

3. **Create Logs Directory**
   ```bash
   mkdir -p logs
   ```

4. **Start Telegraf**
   ```bash
   docker-compose up -d
   ```

5. **Verify Operation**
   ```bash
   # Check container status
   docker-compose ps
   
   # View logs
   docker-compose logs -f telegraf
   ```

### Testing with Mock AVI Server

If you don't have an AVI Load Balancer available for testing, you can use the included mock server:

1. **Start Mock Environment**
   ```bash
   # Quick start with make
   make test-all
   
   # Or manually with Docker Compose
   docker-compose -f docker-compose.testing.yml up --build -d
   ```

2. **Test Mock API**
   ```bash
   # Test the mock server endpoints
   make mock-test
   
   # Or run the test script directly
   python3 test-mock-avi.py
   ```

3. **Monitor Telegraf Collection**
   ```bash
   # View Telegraf logs to see data collection
   docker-compose -f docker-compose.testing.yml logs -f telegraf
   ```

4. **Clean Up**
   ```bash
   make mock-stop
   ```

### Mock Server Details

The mock AVI server provides:
- **Realistic API responses** mimicking AVI Controller API
- **Multiple virtual services, pools, and service engines**
- **Time-series data** with realistic variance
- **Session login authentication** via `POST /login` (admin:admin123); HTTP Basic Auth accepted as a fallback
- **HTTPS endpoint** on port 8443

## Configuration Details

### AVI API Endpoints

The configuration queries the following AVI Controller API endpoints:

- `/api/analytics/metrics/virtualservice` - Virtual service performance metrics
- `/api/analytics/metrics/pool` - Backend pool metrics  
- `/api/analytics/metrics/serviceengine` - Service engine resource metrics
- `/api/analytics/metrics/controller` - Controller cluster metrics

### Authentication

Authentication to the AVI Controller uses **session login**: Telegraf's HTTP input
performs a `POST /login` with a JSON body (`{"username": ..., "password": ...}`) and
`Content-Type: application/json`, then reuses the returned session cookie for all
analytics API calls. The cookie is renewed automatically (`cookie_auth_renewal`). The
AVI API does **not** accept HTTP Basic Auth for analytics by default. For production
deployments, consider:

- Using certificate-based authentication
- Storing credentials in a secure secrets management system
- Implementing proper TLS verification

### Data Collection

- **Collection Interval**: 60 seconds (configurable)
- **Metrics Step**: 300 seconds (5-minute aggregation)
- **Timeout**: 30 seconds per API call
- **TLS**: Skip verification enabled (configure properly for production)

### Kentik Integration

Metrics are sent to Kentik using the HTTP output plugin with:
- InfluxDB Line Protocol format
- Kentik-specific authentication headers
- 30-second timeout
- Automatic retries on failures

## Customization

### Adding More Metrics

To collect additional AVI metrics, modify the `metric_id` parameter in the URLs within `telegraf.conf`. Available metrics include:

- `l4_server.avg_bandwidth` - Average bandwidth usage
- `l7_server.avg_client_data_transfer_time` - Client data transfer time
- `dos_attacks.sum_dos_attacks` - DDoS attack counts
- `l7_server.sum_server_errors` - Server error counts

### Adjusting Collection Frequency

Modify the `interval` setting in the `[agent]` section and the `step` parameter in the API URLs.

### Custom Tags

Add environment-specific tags in the `[global_tags]` section or as environment variables.

## Testing and Development

### Mock AVI Server

For testing and development purposes, this project includes a mock AVI Controller server that simulates the real AVI API endpoints:

#### Features
- **Complete API Simulation**: Mimics all AVI Controller metrics endpoints
- **Realistic Data**: Generates time-series metrics with realistic variance
- **Authentication**: Session login via `POST /login` (admin:admin123); HTTP Basic Auth accepted as a fallback
- **HTTPS Support**: Self-signed certificates for testing
- **Docker Support**: Containerized for easy deployment

#### Available Commands
```bash
# Start mock environment and run tests
make test-all

# Start mock server only
make mock-start

# Test mock server endpoints
make mock-test

# View logs
make mock-logs

# Stop mock environment  
make mock-stop
```

#### Direct Python Usage
```bash
# Install dependencies
pip install -r requirements.txt

# Start mock server
python3 mock-avi-server.py

# Test in another terminal
python3 test-mock-avi.py
```

#### Mock Data Generated
The mock server generates realistic metrics for:
- 5 Virtual Services (web-app, api, mobile, auth, checkout)
- 5 Pools (web-app, api, mobile, auth, database)  
- 3 Service Engines (se-1, se-2, se-3)
- 1 Controller (single controller entity, 30 `controller_stats.*` metrics)

All metrics include time-series data with realistic variance and proper tagging.

### Health Checks

Monitor Telegraf health by:
```bash
# Check container status
docker-compose ps

# View recent logs
docker-compose logs --tail=100 telegraf

# Monitor metrics output
tail -f logs/avi-metrics.out
```

### Common Issues

1. **Authentication Failures**
   - Verify AVI username/password
   - Check if account has API access permissions

2. **Network Connectivity**
   - Ensure Docker container can reach AVI Controller
   - Check firewall rules for outbound HTTPS

3. **Kentik API Issues**
   - Verify API token and email are correct
   - Check Kentik account quotas and limits

4. **TLS Certificate Issues**
   - For production, configure proper TLS validation
   - Add AVI Controller certificates to trusted store

### Debugging

Enable debug logging by setting `debug = true` in the `[agent]` section of `telegraf.conf`.

## Security Considerations

### Production Deployment

For production use:

1. **Secure Credentials**
   - Use Docker secrets or external key management
   - Avoid plaintext passwords in configuration files

2. **TLS Configuration**
   - Implement proper certificate validation
   - Use mutual TLS authentication where possible

3. **Network Security**
   - Deploy in secure network segments
   - Use firewalls to restrict API access

4. **Monitoring**
   - Set up alerts for collection failures
   - Monitor resource usage and performance

## Performance Optimization

### Resource Allocation

Adjust Docker resource limits based on your environment:

```yaml
deploy:
  resources:
    limits:
      memory: 512M
      cpus: '0.5'
    reservations:
      memory: 256M
      cpus: '0.25'
```

### Batching and Buffering

Tune Telegraf batching parameters in `telegraf.conf`:

```toml
metric_batch_size = 1000
metric_buffer_limit = 10000
flush_interval = "10s"
```

## Kentik Dashboard Creation

After data starts flowing to Kentik:

1. **Create Custom Dashboards**
   - Use Kentik's dashboard builder
   - Focus on key AVI performance metrics
   - Set up alerting for critical thresholds

2. **Example Queries**
   - Virtual Service Connection Rate: `avg(l4_server_avg_new_established_conns) by entity_uuid`
   - Service Engine CPU Utilization: `avg(se_stats_avg_cpu_usage) by entity_uuid`
   - Pool Connection Errors: `sum(l4_server_sum_connection_errors) by entity_uuid`

## Support and Maintenance

### Updates

Keep Telegraf updated by:
```bash
docker-compose pull
docker-compose up -d
```

### Backup

Regularly backup:
- Configuration files
- Environment variables
- Any custom modifications

## License

This configuration is provided under the MIT License. See LICENSE file for details.

## Contributing

1. Fork the repository
2. Create a feature branch
3. Submit a pull request with detailed description

## References

- [AVI Load Balancer API Documentation](https://techdocs.broadcom.com/us/en/vmware-security-load-balancing/avi-load-balancer/avi-load-balancer/22-1/monitoring-and-operability-guide/nsx-advanced-load-balancer-monitoring-components/metrics.html)
- [Kentik Telegraf Integration Guide](https://www.kentik.com/blog/using-telegraf-to-feed-api-json-data-into-kentik-nms/)
- [Telegraf Documentation](https://docs.influxdata.com/telegraf/)
- [Docker Compose Documentation](https://docs.docker.com/compose/)
