#!/usr/bin/env python3
"""Collect AVI metrics for all tenants and emit Influx line protocol."""

from __future__ import annotations

import os
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from typing import Dict, Iterable, List, Tuple
from urllib.parse import parse_qsl, urlsplit

import requests
import urllib3

MEASUREMENTS = {
    "virtualservice": "/devices/avi/virtualservice",
    "pool": "/devices/avi/pool",
    "serviceengine": "/devices/avi/serviceengine",
    "controller": "/devices/avi/controller",
}

# Inventory endpoints provide the human-readable name, operational state, and
# object relationships (VS<->Pool) that the analytics metrics API omits.
# Live 22.1.x controllers use the hyphenated REST paths; the non-hyphenated
# forms (from the object swagger) 404, so try hyphenated first then fall back.
INVENTORY_ENDPOINTS = {
    "virtualservice": ["/api/virtualservice-inventory", "/api/vsinventory"],
    "pool": ["/api/pool-inventory", "/api/poolinventory"],
    "serviceengine": ["/api/serviceengine-inventory", "/api/serviceengineinventory"],
}

# Ordered per the AVI OperationalStatus enum. Index is emitted as
# oper_status_code so dashboards/alerts can key on a stable numeric value.
OPER_STATE_ENUM = [
    "OPER_UP",
    "OPER_DOWN",
    "OPER_CREATING",
    "OPER_RESOURCES",
    "OPER_INACTIVE",
    "OPER_DISABLED",
    "OPER_UNUSED",
    "OPER_UNKNOWN",
    "OPER_PROCESSING",
    "OPER_INITIALIZING",
    "OPER_ERROR_DISABLED",
    "OPER_AWAIT_MANUAL_PLACEMENT",
    "OPER_UPGRADING",
    "OPER_SE_PROCESSING",
    "OPER_PARTITIONED",
    "OPER_DISABLING",
    "OPER_FAILED",
    "OPER_UNAVAIL",
    "OPER_AGGREGATE_DOWN",
]
OPER_STATUS_CODE = {name: index for index, name in enumerate(OPER_STATE_ENUM)}

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


def csv_env_set(name: str) -> set[str]:
    value = os.getenv(name, "")
    return {item.strip().casefold() for item in value.split(",") if item.strip()}


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


def parse_ref(ref: object) -> Tuple[str, str]:
    """Split an AVI object reference into (uuid, name).

    With include_name=true refs look like
    https://host/api/pool/pool-<uuid>#pool-name.
    """
    if not ref:
        return "", ""
    text = str(ref)
    name = ""
    if "#" in text:
        text, name = text.split("#", 1)
    uuid = text.rstrip("/").rsplit("/", 1)[-1]
    return uuid, name


def oper_status_fields(state: object) -> Dict[str, object]:
    """Map an OperationalStatus state string to numeric fields for alerting."""
    fields: Dict[str, object] = {}
    if not state:
        return fields
    text = str(state)
    fields["up"] = 1 if text == "OPER_UP" else 0
    if text in OPER_STATUS_CODE:
        fields["oper_status_code"] = OPER_STATUS_CODE[text]
    return fields


def ref_name(ref: object) -> str:
    """Return just the #name suffix of an AVI object reference."""
    return parse_ref(ref)[1]


def first_vip_address(config: Dict[str, object]) -> str:
    """Return the first configured VIP IPv4/IPv6 address, if any."""
    vips = config.get("vip")
    if not isinstance(vips, list):
        return ""
    for vip in vips:
        if not isinstance(vip, dict):
            continue
        for key in ("ip_address", "ip6_address"):
            ip = vip.get(key)
            addr = ip.get("addr") if isinstance(ip, dict) else None
            if addr:
                return str(addr)
    return ""


def vs_pool_link(item: Dict[str, object], config: Dict[str, object]) -> Tuple[str, str]:
    """Resolve a VS's primary pool (uuid, name).

    Falls back from config.pool_ref to the pools[] / poolgroups[] arrays so
    SNI-child and pool-group virtual services still link to a backend.
    """
    pool_uuid, pool_name = parse_ref(config.get("pool_ref"))
    if pool_uuid:
        return pool_uuid, pool_name
    for key in ("pools", "poolgroups"):
        entries = item.get(key)
        if isinstance(entries, list):
            for entry in entries:
                ref = entry.get("ref") if isinstance(entry, dict) else None
                pool_uuid, pool_name = parse_ref(ref)
                if pool_uuid:
                    return pool_uuid, pool_name
    return "", ""



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
        self.tenant_allowlist = csv_env_set("AVI_TENANT_ALLOWLIST")
        self.tenant_denylist = csv_env_set("AVI_TENANT_DENYLIST")
        self.metric_batching = bool_env("AVI_METRIC_BATCHING", True)

        # Inventory enrichment adds names, operational state, and VS<->Pool
        # relationships to the analytics metrics.
        self.collect_inventory = bool_env("AVI_COLLECT_INVENTORY", True)
        self.api_version = os.getenv("AVI_API_VERSION", "22.1.4").strip() or "22.1.4"
        self.inventory_page_size = os.getenv("AVI_INVENTORY_PAGE_SIZE", "200")
        # Cache the inventory REST path that the controller actually serves so we
        # only probe candidate paths once (they differ across AVI versions).
        self._inventory_path_cache: Dict[str, str] = {}
        # Cache global controller (cluster) name/state; fetched once per run.
        self._cluster_info: Dict[str, Dict[str, object]] | None = None

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
        path = "/api/tenant"
        params: Dict[str, str] | None = {"page_size": "200"}
        headers = {self.tenant_name_header: "admin"}
        tenants: List[Dict[str, str]] = []
        while path:
            response = self._request("GET", path, params=params, headers=headers)
            payload = response.json()
            for item in payload.get("results", []):
                tenant_uuid = item.get("uuid")
                if not tenant_uuid:
                    continue
                tenant_name = item.get("name") or tenant_uuid
                tenants.append({"uuid": str(tenant_uuid), "name": str(tenant_name)})

            next_url = payload.get("next")
            if not next_url:
                break
            parsed = urlsplit(str(next_url))
            path = parsed.path or "/api/tenant"
            params = dict(parse_qsl(parsed.query, keep_blank_values=True))

        if self.tenant_allowlist:
            tenants = [
                tenant
                for tenant in tenants
                if tenant["name"].casefold() in self.tenant_allowlist
            ]
        if self.tenant_denylist:
            tenants = [
                tenant
                for tenant in tenants
                if tenant["name"].casefold() not in self.tenant_denylist
            ]
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

    @staticmethod
    def _payload_stats(payload: Dict[str, object]) -> Tuple[int, int, int]:
        total_series = 0
        data_series = 0
        total_points = 0
        for result in payload.get("results", []):
            if not isinstance(result, dict):
                continue
            for series in result.get("series", []):
                if not isinstance(series, dict):
                    continue
                total_series += 1
                data_points = series.get("data", [])
                if not data_points:
                    continue
                data_series += 1
                total_points += sum(
                    1
                    for point in data_points
                    if isinstance(point, dict) and "value" in point
                )
        return total_series, data_series, total_points

    @staticmethod
    def _merge_payloads(payloads: List[Dict[str, object]]) -> Dict[str, object]:
        merged_results: Dict[str, Dict[str, object]] = {}
        for payload in payloads:
            for result in payload.get("results", []):
                entity_uuid = str(result.get("entity_uuid") or "")
                key = entity_uuid or f"entity-{len(merged_results)}"
                if key not in merged_results:
                    merged_results[key] = {
                        "entity_uuid": result.get("entity_uuid"),
                        "series": [],
                    }
                merged_results[key]["series"].extend(result.get("series", []))
        return {"count": len(merged_results), "results": list(merged_results.values())}

    @staticmethod
    def _metric_groups(metric_ids: List[str]) -> List[List[str]]:
        grouped: Dict[str, List[str]] = {}
        for metric_id in metric_ids:
            prefix = metric_id.split(".", 1)[0]
            grouped.setdefault(prefix, []).append(metric_id)
        return list(grouped.values())

    def _fetch_metric_ids(
        self, endpoint: str, tenant: Dict[str, str], metric_ids: List[str]
    ) -> Tuple[Dict[str, object], str]:
        params = {
            "metric_id": ",".join(metric_ids),
            "step": "300",
            "limit": "1",
            "include_name": "true",
        }

        last_error: Exception | None = None
        last_empty_payload: Dict[str, object] | None = None
        last_empty_scope = ""
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
                payload = response.json()
                _, data_series, _ = self._payload_stats(payload)
                if data_series > 0:
                    return payload, scope

                if self.scope_mode != "auto":
                    print(
                        f"WARNING: empty metrics payload for tenant {tenant['name']} "
                        f"({tenant['uuid']}), endpoint={endpoint}, scope={scope}",
                        file=sys.stderr,
                    )
                    return payload, scope

                last_empty_payload = payload
                last_empty_scope = scope
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                if self.scope_mode != "auto":
                    break

        if last_empty_payload is not None:
            if last_error is not None:
                print(
                    f"WARNING: no data in auto scope attempts for tenant "
                    f"{tenant['name']} ({tenant['uuid']}), endpoint={endpoint}; "
                    f"last error={last_error}",
                    file=sys.stderr,
                )
            return last_empty_payload, last_empty_scope

        if last_error is None:
            raise RuntimeError("metrics request failed without error")
        raise last_error

    def fetch_endpoint(
        self, endpoint: str, tenant: Dict[str, str]
    ) -> Tuple[Dict[str, object], str]:
        metric_ids = METRIC_IDS[endpoint]
        grouped_metric_ids = self._metric_groups(metric_ids)
        combined_error: Exception | None = None
        combined_payload: Dict[str, object] | None = None
        combined_scope = "none"

        try:
            payload, scope = self._fetch_metric_ids(endpoint, tenant, metric_ids)
            combined_payload = payload
            combined_scope = scope
            _, data_series, _ = self._payload_stats(payload)
            if data_series > 0 or not self.metric_batching or len(grouped_metric_ids) <= 1:
                return payload, scope
            print(
                f"WARNING: empty combined metric payload for tenant {tenant['name']} "
                f"({tenant['uuid']}), endpoint={endpoint}; trying metric batching",
                file=sys.stderr,
            )
        except Exception as exc:  # noqa: BLE001
            if not self.metric_batching or len(grouped_metric_ids) <= 1:
                raise
            combined_error = exc
            print(
                f"WARNING: combined metrics request failed for tenant {tenant['name']} "
                f"({tenant['uuid']}), endpoint={endpoint}; trying metric batching: {exc}",
                file=sys.stderr,
            )

        batched_payloads: List[Dict[str, object]] = []
        successful_scopes: List[str] = []
        for metric_group in grouped_metric_ids:
            try:
                payload, scope = self._fetch_metric_ids(endpoint, tenant, metric_group)
                _, data_series, _ = self._payload_stats(payload)
                if data_series <= 0:
                    continue
                batched_payloads.append(payload)
                successful_scopes.append(scope)
            except TimeoutError:
                raise
            except Exception as exc:  # noqa: BLE001
                print(
                    f"WARNING: metric batch request failed for tenant "
                    f"{tenant['name']} ({tenant['uuid']}), endpoint={endpoint}, "
                    f"metric_ids={','.join(metric_group)}: {exc}",
                    file=sys.stderr,
                )

        if not batched_payloads:
            if combined_error is not None:
                raise combined_error
            if combined_payload is not None:
                return combined_payload, combined_scope
            return {"count": 0, "results": []}, "none"

        merged = self._merge_payloads(batched_payloads)
        deduped_scopes = sorted({scope for scope in successful_scopes if scope})
        return merged, "+".join(deduped_scopes) if deduped_scopes else "none"

    def _fetch_inventory_scope(
        self, path: str, tenant: Dict[str, str], scope: str
    ) -> Tuple[bool, List[Dict[str, object]]] | None:
        """Fetch one inventory path with one tenant scope.

        Returns ``(not_found, results)`` where ``not_found`` is True when the
        controller returned 404 (the path form is wrong for this version), or
        ``None`` on any other error so the caller can try the next scope.
        """
        results: List[Dict[str, object]] = []
        next_path = path
        params: Dict[str, str] = {
            "include_name": "true",
            "page_size": str(self.inventory_page_size),
        }
        headers: Dict[str, str] = {"X-Avi-Version": self.api_version}
        self._add_scope(scope, tenant, headers, params)
        try:
            while next_path:
                response = self._request(
                    "GET", next_path, params=params, headers=headers
                )
                payload = response.json()
                for item in payload.get("results", []):
                    if isinstance(item, dict):
                        results.append(item)
                next_url = payload.get("next")
                if not next_url:
                    break
                parsed = urlsplit(str(next_url))
                next_path = parsed.path or path
                params = dict(parse_qsl(parsed.query, keep_blank_values=True))
                params.setdefault("include_name", "true")
            return False, results
        except requests.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else None
            if status == 404:
                # Wrong path form for this controller version; signal fallback.
                return True, []
            print(
                f"WARNING: inventory request failed for tenant {tenant['name']} "
                f"({tenant['uuid']}), path={path}, scope={scope}: {exc}",
                file=sys.stderr,
            )
            return None
        except Exception as exc:  # noqa: BLE001
            print(
                f"WARNING: inventory request failed for tenant {tenant['name']} "
                f"({tenant['uuid']}), path={path}, scope={scope}: {exc}",
                file=sys.stderr,
            )
            return None

    def fetch_inventory(
        self, endpoint: str, tenant: Dict[str, str]
    ) -> Dict[str, Dict[str, Dict[str, object]]]:
        """Return {entity_uuid: {"tags": {...}, "fields": {...}}} for an endpoint."""
        candidates = INVENTORY_ENDPOINTS.get(endpoint)
        if not candidates:
            return {}

        # Prefer a path we've already confirmed works on this controller.
        cached = self._inventory_path_cache.get(endpoint)
        if cached:
            ordered = [cached] + [p for p in candidates if p != cached]
        else:
            ordered = list(candidates)

        for path in ordered:
            path_found = False
            for scope in self._scope_attempts():
                outcome = self._fetch_inventory_scope(path, tenant, scope)
                if outcome is None:
                    continue  # transient/other error: try next scope
                not_found, results = outcome
                if not_found:
                    break  # wrong path form: stop scopes, try next candidate
                path_found = True
                self._inventory_path_cache[endpoint] = path
                if results:
                    return _parse_inventory(endpoint, results)
                if self.scope_mode != "auto":
                    return {}
            if path_found:
                # Path exists but returned no entities under any scope.
                return {}
        print(
            f"WARNING: no inventory path matched for {endpoint} "
            f"(tried {', '.join(ordered)}); names/state/relationships unavailable",
            file=sys.stderr,
        )
        return {}

    def fetch_cluster(self) -> Dict[str, Dict[str, object]]:
        """Return controller (cluster) name + state for enriching controller metrics.

        The controller has no per-tenant inventory endpoint; its friendly name and
        operational state come from /api/cluster and /api/cluster/runtime. Result is
        {"tags": {name, cluster_state, controller_node}, "fields": {up, node_count}}.
        Cached because the cluster is global (not per-tenant).
        """
        if self._cluster_info is not None:
            return self._cluster_info

        info: Dict[str, Dict[str, object]] = {"tags": {}, "fields": {}}
        headers = {"X-Avi-Version": self.api_version}
        try:
            cluster = self._request(
                "GET", "/api/cluster", headers=headers
            ).json()
            name = cluster.get("name")
            if name:
                info["tags"]["name"] = str(name)
            nodes = cluster.get("nodes")
            if isinstance(nodes, list) and nodes:
                first = nodes[0] if isinstance(nodes[0], dict) else {}
                node_name = first.get("name") or (
                    first.get("ip", {}).get("addr")
                    if isinstance(first.get("ip"), dict)
                    else None
                )
                if node_name:
                    info["tags"]["controller_node"] = str(node_name)
                info["fields"]["node_count"] = len(nodes)
        except Exception as exc:  # noqa: BLE001
            print(f"WARNING: /api/cluster fetch failed: {exc}", file=sys.stderr)

        try:
            runtime = self._request(
                "GET", "/api/cluster/runtime", headers=headers
            ).json()
            state = (runtime.get("cluster_state") or {}).get("state")
            if state:
                info["tags"]["cluster_state"] = str(state)
                info["fields"]["up"] = 1 if str(state).startswith("CLUSTER_UP") else 0
            if "node_count" not in info["fields"]:
                count = runtime.get("nodes_count")
                if isinstance(count, (int, float)):
                    info["fields"]["node_count"] = int(count)
        except Exception as exc:  # noqa: BLE001
            print(f"WARNING: /api/cluster/runtime fetch failed: {exc}", file=sys.stderr)

        self._cluster_info = info
        return info


def _parse_inventory(
    endpoint: str, results: List[Dict[str, object]]
) -> Dict[str, Dict[str, Dict[str, object]]]:
    lookup: Dict[str, Dict[str, Dict[str, object]]] = {}
    for item in results:
        config = item.get("config") if isinstance(item.get("config"), dict) else {}
        runtime = item.get("runtime") if isinstance(item.get("runtime"), dict) else {}
        entity_uuid = str(item.get("uuid") or config.get("uuid") or "")
        if not entity_uuid:
            entity_uuid, _ = parse_ref(item.get("url") or config.get("url"))
        if not entity_uuid:
            continue

        tags: Dict[str, object] = {}
        fields: Dict[str, object] = {}

        name = config.get("name")
        if name:
            tags["name"] = str(name)

        oper_status = runtime.get("oper_status")
        state = oper_status.get("state") if isinstance(oper_status, dict) else None
        if state:
            tags["oper_status"] = str(state)
            fields.update(oper_status_fields(state))

        # Descriptors common to every inventoried entity.
        health = item.get("health_score")
        if isinstance(health, dict) and isinstance(
            health.get("health_score"), (int, float)
        ):
            fields["health_score"] = float(health["health_score"])
        alert = item.get("alert")
        if isinstance(alert, dict) and alert.get("level"):
            tags["alert_level"] = str(alert["level"])
        cloud_name = ref_name(config.get("cloud_ref"))
        if cloud_name:
            tags["cloud_name"] = cloud_name
        app_profile_type = item.get("app_profile_type")
        if app_profile_type:
            tags["app_profile_type"] = str(app_profile_type)

        if endpoint == "virtualservice":
            pool_uuid, pool_name = vs_pool_link(item, config)
            if pool_uuid:
                tags["pool_uuid"] = pool_uuid
            if pool_name:
                tags["pool_name"] = pool_name
            fqdn = config.get("fqdn")
            if fqdn:
                tags["fqdn"] = str(fqdn)
            vip = first_vip_address(config)
            if vip:
                tags["vip_address"] = vip
            vs_type = config.get("type")
            if vs_type:
                tags["vs_type"] = str(vs_type)
            se_group_name = ref_name(config.get("se_group_ref"))
            if se_group_name:
                tags["se_group_name"] = se_group_name
            enabled = config.get("enabled")
            if enabled is not None:
                fields["admin_enabled"] = 1 if enabled else 0
            percent_ses_up = runtime.get("percent_ses_up")
            if isinstance(percent_ses_up, (int, float)):
                fields["percent_ses_up"] = float(percent_ses_up)
        elif endpoint == "pool":
            vslist = item.get("virtualservices")
            if isinstance(vslist, list) and vslist:
                first = vslist[0] if isinstance(vslist[0], dict) else {}
                vs_uuid, vs_name = parse_ref(first.get("ref"))
                if vs_uuid:
                    tags["virtualservice_uuid"] = vs_uuid
                if vs_name:
                    tags["virtualservice_name"] = vs_name
                fields["num_virtualservices"] = len(vslist)
            for key in (
                "num_servers",
                "num_servers_up",
                "num_servers_enabled",
                "percent_servers_up_total",
                "percent_servers_up_enabled",
            ):
                value = runtime.get(key)
                if isinstance(value, (int, float)):
                    fields[key] = float(value)
        elif endpoint == "serviceengine":
            enable_state = config.get("enable_state")
            if enable_state:
                tags["enable_state"] = str(enable_state)
                fields["admin_enabled"] = 1 if enable_state == "SE_STATE_ENABLED" else 0
            mgmt_ip = config.get("mgmt_ip_address")
            addr = mgmt_ip.get("addr") if isinstance(mgmt_ip, dict) else None
            if addr:
                tags["mgmt_ip"] = str(addr)
            se_group_name = ref_name(config.get("se_group_ref"))
            if se_group_name:
                tags["se_group_name"] = se_group_name
            host_name = ref_name(config.get("host_ref"))
            if host_name:
                tags["host_name"] = host_name
            vs_refs = config.get("vs_refs")
            if isinstance(vs_refs, list):
                fields["num_virtualservices"] = len(vs_refs)

        lookup[entity_uuid] = {"tags": tags, "fields": fields}
    return lookup


def build_line_protocol(
    tenant_lookup: Dict[str, str],
    endpoint: str,
    tenant: Dict[str, str],
    payload: Dict[str, object],
    enrichment: Dict[str, Dict[str, Dict[str, object]]] | None = None,
    default_tags: Dict[str, object] | None = None,
    default_fields: Dict[str, object] | None = None,
) -> List[str]:
    measurement = MEASUREMENTS[endpoint]
    enrichment = enrichment or {}
    default_tags = default_tags or {}
    default_fields = default_fields or {}
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
            for tag_key, tag_value in default_tags.items():
                if tag_value is not None and str(tag_value) != "":
                    tags[tag_key] = tag_value
            entry = enrichment.get(str(entity_uuid)) if entity_uuid else None
            if entry:
                for tag_key, tag_value in entry.get("tags", {}).items():
                    tags[tag_key] = tag_value
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

    if default_fields:
        for fields in records.values():
            for field_key, field_value in default_fields.items():
                fields.setdefault(field_key, field_value)

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


def build_inventory_lines(
    tenant_lookup: Dict[str, str],
    endpoint: str,
    tenant: Dict[str, str],
    enrichment: Dict[str, Dict[str, Dict[str, object]]],
) -> List[str]:
    """Emit one state record per inventoried entity.

    Ensures every entity carries its name plus numeric state fields (up,
    oper_status_code, server counts) even when it has no analytics data.
    """
    measurement = MEASUREMENTS[endpoint]
    tenant_uuid = tenant["uuid"]
    tenant_name = tenant_lookup.get(tenant_uuid, tenant.get("name"))
    timestamp_ns = time.time_ns()

    lines: List[str] = []
    for entity_uuid, entry in enrichment.items():
        fields = entry.get("fields", {})
        if not fields:
            continue
        tags = {
            "entity_uuid": entity_uuid,
            "tenant_uuid": tenant_uuid,
            "tenant_name": tenant_name,
        }
        for tag_key, tag_value in entry.get("tags", {}).items():
            tags[tag_key] = tag_value
        tag_items = sorted(
            (k, str(v)) for k, v in tags.items() if v is not None and str(v) != ""
        )
        tag_text = ",".join(
            f"{escape_tag_or_key(k)}={escape_tag_or_key(v)}" for k, v in tag_items
        )
        field_text = ",".join(
            f"{escape_tag_or_key(k)}={encode_field_value(v)}"
            for k, v in sorted(fields.items())
        )
        line = escape_measurement(measurement)
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
    controller_info: Dict[str, Dict[str, object]] = {"tags": {}, "fields": {}}
    if collector.collect_inventory:
        try:
            controller_info = collector.fetch_cluster()
            print(
                "INFO: controller cluster "
                f"name={controller_info.get('tags', {}).get('name')}, "
                f"state={controller_info.get('tags', {}).get('cluster_state')}",
                file=sys.stderr,
            )
        except Exception as exc:  # noqa: BLE001
            print(f"WARNING: controller cluster info unavailable: {exc}", file=sys.stderr)
    lines: List[str] = []
    successful_requests = 0
    deadline_hit = False

    for tenant in tenants:
        inventory_by_endpoint: Dict[str, Dict[str, Dict[str, Dict[str, object]]]] = {}
        if collector.collect_inventory:
            for endpoint in INVENTORY_ENDPOINTS:
                try:
                    inventory = collector.fetch_inventory(endpoint, tenant)
                except TimeoutError as exc:
                    print(
                        f"ERROR: timeout collecting {endpoint} inventory for tenant "
                        f"{tenant['uuid']}: {exc}",
                        file=sys.stderr,
                    )
                    deadline_hit = True
                    break
                except Exception as exc:  # noqa: BLE001
                    print(
                        f"ERROR: failed collecting {endpoint} inventory for tenant "
                        f"{tenant['uuid']} ({tenant['name']}): {exc}",
                        file=sys.stderr,
                    )
                    continue
                inventory_by_endpoint[endpoint] = inventory
                print(
                    f"INFO: tenant={tenant['name']} ({tenant['uuid']}), "
                    f"inventory={endpoint}, entities={len(inventory)}",
                    file=sys.stderr,
                )
                lines.extend(
                    build_inventory_lines(
                        tenant_lookup, endpoint, tenant, inventory
                    )
                )
            if deadline_hit:
                print(
                    "WARNING: overall collection deadline reached; "
                    "emitting partial results",
                    file=sys.stderr,
                )
                break

        for endpoint in MEASUREMENTS:
            try:
                payload, successful_scope = collector.fetch_endpoint(endpoint, tenant)
                series_count, data_series_count, point_count = collector._payload_stats(
                    payload
                )
                print(
                    f"INFO: tenant={tenant['name']} ({tenant['uuid']}), "
                    f"endpoint={endpoint}, scope={successful_scope}, "
                    f"series={series_count}, data_series={data_series_count}, "
                    f"points={point_count}",
                    file=sys.stderr,
                )
                lines.extend(
                    build_line_protocol(
                        tenant_lookup,
                        endpoint,
                        tenant,
                        payload,
                        inventory_by_endpoint.get(endpoint),
                        default_tags=(
                            controller_info.get("tags")
                            if endpoint == "controller"
                            else None
                        ),
                        default_fields=(
                            controller_info.get("fields")
                            if endpoint == "controller"
                            else None
                        ),
                    )
                )
                successful_requests += 1
            except TimeoutError as exc:
                print(
                    f"ERROR: timeout collecting {endpoint} metrics for tenant "
                    f"{tenant['uuid']}: {exc}",
                    file=sys.stderr,
                )
                deadline_hit = True
                break
            except Exception as exc:  # noqa: BLE001
                print(
                    f"ERROR: failed collecting {endpoint} metrics for tenant "
                    f"{tenant['uuid']} ({tenant['name']}): {exc}",
                    file=sys.stderr,
                )
        if deadline_hit:
            print(
                "WARNING: overall collection deadline reached; emitting partial results",
                file=sys.stderr,
            )
            break

    if lines:
        print("\n".join(lines))

    if successful_requests == 0:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
