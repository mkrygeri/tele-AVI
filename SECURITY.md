# Security Policy

## Supported Versions

We support the latest version of this project with security updates.

| Version | Supported          |
| ------- | ------------------ |
| Latest  | :white_check_mark: |
| < 1.0   | :x:                |

## Reporting a Vulnerability

If you discover a security vulnerability, please follow these steps:

1. **Do NOT** create a public GitHub issue for the vulnerability
2. Send an email to the maintainers with:
   - A description of the vulnerability
   - Steps to reproduce the issue
   - Potential impact assessment
   - Any suggested fixes (optional)

## Security Best Practices

When deploying this project:

### Credentials Management
- Never commit credentials to version control
- Use environment variables or secrets management systems
- Rotate credentials regularly
- Use service accounts with minimal permissions

### TLS Configuration
- Always use proper TLS certificates in production
- Never use `insecure_skip_verify = true` in production
- Keep TLS libraries updated
- Use strong cipher suites

### Network Security
- Deploy in secure network segments
- Use firewalls to restrict access
- Monitor network traffic for anomalies
- Consider using VPN or private connections

### Container Security
- Use official Docker images when possible
- Regularly update base images
- Scan containers for vulnerabilities
- Run containers with non-root users where possible

### Monitoring
- Enable debug logging during troubleshooting only
- Monitor for authentication failures
- Set up alerts for unusual activity
- Regularly review access logs

## Vulnerability Response

We will:
- Acknowledge receipt of vulnerability reports within 48 hours
- Provide regular updates on our investigation
- Work to fix confirmed vulnerabilities promptly
- Coordinate disclosure timing with reporters
- Credit reporters (if desired) in security advisories

## Dependencies

This project depends on:
- Telegraf (InfluxData)
- Docker/Docker Compose
- Python (for mock server)

We monitor these dependencies for security updates and will update our recommendations accordingly.
