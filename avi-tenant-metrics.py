#!/usr/bin/env python3
"""Collect AVI metrics for all tenants and emit Influx line protocol."""

from __future__ import annotations

import os
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from typing import Dict, Iterable, List, Tuple

import requests
import urllib3

MEASUREMENTS = {
    "virtualservice": "/devices/avi/virtualservice",
    "pool": "/devices/avi/pool",
    "serviceengine": "/devices/avi/serviceengine",
    "controller": "/devices/avi/controller",
}

METRIC_IDS = {
    "virtualservice": [
        "l4_server.avg_complete_conns",
        "l4_server.avg_new_established_conns",
        "l4_server.avg_pool_complete_conns",
        "l4_server.avg_pool_new_established_conns",
        "l7_server.avg_complete_responses",
        "l7_server.avg_client_complete_requests",
    ],
    "pool": [
        "l4_server.avg_complete_conns",
        "l4_server.avg_new_established_conns",
        "l4_server.avg_pool_open_conns",
        "l4_server.sum_connection_errors",
    ],
    "serviceengine": [
        "se_stats.avg_cpu_usage",
        "se_stats.avg_mem_usage",
        "se_stats.avg_disk_usage",
        "se_if.avg_bandwidth",
    ],
    "controller": [
        "controller_stats.avg_cpu_usage",
        "controller_stats.avg_mem_usage",
        "controller_stats.avg_disk_usage",
        "controller_stats.avg_disk_read_bytes",
        "controller_stats.avg_disk_write_bytes",
        "controller_stats.avg_num_active_vs",
        "controller_stats.max_num_active_vs",
        "controller_stats.avg_num_ses",
        "controller_stats.max_num_ses",
        "controller_stats.avg_num_se_cores",
        "controller_stats.max_num_se_cores",
        "controller_stats.avg_num_service_cores",
        "controller_stats.max_num_service_cores",
        "controller_stats.avg_num_sockets",
        "controller_stats.max_num_sockets",
        "controller_stats.avg_num_backend_servers",
        "controller_stats.max_num_backend_servers",
        "controller_stats.avg_total_se_throughput",
        "controller_stats.max_total_se_throughput",
        "controller_stats.sum_total_se_bytes",
        "controller_stats.sum_total_vs_bytes",
        "controller_stats.sum_total_vs_client_bytes",
        "controller_stats.sum_total_vs_usage",
        "controller_stats.max_num_active_vs_lic_usage",
        "controller_stats.max_num_ses_lic_usage",
        "controller_stats.max_num_sockets_lic_usage",
        "controller_stats.max_num_service_cores_lic_usage",
        "controller_stats.max_se_cores_lic_usage",
        "controller_stats.max_se_throughput_lic_usage",
        "controller_stats.max_be_servers_lic_usage",
    ],
}

SCOPE_MODES = {"auto", "header_uuid", "header_name", "query_uuid", "query_name"}


def bool_env(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def float_env(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    try:
        return float(value)
    except ValueError:
        print(
            f"WARNING: invalid {name}={value!r}, using default {default}",
            file=sys.stderr,
        )
        return default


def require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def to_ns(timestamp: str | None) -> int:
    if not timestamp:
        return time.time_ns()
    text = timestamp.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return time.time_ns()
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1_000_000_000)


def escape_measurement(value: str) -> str:
    return value.replace("\\", "\\\\").replace(",", "\\,").replace(" ", "\\ ")


def escape_tag_or_key(value: str) -> str:
    escaped = value.replace("\\", "\\\\")
    escaped = escaped.replace(",", "\\,").replace(" ", "\\ ")
    return escaped.replace("=", "\\=")


def encode_field_value(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return f"{value}i"
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            raise ValueError("invalid float")
        return repr(value)
    text = str(value).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{text}"'


def normalize_metric_name(endpoint: str, name: str) -> str:
    if endpoint == "controller" and name.startswith("controller_stats."):
        prefix_len = len("controller_stats.")
        name = name[prefix_len:]
    return name.replace(".", "_")


class AviCollector:
    def __init__(self) -> None:
        controller = require_env("AVI_CONTROLLER_IP").strip()
        if controller.startswith("http://") or controller.startswith("https://"):
            self.base_url = controller.rstrip("/")
        else:
            self.base_url = f"https://{controller}"

        self.username = require_env("AVI_USERNAME")
        self.password = require_env("AVI_PASSWORD")

        self.insecure_skip_verify = bool_env("AVI_INSECURE_SKIP_VERIFY", True)
        if self.insecure_skip_verify:
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
            print(
                "WARNING: TLS verification is disabled (AVI_INSECURE_SKIP_VERIFY=true)",
                file=sys.stderr,
            )

        self.request_timeout = float_env("AVI_REQUEST_TIMEOUT_SECONDS", 15.0)
        self.total_timeout = float_env("AVI_TOTAL_TIMEOUT_SECONDS", 50.0)
        self.deadline = time.monotonic() + self.total_timeout

        self.scope_mode = os.getenv("AVI_TENANT_SCOPE_MODE", "auto").strip().lower()
        if self.scope_mode not in SCOPE_MODES:
            print(
                "WARNING: unsupported AVI_TENANT_SCOPE_MODE="
                f"{self.scope_mode!r}; using 'auto'",
                file=sys.stderr,
            )
            self.scope_mode = "auto"

        self.tenant_uuid_header = os.getenv(
            "AVI_TENANT_UUID_HEADER", "X-Avi-Tenant-UUID"
        )
        self.tenant_name_header = os.getenv("AVI_TENANT_NAME_HEADER", "X-Avi-Tenant")
        self.tenant_uuid_query_param = os.getenv(
            "AVI_TENANT_UUID_QUERY_PARAM", "tenant_uuid"
        )
        self.tenant_name_query_param = os.getenv(
            "AVI_TENANT_NAME_QUERY_PARAM", "tenant"
        )

        self.session = requests.Session()

    def _timeout(self) -> float:
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("overall collection timeout reached")
        return min(self.request_timeout, remaining)

    def _request(self, method: str, path: str, **kwargs) -> requests.Response:
        timeout = kwargs.pop("timeout", None)
        response = self.session.request(
            method=method,
            url=f"{self.base_url}{path}",
            timeout=timeout or self._timeout(),
            verify=not self.insecure_skip_verify,
            **kwargs,
        )
        response.raise_for_status()
        return response

    def login(self) -> None:
        self._request(
            "POST",
            "/login",
            json={"username": self.username, "password": self.password},
            headers={"Content-Type": "application/json"},
        )

    def list_tenants(self) -> List[Dict[str, str]]:
        response = self._request("GET", "/api/tenant")
        payload = response.json()
        tenants: List[Dict[str, str]] = []
        for item in payload.get("results", []):
            tenant_uuid = item.get("uuid")
            if not tenant_uuid:
                continue
            tenant_name = item.get("name") or tenant_uuid
            tenants.append({"uuid": str(tenant_uuid), "name": str(tenant_name)})
        return tenants

    def _scope_attempts(self) -> Iterable[str]:
        if self.scope_mode != "auto":
            return [self.scope_mode]
        return ["header_uuid", "query_uuid", "header_name", "query_name"]

    def _add_scope(
        self,
        scope: str,
        tenant: Dict[str, str],
        headers: Dict[str, str],
        params: Dict[str, str],
    ) -> None:
        if scope == "header_uuid":
            headers[self.tenant_uuid_header] = tenant["uuid"]
        elif scope == "header_name":
            headers[self.tenant_name_header] = tenant["name"]
        elif scope == "query_uuid":
            params[self.tenant_uuid_query_param] = tenant["uuid"]
        elif scope == "query_name":
            params[self.tenant_name_query_param] = tenant["name"]

    def fetch_endpoint(
        self, endpoint: str, tenant: Dict[str, str]
    ) -> Dict[str, object]:
        params = {
            "metric_id": ",".join(METRIC_IDS[endpoint]),
            "step": "300",
            "limit": "1",
            "include_name": "true",
        }

        last_error: Exception | None = None
        for scope in self._scope_attempts():
            req_params = dict(params)
            headers: Dict[str, str] = {}
            self._add_scope(scope, tenant, headers, req_params)
            try:
                response = self._request(
                    "GET",
                    f"/api/analytics/metrics/{endpoint}",
                    params=req_params,
                    headers=headers,
                )
                return response.json()
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                if self.scope_mode != "auto":
                    break

        if last_error is None:
            raise RuntimeError("metrics request failed without error")
        raise last_error


def build_line_protocol(
    tenant_lookup: Dict[str, str],
    endpoint: str,
    tenant: Dict[str, str],
    payload: Dict[str, object],
) -> List[str]:
    measurement = MEASUREMENTS[endpoint]
    records: Dict[Tuple[str, Tuple[Tuple[str, str], ...], int], Dict[str, object]] = (
        defaultdict(dict)
    )

    for result in payload.get("results", []):
        entity_default = result.get("entity_uuid")
        for series in result.get("series", []):
            header = series.get("header", {})
            metric_name = header.get("name")
            if not metric_name:
                continue
            field_name = normalize_metric_name(endpoint, str(metric_name))

            entity_uuid = (
                header.get("entity_uuid")
                or header.get("pool_uuid")
                or header.get("serviceengine_uuid")
                or entity_default
            )
            tenant_uuid = header.get("tenant_uuid") or tenant["uuid"]
            tenant_name = (
                header.get("tenant_name")
                or tenant_lookup.get(str(tenant_uuid))
                or tenant.get("name")
            )

            tags = {
                "entity_uuid": entity_uuid,
                "pool_uuid": header.get("pool_uuid"),
                "serviceengine_uuid": header.get("serviceengine_uuid"),
                "tenant_uuid": tenant_uuid,
                "tenant_name": tenant_name,
            }
            tag_items = tuple(
                sorted(
                    (k, str(v))
                    for k, v in tags.items()
                    if v is not None and str(v) != ""
                )
            )

            for point in series.get("data", []):
                if "value" not in point:
                    continue
                timestamp_ns = to_ns(point.get("timestamp"))
                key = (measurement, tag_items, timestamp_ns)
                try:
                    records[key][field_name] = float(point["value"])
                except (TypeError, ValueError):
                    continue

    lines: List[str] = []
    for (measure, tag_items, timestamp_ns), fields in sorted(
        records.items(), key=lambda item: (item[0][0], item[0][2], item[0][1])
    ):
        if not fields:
            continue
        tag_text = ",".join(
            f"{escape_tag_or_key(k)}={escape_tag_or_key(v)}" for k, v in tag_items
        )
        field_text = ",".join(
            f"{escape_tag_or_key(k)}={encode_field_value(v)}"
            for k, v in sorted(fields.items())
        )
        line = escape_measurement(measure)
        if tag_text:
            line += f",{tag_text}"
        line += f" {field_text} {timestamp_ns}"
        lines.append(line)

    return lines


def main() -> int:
    if bool_env("AVI_COLLECTOR_VALIDATE_ONLY", False):
        return 0

    try:
        collector = AviCollector()
        collector.login()
        tenants = collector.list_tenants()
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: setup failed: {exc}", file=sys.stderr)
        return 1

    if not tenants:
        print("ERROR: no tenants returned by /api/tenant", file=sys.stderr)
        return 1

    tenant_lookup = {tenant["uuid"]: tenant["name"] for tenant in tenants}
    lines: List[str] = []
    successful_requests = 0

    for tenant in tenants:
        for endpoint in MEASUREMENTS:
            try:
                payload = collector.fetch_endpoint(endpoint, tenant)
                lines.extend(
                    build_line_protocol(tenant_lookup, endpoint, tenant, payload)
                )
                successful_requests += 1
            except TimeoutError as exc:
                print(
                    f"ERROR: timeout collecting {endpoint} metrics for tenant "
                    f"{tenant['uuid']}: {exc}",
                    file=sys.stderr,
                )
                break
            except Exception as exc:  # noqa: BLE001
                print(
                    f"ERROR: failed collecting {endpoint} metrics for tenant "
                    f"{tenant['uuid']} ({tenant['name']}): {exc}",
                    file=sys.stderr,
                )

    if lines:
        print("\n".join(lines))

    if successful_requests == 0:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
