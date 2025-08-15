#!/usr/bin/env python3
"""
Mock AVI Controller API Server
Simulates AVI Load Balancer API endpoints for testing Telegraf configuration
"""

from flask import Flask, jsonify, request
from flask_httpauth import HTTPBasicAuth
import json
import random
import time
from datetime import datetime, timedelta
import logging

app = Flask(__name__)
auth = HTTPBasicAuth()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Mock credentials
USERS = {
    "admin": "admin123",
    "aviuser": "avipass"
}

@auth.verify_password
def verify_password(username, password):
    if username in USERS and USERS[username] == password:
        return username
    return None

def generate_timestamp():
    """Generate timestamp in AVI format"""
    now = datetime.now()
    return int(now.timestamp()) * 1000

def generate_time_series_data(num_points=5):
    """Generate time series data points"""
    data_points = []
    base_time = datetime.now() - timedelta(minutes=25)  # Start 25 minutes ago
    
    for i in range(num_points):
        timestamp = base_time + timedelta(minutes=i*5)
        data_points.append({
            "timestamp": int(timestamp.timestamp()) * 1000,
            "value": round(random.uniform(10, 100), 2)
        })
    
    return data_points

@app.route('/api/tenant', methods=['GET'])
@auth.login_required
def get_tenants():
    """Mock tenant endpoint for connectivity testing"""
    return jsonify({
        "count": 2,
        "results": [
            {
                "uuid": "admin-tenant-uuid-1234",
                "name": "admin",
                "local": True,
                "config_settings": {
                    "tenant_vrf": False,
                    "se_in_provider_context": True
                }
            },
            {
                "uuid": "demo-tenant-uuid-5678",
                "name": "demo",
                "local": True,
                "config_settings": {
                    "tenant_vrf": False,
                    "se_in_provider_context": True
                }
            }
        ]
    })

@app.route('/api/analytics/metrics/virtualservice', methods=['GET'])
@auth.login_required
def get_virtualservice_metrics():
    """Mock Virtual Service metrics endpoint"""
    logger.info(f"Virtual Service metrics request: {request.args}")
    
    # Parse metric_id parameter
    metric_ids = request.args.get('metric_id', '').split(',')
    step = int(request.args.get('step', 300))
    limit = int(request.args.get('limit', 1))
    
    # Generate mock virtual services
    virtual_services = [
        {
            "name": "web-app-vs",
            "uuid": "virtualservice-web-app-uuid-1234",
            "tenant": "admin"
        },
        {
            "name": "api-vs", 
            "uuid": "virtualservice-api-uuid-5678",
            "tenant": "admin"
        },
        {
            "name": "mobile-vs",
            "uuid": "virtualservice-mobile-uuid-9012",
            "tenant": "demo"
        }
    ]
    
    series_data = []
    
    for vs in virtual_services[:limit]:
        for metric_id in metric_ids:
            if not metric_id.strip():
                continue
                
            # Generate realistic values based on metric type
            if 'conn' in metric_id:
                base_value = random.uniform(50, 500)
            elif 'response' in metric_id:
                base_value = random.uniform(100, 1000)
            elif 'request' in metric_id:
                base_value = random.uniform(80, 800)
            else:
                base_value = random.uniform(10, 100)
            
            # Create time series data
            data_points = []
            base_time = datetime.now() - timedelta(minutes=20)
            
            for i in range(5):  # 5 data points over 20 minutes
                timestamp = base_time + timedelta(minutes=i*5)
                value = base_value + random.uniform(-10, 10)  # Add some variance
                data_points.append({
                    "timestamp": int(timestamp.timestamp()) * 1000,
                    "value": round(max(0, value), 2)  # Ensure non-negative
                })
            
            series_data.append({
                "metric_id": metric_id,
                "tags": {
                    "virtualservice_name": vs["name"],
                    "virtualservice_uuid": vs["uuid"],
                    "tenant": vs["tenant"]
                },
                "data": data_points
            })
    
    response = {
        "series": series_data,
        "start": int((datetime.now() - timedelta(minutes=25)).timestamp()) * 1000,
        "stop": int(datetime.now().timestamp()) * 1000,
        "step": step
    }
    
    logger.info(f"Returning {len(series_data)} virtual service metric series")
    return jsonify(response)

@app.route('/api/analytics/metrics/pool', methods=['GET'])
@auth.login_required
def get_pool_metrics():
    """Mock Pool metrics endpoint"""
    logger.info(f"Pool metrics request: {request.args}")
    
    metric_ids = request.args.get('metric_id', '').split(',')
    step = int(request.args.get('step', 300))
    limit = int(request.args.get('limit', 1))
    
    # Generate mock pools
    pools = [
        {
            "name": "web-app-pool",
            "uuid": "pool-web-app-uuid-1234",
            "tenant": "admin"
        },
        {
            "name": "api-pool",
            "uuid": "pool-api-uuid-5678", 
            "tenant": "admin"
        },
        {
            "name": "database-pool",
            "uuid": "pool-db-uuid-9012",
            "tenant": "demo"
        }
    ]
    
    series_data = []
    
    for pool in pools[:limit]:
        for metric_id in metric_ids:
            if not metric_id.strip():
                continue
                
            # Generate realistic values based on metric type
            if 'error' in metric_id:
                base_value = random.uniform(0, 5)  # Lower error rates
            elif 'conn' in metric_id:
                base_value = random.uniform(20, 200)
            else:
                base_value = random.uniform(10, 100)
            
            # Create time series data
            data_points = []
            base_time = datetime.now() - timedelta(minutes=20)
            
            for i in range(5):
                timestamp = base_time + timedelta(minutes=i*5)
                value = base_value + random.uniform(-5, 5)
                data_points.append({
                    "timestamp": int(timestamp.timestamp()) * 1000,
                    "value": round(max(0, value), 2)
                })
            
            series_data.append({
                "metric_id": metric_id,
                "tags": {
                    "pool_name": pool["name"],
                    "pool_uuid": pool["uuid"],
                    "tenant": pool["tenant"]
                },
                "data": data_points
            })
    
    response = {
        "series": series_data,
        "start": int((datetime.now() - timedelta(minutes=25)).timestamp()) * 1000,
        "stop": int(datetime.now().timestamp()) * 1000,
        "step": step
    }
    
    logger.info(f"Returning {len(series_data)} pool metric series")
    return jsonify(response)

@app.route('/api/analytics/metrics/serviceengine', methods=['GET'])
@auth.login_required
def get_serviceengine_metrics():
    """Mock Service Engine metrics endpoint"""
    logger.info(f"Service Engine metrics request: {request.args}")
    
    metric_ids = request.args.get('metric_id', '').split(',')
    step = int(request.args.get('step', 300))
    limit = int(request.args.get('limit', 1))
    
    # Generate mock service engines
    service_engines = [
        {
            "name": "Avi-se-1",
            "uuid": "se-uuid-1234-abcd",
            "tenant": "admin"
        },
        {
            "name": "Avi-se-2", 
            "uuid": "se-uuid-5678-efgh",
            "tenant": "admin"
        },
        {
            "name": "Avi-se-3",
            "uuid": "se-uuid-9012-ijkl",
            "tenant": "demo"
        }
    ]
    
    series_data = []
    
    for se in service_engines[:limit]:
        for metric_id in metric_ids:
            if not metric_id.strip():
                continue
                
            # Generate realistic values based on metric type
            if 'cpu_usage' in metric_id:
                base_value = random.uniform(20, 80)  # CPU percentage
            elif 'mem_usage' in metric_id:
                base_value = random.uniform(30, 70)  # Memory percentage
            elif 'disk_usage' in metric_id:
                base_value = random.uniform(10, 40)  # Disk percentage
            elif 'bandwidth' in metric_id:
                base_value = random.uniform(1000000, 10000000)  # Bytes per second
            else:
                base_value = random.uniform(10, 100)
            
            # Create time series data
            data_points = []
            base_time = datetime.now() - timedelta(minutes=20)
            
            for i in range(5):
                timestamp = base_time + timedelta(minutes=i*5)
                # Add some realistic variance
                if 'bandwidth' in metric_id:
                    value = base_value + random.uniform(-base_value*0.2, base_value*0.2)
                else:
                    value = base_value + random.uniform(-5, 5)
                
                data_points.append({
                    "timestamp": int(timestamp.timestamp()) * 1000,
                    "value": round(max(0, value), 2)
                })
            
            series_data.append({
                "metric_id": metric_id,
                "tags": {
                    "serviceengine_name": se["name"],
                    "serviceengine_uuid": se["uuid"],
                    "tenant": se["tenant"]
                },
                "data": data_points
            })
    
    response = {
        "series": series_data,
        "start": int((datetime.now() - timedelta(minutes=25)).timestamp()) * 1000,
        "stop": int(datetime.now().timestamp()) * 1000,
        "step": step
    }
    
    logger.info(f"Returning {len(series_data)} service engine metric series")
    return jsonify(response)

@app.route('/api/analytics/metrics/controller', methods=['GET'])
@auth.login_required
def get_controller_metrics():
    """Mock Controller metrics endpoint"""
    logger.info(f"Controller metrics request: {request.args}")
    
    metric_ids = request.args.get('metric_id', '').split(',')
    step = int(request.args.get('step', 300))
    limit = int(request.args.get('limit', 1))
    
    # Generate mock controllers
    controllers = [
        {
            "name": "avi-controller-1",
            "uuid": "controller-uuid-1234-primary"
        },
        {
            "name": "avi-controller-2",
            "uuid": "controller-uuid-5678-secondary"
        },
        {
            "name": "avi-controller-3", 
            "uuid": "controller-uuid-9012-tertiary"
        }
    ]
    
    series_data = []
    
    for controller in controllers[:limit]:
        for metric_id in metric_ids:
            if not metric_id.strip():
                continue
                
            # Generate realistic values based on metric type
            if 'cpu_usage' in metric_id:
                base_value = random.uniform(15, 60)  # Controller CPU
            elif 'mem_usage' in metric_id:
                base_value = random.uniform(40, 80)  # Controller Memory
            elif 'disk_usage' in metric_id:
                base_value = random.uniform(20, 50)  # Controller Disk
            else:
                base_value = random.uniform(10, 100)
            
            # Create time series data
            data_points = []
            base_time = datetime.now() - timedelta(minutes=20)
            
            for i in range(5):
                timestamp = base_time + timedelta(minutes=i*5)
                value = base_value + random.uniform(-3, 3)  # Small variance
                data_points.append({
                    "timestamp": int(timestamp.timestamp()) * 1000,
                    "value": round(max(0, value), 2)
                })
            
            series_data.append({
                "metric_id": metric_id,
                "tags": {
                    "controller_name": controller["name"],
                    "controller_uuid": controller["uuid"]
                },
                "data": data_points
            })
    
    response = {
        "series": series_data,
        "start": int((datetime.now() - timedelta(minutes=25)).timestamp()) * 1000,
        "stop": int(datetime.now().timestamp()) * 1000,
        "step": step
    }
    
    logger.info(f"Returning {len(series_data)} controller metric series")
    return jsonify(response)

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        "status": "healthy",
        "timestamp": generate_timestamp(),
        "version": "mock-avi-1.0.0"
    })

@app.route('/', methods=['GET'])
def index():
    """Root endpoint with API information"""
    return jsonify({
        "name": "Mock AVI Controller API",
        "version": "1.0.0",
        "description": "Mock server for testing AVI Load Balancer Telegraf integration",
        "endpoints": [
            "/api/tenant",
            "/api/analytics/metrics/virtualservice",
            "/api/analytics/metrics/pool", 
            "/api/analytics/metrics/serviceengine",
            "/api/analytics/metrics/controller",
            "/health"
        ],
        "authentication": "HTTP Basic Auth (admin:admin123 or aviuser:avipass)"
    })

@app.errorhandler(401)
def unauthorized(error):
    return jsonify({"error": "Authentication required"}), 401

@app.errorhandler(404)
def not_found(error):
    return jsonify({"error": "Endpoint not found"}), 404

if __name__ == '__main__':
    print("🚀 Starting Mock AVI Controller API Server")
    print("📋 Available credentials:")
    print("   - admin:admin123")
    print("   - aviuser:avipass")
    print("🔗 API will be available at: https://localhost:8443")
    print("💡 Use 'Ctrl+C' to stop the server")
    
    # Run with SSL context for HTTPS
    import ssl
    
    # Create a simple SSL context (self-signed cert)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    
    app.run(
        host='0.0.0.0',
        port=8443,
        debug=True,
        ssl_context='adhoc'  # Generate self-signed cert automatically
    )
