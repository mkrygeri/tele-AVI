# AVI Load Balancer to Kentik Integration using Telegraf

This repository contains a Telegraf configuration to collect metrics from VMware AVI Load Balancer (NSX Advanced Load Balancer) and send them to Kentik NMS for monitoring and analysis.

## Overview

The configuration collects the following metrics from AVI:

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
   
   # Kentik Configuration
   KENTIK_API_TOKEN=your-kentik-api-token
   KENTIK_API_EMAIL=your-kentik-email@company.com
   
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
- **HTTP Basic Authentication** (admin:admin123)
- **HTTPS endpoint** on port 8443

## Configuration Details

### AVI API Endpoints

The configuration queries the following AVI Controller API endpoints:

- `/api/analytics/metrics/virtualservice` - Virtual service performance metrics
- `/api/analytics/metrics/pool` - Backend pool metrics  
- `/api/analytics/metrics/serviceengine` - Service engine resource metrics
- `/api/analytics/metrics/controller` - Controller cluster metrics

### Authentication

Authentication to AVI Controller uses HTTP Basic Auth with the configured username and password. For production deployments, consider:

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
- **Authentication**: HTTP Basic Auth (admin:admin123)
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
- 3 Virtual Services (web-app-vs, api-vs, mobile-vs)
- 3 Pools (web-app-pool, api-pool, database-pool)  
- 3 Service Engines (Avi-se-1, Avi-se-2, Avi-se-3)
- 3 Controllers (avi-controller-1, avi-controller-2, avi-controller-3)

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
   - Virtual Service Connection Rate: `avg(connections_avg_new_established) by vs_name`
   - Service Engine CPU Utilization: `avg(cpu_usage_avg_percent) by se_name`
   - Pool Health: `sum(pool_connection_errors_sum) by pool_name`

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
