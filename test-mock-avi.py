#!/usr/bin/env python3
"""Basic tests for the mock AVI Controller API."""

import sys

import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class MockAVITester:
    def __init__(
        self,
        base_url: str = "https://localhost:8443",
        username: str = "admin",
        password: str = "admin123",
    ) -> None:
        self.base_url = base_url
        self.username = username
        self.password = password
        self.session = requests.Session()
        self.verify = False
        self.tenants = []

    def login(self) -> bool:
        response = self.session.post(
            f"{self.base_url}/login",
            json={"username": self.username, "password": self.password},
            headers={"Content-Type": "application/json"},
            timeout=8,
            verify=self.verify,
        )
        return response.status_code == 200

    def test_health(self) -> bool:
        print("🔍 Testing health endpoint...")
        try:
            response = self.session.get(
                f"{self.base_url}/health", timeout=8, verify=self.verify
            )
            if response.status_code == 200:
                print("✅ Health check passed")
                return True
            print(f"❌ Health check failed: {response.status_code}")
            return False
        except Exception as exc:  # noqa: BLE001
            print(f"❌ Health check error: {exc}")
            return False

    def test_authentication(self) -> bool:
        print("🔍 Testing authentication...")
        try:
            if not self.login():
                print("❌ Session login failed")
                return False
            response = self.session.get(
                f"{self.base_url}/api/tenant", timeout=8, verify=self.verify
            )
            if response.status_code == 200:
                print("✅ Authentication successful (session cookie)")
                return True
            print(f"❌ Authentication failed: {response.status_code}")
            return False
        except Exception as exc:  # noqa: BLE001
            print(f"❌ Authentication error: {exc}")
            return False

    def test_tenants(self) -> bool:
        print("🔍 Testing tenant discovery...")
        try:
            response = self.session.get(
                f"{self.base_url}/api/tenant", timeout=8, verify=self.verify
            )
            if response.status_code != 200:
                print(f"❌ Tenant API failed: {response.status_code}")
                return False
            data = response.json()
            self.tenants = data.get("results", [])
            if len(self.tenants) < 2:
                print("❌ Expected multiple tenants from /api/tenant")
                return False
            print(f"✅ Tenant discovery returned {len(self.tenants)} tenants")
            return True
        except Exception as exc:  # noqa: BLE001
            print(f"❌ Tenant API error: {exc}")
            return False

    def _test_metrics_endpoint(self, endpoint: str, metric_ids: str) -> bool:
        params = {"metric_id": metric_ids, "step": 300, "limit": 1}
        response = self.session.get(
            f"{self.base_url}/api/analytics/metrics/{endpoint}",
            params=params,
            timeout=8,
            verify=self.verify,
        )
        if response.status_code != 200:
            print(f"❌ {endpoint} metrics failed: {response.status_code}")
            return False
        data = response.json()
        series_count = sum(
            len(item.get("series", [])) for item in data.get("results", [])
        )
        print(f"✅ {endpoint} metrics returned {series_count} series")
        return True

    def test_metrics_endpoints(self) -> bool:
        print("🔍 Testing metric endpoints...")
        return all(
            [
                self._test_metrics_endpoint(
                    "virtualservice",
                    "l4_server.avg_complete_conns,l7_server.avg_complete_responses",
                ),
                self._test_metrics_endpoint(
                    "pool",
                    "l4_server.avg_complete_conns,l4_server.sum_connection_errors",
                ),
                self._test_metrics_endpoint(
                    "serviceengine", "se_stats.avg_cpu_usage,se_stats.avg_mem_usage"
                ),
                self._test_metrics_endpoint(
                    "controller",
                    "controller_stats.avg_cpu_usage,controller_stats.avg_mem_usage",
                ),
            ]
        )

    def test_tenant_scoping(self) -> bool:
        print("🔍 Testing tenant scoping (header/query)...")
        if not self.tenants:
            print("❌ No tenant list available for scoping test")
            return False

        target = self.tenants[1]
        tenant_uuid = target["uuid"]
        tenant_name = target["name"]
        metric_ids = "l4_server.avg_complete_conns"

        try:
            by_query = self.session.get(
                f"{self.base_url}/api/analytics/metrics/virtualservice",
                params={
                    "metric_id": metric_ids,
                    "step": 300,
                    "limit": 1,
                    "tenant_uuid": tenant_uuid,
                },
                timeout=8,
                verify=self.verify,
            )
            by_header = self.session.get(
                f"{self.base_url}/api/analytics/metrics/virtualservice",
                params={"metric_id": metric_ids, "step": 300, "limit": 1},
                headers={"X-Avi-Tenant": tenant_name},
                timeout=8,
                verify=self.verify,
            )
            if by_query.status_code != 200 or by_header.status_code != 200:
                print("❌ Tenant-scoped metrics request failed")
                return False

            for payload in (by_query.json(), by_header.json()):
                for result in payload.get("results", []):
                    for series in result.get("series", []):
                        actual_tenant = series.get("header", {}).get("tenant_uuid")
                        if actual_tenant != tenant_uuid:
                            print(
                                "❌ Unexpected tenant in scoped response: "
                                f"{actual_tenant} (expected {tenant_uuid})"
                            )
                            return False

            print("✅ Tenant scoping works for query and header modes")
            return True
        except Exception as exc:  # noqa: BLE001
            print(f"❌ Tenant scoping test error: {exc}")
            return False

    def test_all_endpoints(self) -> bool:
        print("🚀 Starting Mock AVI Controller API Tests")
        print("=" * 50)

        tests = [
            ("Health Check", self.test_health),
            ("Authentication", self.test_authentication),
            ("Tenant Discovery", self.test_tenants),
            ("Metrics Endpoints", self.test_metrics_endpoints),
            ("Tenant Scoping", self.test_tenant_scoping),
        ]

        passed = 0
        for test_name, test_func in tests:
            print(f"\n📋 Running: {test_name}")
            if test_func():
                passed += 1
            else:
                print(f"   ⚠️  {test_name} failed")

        print("\n" + "=" * 50)
        print(f"📊 Test Results: {passed}/{len(tests)} tests passed")

        if passed == len(tests):
            print("🎉 All tests passed! Mock AVI server is working correctly.")
            return True

        print("❌ Some tests failed. Check the server logs for details.")
        return False


def main() -> None:
    base_url = sys.argv[1] if len(sys.argv) > 1 else "https://localhost:8443"
    username = sys.argv[2] if len(sys.argv) > 2 else "admin"
    password = sys.argv[3] if len(sys.argv) > 3 else "admin123"

    print(f"🔗 Testing Mock AVI API at: {base_url}")
    print(f"👤 Using credentials: {username}:{'*' * len(password)}")

    tester = MockAVITester(base_url, username, password)
    success = tester.test_all_endpoints()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
