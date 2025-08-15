# Troubleshooting Guide

This guide helps diagnose and resolve common issues with the AVI Load Balancer to Kentik integration.

## Quick Diagnostics

### System Health Check

```bash
# Check container status
docker-compose ps

# Check Telegraf logs
docker-compose logs --tail=50 telegraf

# Test configuration
docker-compose exec telegraf telegraf --config /etc/telegraf/telegraf.conf --test

# Check resource usage
docker stats
```

### Connectivity Tests

```bash
# Test AVI Controller API
curl -k -u "${AVI_USERNAME}:${AVI_PASSWORD}" \
  "https://${AVI_CONTROLLER_IP}/api/analytics/metrics/virtualservice"

# Test Kentik API
curl -X POST "${KENTIK_API_ENDPOINT}" \
  -H "X-CH-Auth-Email: ${KENTIK_API_EMAIL}" \
  -H "X-CH-Auth-API-Token: ${KENTIK_API_TOKEN}" \
  -H "Content-Type: application/influx" \
  --data-binary "test_metric value=1"
```

## Common Issues

### 1. Authentication Failures

#### Symptoms
```
ERROR: HTTP response error: 401 Unauthorized
ERROR: Authentication failed for AVI Controller
```

#### Diagnosis
- Check credentials in `.env` file
- Verify AVI user account exists and is active
- Test manual API authentication

#### Solutions

1. **Verify Credentials**
   ```bash
   # Test with curl
   curl -k -u "${AVI_USERNAME}:${AVI_PASSWORD}" \
     "https://${AVI_CONTROLLER_IP}/api/initial-data"
   ```

2. **Check User Permissions**
   - User must have "Read" access to Analytics
   - User account must not be locked
   - Password must not be expired

3. **Update Configuration**
   ```bash
   # Edit .env file with correct credentials
   nano .env
   
   # Restart containers
   docker-compose restart
   ```

### 2. Network Connectivity Issues

#### Symptoms
```
ERROR: connection refused
ERROR: timeout waiting for response
ERROR: no route to host
```

#### Diagnosis
- Check network connectivity to AVI Controller
- Verify firewall rules
- Test DNS resolution

#### Solutions

1. **Network Connectivity**
   ```bash
   # Test basic connectivity
   ping ${AVI_CONTROLLER_IP}
   
   # Test HTTPS port
   telnet ${AVI_CONTROLLER_IP} 443
   
   # Test with curl
   curl -k --connect-timeout 10 https://${AVI_CONTROLLER_IP}
   ```

2. **Firewall Configuration**
   ```bash
   # Check outbound rules
   sudo iptables -L OUTPUT
   
   # Allow HTTPS traffic (if needed)
   sudo iptables -A OUTPUT -p tcp --dport 443 -j ACCEPT
   ```

3. **Docker Network Issues**
   ```bash
   # Check Docker networks
   docker network ls
   
   # Inspect bridge network
   docker network inspect bridge
   
   # Restart Docker networking
   sudo systemctl restart docker
   ```

### 3. TLS Certificate Problems

#### Symptoms
```
ERROR: certificate verify failed
ERROR: x509: certificate signed by unknown authority
ERROR: tls: handshake failure
```

#### Solutions

1. **For Testing (Temporary)**
   ```toml
   # In telegraf.conf
   insecure_skip_verify = true
   ```

2. **For Production (Recommended)**
   ```bash
   # Get AVI Controller certificate
   openssl s_client -connect ${AVI_CONTROLLER_IP}:443 -showcerts
   
   # Save CA certificate to file
   echo "-----BEGIN CERTIFICATE-----" > /etc/telegraf/certs/ca.pem
   # ... certificate content ...
   echo "-----END CERTIFICATE-----" >> /etc/telegraf/certs/ca.pem
   
   # Update telegraf.conf
   tls_ca = "/etc/telegraf/certs/ca.pem"
   insecure_skip_verify = false
   ```

### 4. JSON Parsing Errors

#### Symptoms
```
ERROR: json: cannot unmarshal array into Go value
ERROR: field not found in parsed JSON
ERROR: invalid JSON response
```

#### Diagnosis
- Check AVI API response format
- Verify JSON path expressions
- Test with sample data

#### Solutions

1. **Debug JSON Response**
   ```bash
   # Get raw API response
   curl -k -u "${AVI_USERNAME}:${AVI_PASSWORD}" \
     "https://${AVI_CONTROLLER_IP}/api/analytics/metrics/virtualservice?metric_id=l4_server.avg_complete_conns&step=300&limit=1" | jq '.'
   ```

2. **Validate JSON Paths**
   ```bash
   # Test JSON path with jq
   curl -k -u admin:password123 https://localhost:8443/api/analytics/metrics/virtualservice | \
   jq '.series[0].tags.virtualservice_name'
   ```

3. **Update Configuration**
   - Verify `json_v2` path expressions
   - Check for changes in AVI API response format
   - Test with minimal configuration

### 5. Kentik Output Failures

#### Symptoms
```
ERROR: HTTP response error: 400 Bad Request
ERROR: failed to write metrics to Kentik
ERROR: API token invalid or expired
```

#### Solutions

1. **Verify Kentik Credentials**
   ```bash
   # Test API endpoint
   curl -X GET "https://api.kentik.com/api/v1/users" \
     -H "X-CH-Auth-Email: ${KENTIK_API_EMAIL}" \
     -H "X-CH-Auth-API-Token: ${KENTIK_API_TOKEN}"
   ```

2. **Check Data Format**
   ```bash
   # Test with sample data
   curl -X POST "${KENTIK_API_ENDPOINT}" \
     -H "X-CH-Auth-Email: ${KENTIK_API_EMAIL}" \
     -H "X-CH-Auth-API-Token: ${KENTIK_API_TOKEN}" \
     -H "Content-Type: application/influx" \
     --data-binary "avi_test,host=test value=1.0 $(date +%s)000000000"
   ```

### 6. High Memory Usage

#### Symptoms
```
WARNING: metric buffer limit exceeded
ERROR: out of memory
Container keeps restarting
```

#### Solutions

1. **Increase Buffer Limits**
   ```toml
   [agent]
   metric_batch_size = 5000
   metric_buffer_limit = 50000
   flush_interval = "10s"
   ```

2. **Optimize Collection**
   ```toml
   # Reduce collection frequency
   interval = "120s"
   
   # Add jitter to spread load
   collection_jitter = "30s"
   ```

3. **Docker Memory Limits**
   ```yaml
   services:
     telegraf:
       deploy:
         resources:
           limits:
             memory: 2G
   ```

### 7. Missing Metrics

#### Symptoms
- Some metric types not appearing in Kentik
- Empty or partial data sets
- Metrics stop appearing intermittently

#### Diagnosis

1. **Check Input Status**
   ```bash
   # Look for input-specific errors
   docker-compose logs telegraf | grep -E "(virtualservice|pool|serviceengine|controller)"
   ```

2. **Verify API Responses**
   ```bash
   # Test each endpoint manually
   for endpoint in virtualservice pool serviceengine controller; do
     echo "Testing $endpoint..."
     curl -k -u "${AVI_USERNAME}:${AVI_PASSWORD}" \
       "https://${AVI_CONTROLLER_IP}/api/analytics/metrics/$endpoint" | jq '.series | length'
   done
   ```

#### Solutions

1. **Check Metric IDs**
   - Verify metric_id parameters match AVI version
   - Some metrics may not be available in all AVI versions
   - Check AVI documentation for available metrics

2. **Review Time Ranges**
   ```toml
   # Increase time window
   urls = ["https://${AVI_CONTROLLER_IP}/api/analytics/metrics/virtualservice?metric_id=...&step=300&limit=10"]
   ```

3. **Split Configurations**
   - Create separate inputs for each metric type
   - Use different collection intervals
   - Implement retry logic

### 8. Performance Issues

#### Symptoms
- Slow metric collection
- High CPU usage
- API timeouts

#### Solutions

1. **Optimize Timeouts**
   ```toml
   timeout = "60s"
   ```

2. **Parallel Collection**
   ```toml
   # Use multiple HTTP inputs with different intervals
   [[inputs.http]]
   name_override = "avi_critical_metrics"
   interval = "30s"
   # ... configuration for critical metrics
   
   [[inputs.http]]  
   name_override = "avi_detailed_metrics"
   interval = "300s" 
   # ... configuration for detailed metrics
   ```

3. **Resource Allocation**
   ```bash
   # Monitor resource usage
   docker stats
   
   # Increase resources if needed
   docker-compose up --scale telegraf=2
   ```

## Debug Mode

### Enable Debug Logging

```toml
[agent]
  debug = true
  quiet = false
  logfile = "/var/log/telegraf/telegraf.log"
```

### Useful Log Patterns

```bash
# Authentication issues
grep -i "auth\|401\|403" /var/log/telegraf/telegraf.log

# Network issues  
grep -i "connect\|timeout\|refused" /var/log/telegraf/telegraf.log

# JSON parsing issues
grep -i "json\|parse\|unmarshal" /var/log/telegraf/telegraf.log

# Output issues
grep -i "output\|write\|kentik" /var/log/telegraf/telegraf.log
```

## Mock Server Testing

### Using Mock Server for Debugging

```bash
# Start mock environment
docker-compose -f docker-compose.testing.yml up -d

# Test mock endpoints
python test-mock-avi.py

# Compare with real AVI responses
curl -k -u admin:admin123 https://localhost:8443/api/analytics/metrics/virtualservice | jq '.'
```

### Mock vs Real API Differences

If working in mock environment but failing with real AVI:

1. **Compare Response Formats**
   ```bash
   # Mock response
   curl -k -u admin:admin123 https://localhost:8443/api/analytics/metrics/virtualservice > mock_response.json
   
   # Real AVI response  
   curl -k -u "${AVI_USERNAME}:${AVI_PASSWORD}" \
     "https://${AVI_CONTROLLER_IP}/api/analytics/metrics/virtualservice" > real_response.json
   
   # Compare
   diff mock_response.json real_response.json
   ```

2. **Adjust Mock Server**
   - Update mock server to match real API responses
   - Test configuration changes with mock first

## Getting Help

### Information to Collect

When reporting issues, include:

1. **Environment Details**
   ```bash
   # Telegraf version
   telegraf version
   
   # Docker version
   docker version
   
   # System info
   uname -a
   ```

2. **Configuration Files** (sanitized)
   - `telegraf.conf` (remove passwords)
   - `docker-compose.yml`
   - `.env.example` with structure

3. **Log Excerpts**
   ```bash
   # Recent errors
   docker-compose logs --tail=100 telegraf | grep ERROR
   
   # Full debug logs (if enabled)
   docker-compose logs telegraf > telegraf_debug.log
   ```

4. **Network Information**
   ```bash
   # Connectivity tests
   ping ${AVI_CONTROLLER_IP}
   nslookup ${AVI_CONTROLLER_IP}
   ```

### Support Channels

- **GitHub Issues**: For bugs and feature requests
- **GitHub Discussions**: For questions and community help
- **Documentation**: Check docs/ directory for guides

### Emergency Procedures

1. **Stop Data Collection**
   ```bash
   docker-compose stop telegraf
   ```

2. **Backup Configuration**
   ```bash
   cp telegraf.conf telegraf.conf.backup.$(date +%Y%m%d)
   ```

3. **Rollback Changes**
   ```bash
   git checkout HEAD~1 telegraf.conf
   docker-compose restart telegraf
   ```

4. **Alternative Collection**
   - Use minimal configuration for critical metrics only
   - Implement manual data collection scripts as backup
   - Set up monitoring alerts for service failures
