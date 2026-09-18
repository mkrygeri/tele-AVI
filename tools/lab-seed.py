#!/usr/bin/env python3
"""Seed a NON-PRODUCTION AVI/NSX-ALB controller with sample tenants, pools, and
virtual services so the collector's name/state/relationship enrichment can be
validated end to end.

This is a TEST helper. It talks to the controller defined by the same
environment variables the collector uses (AVI_CONTROLLER_IP, AVI_USERNAME,
AVI_PASSWORD, AVI_INSECURE_SKIP_VERIFY). It is idempotent: objects that already
exist (matched by name) are left untouched.

Run `python tools/lab-teardown.py` to remove everything this script creates.

WARNING: This performs WRITE operations (POST) on the controller. Only run it
against a lab/test controller you are authorized to modify.
"""
from __future__ import annotations

import os
import sys
from typing import Dict, List, Optional

import requests
import urllib3

# Tenants created by this seeder (in addition to the built-in "admin").
SEED_TENANTS: List[str] = ["tenant-blue", "tenant-green"]

# app -> (tenant, vip, [server ips], disabled?) ; VS references the pool so the
# collector can surface the VS<->Pool relationship. One app is left disabled to
# exercise the "state" path used for alerting.
SEED_APPS = [
    ("web", "admin", "10.90.0.10", ["10.0.0.10", "10.0.0.11"], False),
    ("checkout", "admin", "10.90.0.11", ["10.0.1.10"], True),
    ("api", "tenant-blue", "10.90.1.10", ["10.1.0.10", "10.1.0.11"], False),
    ("mobile", "tenant-green", "10.90.2.10", ["10.2.0.10"], False),
]


def _base_url() -> str:
    ctrl = os.environ["AVI_CONTROLLER_IP"].strip()
    base = ctrl if ctrl.startswith(("http://", "https://")) else f"https://{ctrl}"
    return base.rstrip("/")


def _truthy(value: Optional[str]) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


class LabSeeder:
    def __init__(self) -> None:
        self.base = _base_url()
        self.verify = not _truthy(os.getenv("AVI_INSECURE_SKIP_VERIFY", "true"))
        if not self.verify:
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        self.session = requests.Session()
        self.version = "22.1.4"

    def login(self) -> None:
        r = self.session.post(
            f"{self.base}/login",
            json={
                "username": os.environ["AVI_USERNAME"],
                "password": os.environ["AVI_PASSWORD"],
            },
            verify=self.verify,
            timeout=15,
        )
        r.raise_for_status()
        try:
            self.version = r.json().get("version", {}).get("Version", self.version)
        except Exception:  # noqa: BLE001
            pass

    def _headers(self, tenant: Optional[str] = None) -> Dict[str, str]:
        h = {
            "X-Avi-Version": self.version,
            "Content-Type": "application/json",
            "Referer": f"{self.base}/",
            "X-CSRFToken": self.session.cookies.get("csrftoken", ""),
        }
        if tenant:
            h["X-Avi-Tenant"] = tenant
        return h

    def find_by_name(self, kind: str, name: str, tenant: Optional[str] = None):
        r = self.session.get(
            f"{self.base}/api/{kind}",
            params={"name": name},
            headers=self._headers(tenant),
            verify=self.verify,
            timeout=15,
        )
        if r.status_code != 200:
            return None
        for item in r.json().get("results", []):
            if item.get("name") == name:
                return item
        return None

    def create(self, kind: str, body: dict, tenant: Optional[str] = None):
        existing = self.find_by_name(kind, body["name"], tenant)
        if existing:
            print(f"  skip {kind} {body['name']} (exists)")
            return existing
        r = self.session.post(
            f"{self.base}/api/{kind}",
            json=body,
            headers=self._headers(tenant),
            verify=self.verify,
            timeout=20,
        )
        if r.status_code not in (200, 201):
            print(f"  ERR {r.status_code} {kind} {body['name']}: {str(r.text)[:200]}")
            return None
        obj = r.json()
        print(f"  ok  {kind} {body['name']}")
        return obj

    def run(self) -> None:
        self.login()
        cloud = self.session.get(
            f"{self.base}/api/cloud", headers=self._headers(), verify=self.verify,
            timeout=15,
        ).json()["results"][0]["url"]
        seg = self.session.get(
            f"{self.base}/api/serviceenginegroup", headers=self._headers(),
            verify=self.verify, timeout=15,
        ).json()["results"][0]["url"]
        vrfs = self.session.get(
            f"{self.base}/api/vrfcontext", headers=self._headers(),
            verify=self.verify, timeout=15,
        ).json()["results"]
        vrf = next((v["url"] for v in vrfs if v["name"] == "global"), vrfs[0]["url"])

        print("Tenants:")
        for tn in SEED_TENANTS:
            self.create(
                "tenant",
                {"name": tn, "local": True, "config_settings": {"tenant_vrf": False}},
            )

        for app, tenant, vip, servers, disabled in SEED_APPS:
            print(f"App '{app}' in tenant '{tenant}':")
            pool = self.create(
                "pool",
                {
                    "name": f"{app}-pool",
                    "cloud_ref": cloud,
                    "default_server_port": 80,
                    "servers": [
                        {"ip": {"addr": ip, "type": "V4"}, "port": 80,
                         "enabled": not disabled}
                        for ip in servers
                    ],
                },
                tenant=tenant,
            )
            if not pool:
                continue
            vsvip = self.create(
                "vsvip",
                {
                    "name": f"{app}-vsvip",
                    "cloud_ref": cloud,
                    "vrf_context_ref": vrf,
                    "vip": [
                        {"vip_id": "1", "enabled": True,
                         "ip_address": {"type": "V4", "addr": vip}}
                    ],
                },
                tenant=tenant,
            )
            if not vsvip:
                continue
            self.create(
                "virtualservice",
                {
                    "name": f"{app}-vs",
                    "cloud_ref": cloud,
                    "se_group_ref": seg,
                    "vsvip_ref": vsvip["url"],
                    "pool_ref": pool["url"],
                    "services": [{"port": 80, "enable_ssl": False}],
                    "enabled": not disabled,
                },
                tenant=tenant,
            )
        print("\nDone. Run the collector to see enriched output, or "
              "tools/lab-teardown.py to remove these objects.")


def main() -> int:
    for key in ("AVI_CONTROLLER_IP", "AVI_USERNAME", "AVI_PASSWORD"):
        if not os.getenv(key):
            print(f"ERROR: {key} is not set (source your .env first)", file=sys.stderr)
            return 2
    LabSeeder().run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
