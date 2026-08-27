#!/usr/bin/env python3
"""
Test script for Mock AVI Controller API
"""

import requests
import json
import sys
import urllib3

# Disable SSL warnings for testing
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class MockAVITester:
    def __init__(self, base_url="https://localhost:8443", username="admin", password="admin123"):
        self.base_url = base_url
        self.username = username
        self.password = password
        self.session = requests.Session()
        self.session.verify = False  # Skip SSL verification for testing

    def login(self):
        """Authenticate via AVI session login (POST /login) and store the cookie."""
        response = self.session.post(
            f"{self.base_url}/login",
            json={"username": self.username, "password": self.password},
            headers={"Content-Type": "application/json"},
        )
        return response.status_code == 200

    def test_health(self):
        """Test health endpoint"""
        print("🔍 Testing health endpoint...")
        try:
            response = self.session.get(f"{self.base_url}/health")
            if response.status_code == 200:
                print("✅ Health check passed")
                return True
            else:
                print(f"❌ Health check failed: {response.status_code}")
                return False
        except Exception as e:
            print(f"❌ Health check error: {e}")
            return False
    
    def test_authentication(self):
        """Test session login authentication"""
        print("🔍 Testing authentication...")
        try:
            # Log in via POST /login to obtain a session cookie
            if not self.login():
                print("❌ Session login failed")
                return False
            # Confirm the cookie is accepted on an authenticated endpoint
            response = self.session.get(f"{self.base_url}/api/tenant")
            if response.status_code == 200:
                print("✅ Authentication successful (session cookie)")
                return True
            else:
                print(f"❌ Authentication failed: {response.status_code}")
                return False
        except Exception as e:
            print(f"❌ Authentication error: {e}")
            return False
    
    def test_virtualservice_metrics(self):
        """Test virtual service metrics endpoint"""
        print("🔍 Testing Virtual Service metrics...")
        try:
            params = {
                'metric_id': 'l4_server.avg_complete_conns,l7_server.avg_complete_responses',
                'step': 300,
                'limit': 1
            }
            response = self.session.get(
                f"{self.base_url}/api/analytics/metrics/virtualservice",
                params=params
            )
            
            if response.status_code == 200:
                data = response.json()
                results = data.get('results', [])
                series_count = sum(len(r.get('series', [])) for r in results)
                print(f"✅ Virtual Service metrics returned {series_count} series")
                
                # Print sample data
                if results and results[0].get('series'):
                    sample = results[0]['series'][0]
                    header = sample.get('header', {})
                    print(f"   📊 Sample metric: {header.get('name')}")
                    print(f"   🏷️  Entity UUID: {header.get('entity_uuid')}")
                    print(f"   📈 Data points: {len(sample.get('data', []))}")
                
                return True
            else:
                print(f"❌ Virtual Service metrics failed: {response.status_code}")
                return False
        except Exception as e:
            print(f"❌ Virtual Service metrics error: {e}")
            return False
    
    def test_pool_metrics(self):
        """Test pool metrics endpoint"""
        print("🔍 Testing Pool metrics...")
        try:
            params = {
                'metric_id': 'l4_server.avg_complete_conns,l4_server.sum_connection_errors',
                'step': 300,
                'limit': 1
            }
            response = self.session.get(
                f"{self.base_url}/api/analytics/metrics/pool",
                params=params
            )
            
            if response.status_code == 200:
                data = response.json()
                series_count = sum(len(r.get('series', [])) for r in data.get('results', []))
                print(f"✅ Pool metrics returned {series_count} series")
                return True
            else:
                print(f"❌ Pool metrics failed: {response.status_code}")
                return False
        except Exception as e:
            print(f"❌ Pool metrics error: {e}")
            return False
    
    def test_serviceengine_metrics(self):
        """Test service engine metrics endpoint"""
        print("🔍 Testing Service Engine metrics...")
        try:
            params = {
                'metric_id': 'se_stats.avg_cpu_usage,se_stats.avg_mem_usage',
                'step': 300,
                'limit': 1
            }
            response = self.session.get(
                f"{self.base_url}/api/analytics/metrics/serviceengine",
                params=params
            )
            
            if response.status_code == 200:
                data = response.json()
                series_count = sum(len(r.get('series', [])) for r in data.get('results', []))
                print(f"✅ Service Engine metrics returned {series_count} series")
                return True
            else:
                print(f"❌ Service Engine metrics failed: {response.status_code}")
                return False
        except Exception as e:
            print(f"❌ Service Engine metrics error: {e}")
            return False
    
    def test_controller_metrics(self):
        """Test controller metrics endpoint"""
        print("🔍 Testing Controller metrics...")
        try:
            params = {
                'metric_id': 'controller_stats.avg_cpu_usage,controller_stats.avg_mem_usage',
                'step': 300,
                'limit': 1
            }
            response = self.session.get(
                f"{self.base_url}/api/analytics/metrics/controller",
                params=params
            )
            
            if response.status_code == 200:
                data = response.json()
                series_count = sum(len(r.get('series', [])) for r in data.get('results', []))
                print(f"✅ Controller metrics returned {series_count} series")
                return True
            else:
                print(f"❌ Controller metrics failed: {response.status_code}")
                return False
        except Exception as e:
            print(f"❌ Controller metrics error: {e}")
            return False
    
    def test_all_endpoints(self):
        """Run all tests"""
        print("🚀 Starting Mock AVI Controller API Tests")
        print("=" * 50)
        
        tests = [
            ("Health Check", self.test_health),
            ("Authentication", self.test_authentication),
            ("Virtual Service Metrics", self.test_virtualservice_metrics),
            ("Pool Metrics", self.test_pool_metrics),
            ("Service Engine Metrics", self.test_serviceengine_metrics),
            ("Controller Metrics", self.test_controller_metrics)
        ]
        
        passed = 0
        total = len(tests)
        
        for test_name, test_func in tests:
            print(f"\n📋 Running: {test_name}")
            if test_func():
                passed += 1
            else:
                print(f"   ⚠️  {test_name} failed")
        
        print("\n" + "=" * 50)
        print(f"📊 Test Results: {passed}/{total} tests passed")
        
        if passed == total:
            print("🎉 All tests passed! Mock AVI server is working correctly.")
            return True
        else:
            print("❌ Some tests failed. Check the server logs for details.")
            return False

def main():
    """Main function"""
    if len(sys.argv) > 1:
        base_url = sys.argv[1]
    else:
        base_url = "https://localhost:8443"
    
    if len(sys.argv) > 3:
        username = sys.argv[2]
        password = sys.argv[3]
    else:
        username = "admin"
        password = "admin123"
    
    print(f"🔗 Testing Mock AVI API at: {base_url}")
    print(f"👤 Using credentials: {username}:{'*' * len(password)}")
    
    tester = MockAVITester(base_url, username, password)
    success = tester.test_all_endpoints()
    
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()
