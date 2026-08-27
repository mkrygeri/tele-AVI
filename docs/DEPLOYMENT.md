# Production Deployment Guide

This guide covers deploying the AVI Load Balancer to Kentik integration in production environments.

## Prerequisites

### System Requirements

- **Operating System**: Linux (Ubuntu 20.04+ recommended)
- **CPU**: 2+ cores
- **Memory**: 4GB+ RAM  
- **Disk**: 20GB+ available space
- **Network**: Access to AVI Controller and Kentik APIs

### Software Requirements

- Docker 20.10+
- Docker Compose 2.0+
- Network connectivity to:
  - AVI Controller (HTTPS/443)
  - Kentik API endpoints (HTTPS/443)

## Pre-Deployment Checklist

### AVI Controller Preparation

- [ ] Create dedicated service account for API access
- [ ] Verify API permissions for metrics endpoints
- [ ] Test API connectivity from deployment host
- [ ] Document AVI Controller FQDN/IP
- [ ] Obtain or generate TLS certificates if using certificate validation

### Kentik Account Preparation

- [ ] Create Kentik API token
- [ ] Verify account quotas and limits
- [ ] Test API endpoint connectivity
- [ ] Document Kentik account details

### Infrastructure Preparation

- [ ] Provision deployment host
- [ ] Configure firewall rules
- [ ] Set up log aggregation
- [ ] Configure monitoring and alerting

## Deployment Methods

### Method 1: Docker Compose (Recommended)

1. **Clone Repository**
   ```bash
   git clone https://github.com/mkrygeri/tele-AVI.git
   cd tele-AVI
   ```

2. **Configure Environment**
   ```bash
   cp .env.example .env
   # Edit .env with production values
   ```

3. **Create Required Directories**
   ```bash
   sudo mkdir -p /var/log/telegraf
   sudo chown $(id -u):$(id -g) /var/log/telegraf
   ```

4. **Deploy**
   ```bash
   docker-compose up -d
   ```

5. **Verify**
   ```bash
   docker-compose ps
   docker-compose logs telegraf
   ```

### Method 2: Native Installation

1. **Install Telegraf**
   ```bash
   # Ubuntu/Debian
   wget -q https://repos.influxdata.com/influxdata-archive_compat.key
   echo '393e8779c89ac8d958f81f942f9ad7fb82a25e133fddaf92e15b16e6ac9ce4c6 influxdata-archive_compat.key' | sha256sum -c && cat influxdata-archive_compat.key | gpg --dearmor | sudo tee /etc/apt/trusted.gpg.d/influxdata-archive_compat.gpg > /dev/null
   echo 'deb [signed-by=/etc/apt/trusted.gpg.d/influxdata-archive_compat.gpg] https://repos.influxdata.com/debian stable main' | sudo tee /etc/apt/sources.list.d/influxdata.list
   sudo apt-get update && sudo apt-get install telegraf
   ```

2. **Configure**
   ```bash
   sudo cp telegraf.conf /etc/telegraf/telegraf.conf
   sudo cp .env /etc/telegraf/.env
   ```

3. **Start Service**
   ```bash
   sudo systemctl enable telegraf
   sudo systemctl start telegraf
   ```

## Production Configuration

### Environment Variables

Create `/etc/telegraf/.env`:

```bash
# AVI Controller Configuration  
AVI_CONTROLLER_IP=avi-controller.example.com
AVI_USERNAME=telegraf-service
AVI_PASSWORD=secure-password-here
AVI_DEVICE_NAME=avi-controller-01

# Kentik Configuration
KENTIK_API_ENDPOINT="https://grpc.api.kentik.com/kmetrics/v202207/metrics/api/v2/write?bucket=&org=&precision=ns"
KENTIK_API_EMAIL=monitoring@example.com
KENTIK_API_TOKEN=your-secure-api-token

# Environment Tags
ENVIRONMENT=production
LOCATION=datacenter-west
```

### TLS Configuration

For production deployments with proper TLS:

1. **Obtain Certificates**
   - CA certificate for AVI Controller
   - Client certificate (if using mutual TLS)

2. **Update telegraf.conf**
   ```toml
   tls_ca = "/etc/telegraf/certs/ca.pem"
   tls_cert = "/etc/telegraf/certs/client.pem"
   tls_key = "/etc/telegraf/certs/client-key.pem"
   insecure_skip_verify = false
   ```

3. **Set Permissions**
   ```bash
   sudo chown -R telegraf:telegraf /etc/telegraf/certs
   sudo chmod 600 /etc/telegraf/certs/*-key.pem
   ```

### Security Hardening

1. **Service Account**
   ```bash
   sudo useradd -r -s /bin/false telegraf
   ```

2. **File Permissions**
   ```bash
   sudo chown -R telegraf:telegraf /etc/telegraf
   sudo chmod 640 /etc/telegraf/telegraf.conf
   sudo chmod 600 /etc/telegraf/.env
   ```

3. **Network Security**
   - Configure firewall rules
   - Use VPN or private networks
   - Enable audit logging

## High Availability Setup

### Load Balancer Configuration

Deploy multiple Telegraf instances behind a load balancer:

```yaml
version: '3.8'
services:
  telegraf-1:
    image: telegraf:1.29-alpine
    environment:
      - TELEGRAF_INSTANCE_ID=telegraf-1
    # ... other configuration
  
  telegraf-2:
    image: telegraf:1.29-alpine  
    environment:
      - TELEGRAF_INSTANCE_ID=telegraf-2
    # ... other configuration
```

### Data Consistency

To prevent duplicate metrics:
- Use different `host` tags per instance
- Implement jittered collection intervals
- Monitor for data duplication in Kentik

### Health Monitoring

Implement health checks:

```yaml
healthcheck:
  test: ["CMD", "telegraf", "--config", "/etc/telegraf/telegraf.conf", "--test"]
  interval: 30s
  timeout: 10s
  retries: 3
  start_period: 40s
```

## Monitoring and Alerting

### Log Monitoring

Monitor Telegraf logs for:
- API connection errors
- Authentication failures  
- Data parsing errors
- Output failures

### Metrics Monitoring

Set up alerts for:
- Collection failures
- High error rates
- Memory/CPU usage
- Network connectivity issues

### Example Prometheus Metrics

If using Prometheus output:

```toml
[[outputs.prometheus_client]]
  listen = ":9273"
  metric_version = 2
```

Key metrics to monitor:
- `telegraf_internal_gather_errors_total`
- `telegraf_internal_write_errors_total`  
- `telegraf_internal_buffer_size`

## Performance Optimization

### Resource Allocation

For Docker deployments:

```yaml
deploy:
  resources:
    limits:
      memory: 1G
      cpus: '1'
    reservations:  
      memory: 512M
      cpus: '0.5'
```

### Configuration Tuning

High-throughput environments:

```toml
[agent]
  interval = "30s"
  metric_batch_size = 5000
  metric_buffer_limit = 50000
  flush_interval = "15s"
  collection_jitter = "5s"
```

### Parallel Processing

Split configurations by metric type:

- `telegraf-vs.conf` - Virtual Service metrics
- `telegraf-pools.conf` - Pool metrics  
- `telegraf-se.conf` - Service Engine metrics
- `telegraf-controller.conf` - Controller metrics

## Backup and Recovery

### Configuration Backup

```bash
#!/bin/bash
# backup-telegraf.sh
BACKUP_DIR="/backup/telegraf/$(date +%Y%m%d)"
mkdir -p "$BACKUP_DIR"

# Backup configuration
cp /etc/telegraf/telegraf.conf "$BACKUP_DIR/"
cp /etc/telegraf/.env "$BACKUP_DIR/"

# Backup certificates  
if [ -d /etc/telegraf/certs ]; then
    cp -r /etc/telegraf/certs "$BACKUP_DIR/"
fi

# Compress
tar -czf "$BACKUP_DIR/../telegraf-backup-$(date +%Y%m%d).tar.gz" -C "$BACKUP_DIR" .
```

### Disaster Recovery

1. **Restore Configuration**
   ```bash
   sudo tar -xzf telegraf-backup.tar.gz -C /etc/telegraf/
   sudo systemctl restart telegraf
   ```

2. **Validate Operation**
   ```bash
   sudo systemctl status telegraf
   sudo journalctl -u telegraf -f
   ```

## Troubleshooting

### Common Issues

1. **Authentication Failures**
   - Verify credentials in `.env`
   - Check AVI user permissions
   - Test manual API access

2. **Network Connectivity**
   - Verify firewall rules
   - Test DNS resolution  
   - Check proxy settings

3. **Certificate Issues**
   - Validate certificate paths
   - Check certificate expiration
   - Verify CA chain

### Debug Mode

Enable debug logging:

```toml
[agent]
  debug = true
  quiet = false
```

### Log Analysis

Common log patterns:

```bash
# Authentication errors
grep "401\|403" /var/log/telegraf/telegraf.log

# Network errors  
grep "connection\|timeout" /var/log/telegraf/telegraf.log

# Parsing errors
grep "parse\|json" /var/log/telegraf/telegraf.log
```

## Maintenance

### Regular Tasks

1. **Log Rotation**
   ```bash
   # /etc/logrotate.d/telegraf
   /var/log/telegraf/*.log {
       daily
       missingok
       rotate 52
       compress
       notifempty
       create 644 telegraf telegraf
       postrotate
           systemctl reload telegraf
       endscript
   }
   ```

2. **Update Schedule**
   - Review Telegraf releases monthly
   - Test updates in staging first
   - Schedule maintenance windows

3. **Certificate Renewal**
   - Monitor certificate expiration
   - Automate renewal where possible
   - Test after renewal

### Performance Reviews

Quarterly reviews should include:
- Resource usage analysis
- Error rate trends  
- Configuration optimization
- Capacity planning

## Support Escalation

### Information to Collect

When reporting issues:
- Telegraf version
- Configuration files (sanitized)
- Error logs (relevant sections)
- AVI Controller version
- Network topology

### Contact Information

- GitHub Issues: https://github.com/mkrygeri/tele-AVI/issues
- Documentation: https://github.com/mkrygeri/tele-AVI/docs
