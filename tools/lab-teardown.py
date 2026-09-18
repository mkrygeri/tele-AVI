#!/usr/bin/env python3
"""Remove the sample tenants, pools, VsVips, and virtual services created by
tools/lab-seed.py from a NON-PRODUCTION AVI/NSX-ALB controller.

Only objects whose names exactly match the seeded set are deleted, so this will
not touch unrelated configuration. Deletion order respects dependencies:
virtual service -> vsvip -> pool -> tenant.

WARNING: This performs DELETE operations on the controller. Only run it against
a lab/test controller you are authorized to modify.
"""
from __future__ import annotations

import os
import sys
from typing import Dict, List, Optional

import requests
import urllib3

SEED_TENANTS: List[str] = ["tenant-blue", "tenant-green"]
SEED_APPS = ["web", "checkout", "api", "mobile"]
# Which tenant each app lives in (must match lab-seed.py).
APP_TENANT = {
    "web": "admin",
    "checkout": "admin",
    "api": "tenant-blue",
    "mobile": "tenant-green",
}


def _base_url() -> str:
    ctrl = os.environ["AVI_CONTROLLER_IP"].strip()
    base = ctrl if ctrl.startswith(("http://", "https://")) else f"https://{ctrl}"
    return base.rstrip("/")


def _truthy(value: Optional[str]) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


class LabTeardown:
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

    def delete_by_name(self, kind: str, name: str, tenant: Optional[str] = None) -> None:
        r = self.session.get(
            f"{self.base}/api/{kind}",
            params={"name": name},
            headers=self._headers(tenant),
            verify=self.verify,
            timeout=15,
        )
        if r.status_code != 200:
            return
        for item in r.json().get("results", []):
            if item.get("name") != name:
                continue
            url = item.get("url")
            dr = self.session.delete(
                url, headers=self._headers(tenant), verify=self.verify, timeout=20
            )
            state = "ok " if dr.status_code in (200, 204) else f"ERR {dr.status_code}"
            print(f"  {state} delete {kind} {name}")

    def run(self) -> None:
        self.login()
        # 1) virtual services (depend on vsvip + pool)
        print("Virtual services:")
        for app in SEED_APPS:
            self.delete_by_name("virtualservice", f"{app}-vs", APP_TENANT[app])
        # 2) vsvips
        print("VsVips:")
        for app in SEED_APPS:
            self.delete_by_name("vsvip", f"{app}-vsvip", APP_TENANT[app])
        # 3) pools
        print("Pools:")
        for app in SEED_APPS:
            self.delete_by_name("pool", f"{app}-pool", APP_TENANT[app])
        # 4) tenants (must be empty first)
        print("Tenants:")
        for tn in SEED_TENANTS:
            self.delete_by_name("tenant", tn)
        print("\nTeardown complete.")


def main() -> int:
    for key in ("AVI_CONTROLLER_IP", "AVI_USERNAME", "AVI_PASSWORD"):
        if not os.getenv(key):
            print(f"ERROR: {key} is not set (source your .env first)", file=sys.stderr)
            return 2
    LabTeardown().run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
