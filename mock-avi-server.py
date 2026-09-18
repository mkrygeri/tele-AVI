#!/usr/bin/env python3
"""Mock AVI Controller API server."""

from datetime import datetime, timezone
from functools import wraps
import logging
import random
import uuid as uuidlib

from flask import Flask, jsonify, make_response, request

app = Flask(__name__)
app.json.sort_keys = False

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

USERS = {
    "admin": "admin123",
    "aviuser": "avipass",
}

SESSIONS = set()

TENANTS = [
    {"uuid": "tenant-admin-uuid-0001", "name": "admin", "local": True},
    {"uuid": "tenant-blue-uuid-0002", "name": "tenant-blue", "local": False},
    {"uuid": "tenant-green-uuid-0003", "name": "tenant-green", "local": False},
]
TENANT_BY_NAME = {tenant["name"]: tenant["uuid"] for tenant in TENANTS}

# Cluster / controller identity (a controller cluster is not tenant-scoped).
CLUSTER = {
    "uuid": "cluster-avi-uuid-0001",
    "name": "avi-controller-cluster",
    "nodes": [
        {"name": "avi-node-1", "role": "leader", "ip": {"type": "V4", "addr": "10.90.10.11"}, "vm_uuid": "564d0000-0000-0000-0000-000000000001"},
        {"name": "avi-node-2", "role": "follower", "ip": {"type": "V4", "addr": "10.90.10.12"}, "vm_uuid": "564d0000-0000-0000-0000-000000000002"},
        {"name": "avi-node-3", "role": "follower", "ip": {"type": "V4", "addr": "10.90.10.13"}, "vm_uuid": "564d0000-0000-0000-0000-000000000003"},
    ],
}

# Shared topology objects referenced by inventoried entities.
CLOUD = {"uuid": "cloud-default-uuid", "name": "Default-Cloud"}
SE_GROUP = {"uuid": "segroup-default-uuid", "name": "Default-Group"}
HOST = {"uuid": "host-esxi-uuid", "name": "esxi-host-01"}

# Each tenant hosts multiple applications so the mock emulates a realistic
# multi-tenant controller. Every app yields one virtual service linked to one
# pool, giving explicit VS<->Pool relationships for enrichment testing.
APPS_BY_TENANT = {
    "admin": ["web-app", "checkout", "auth"],
    "tenant-blue": ["api", "payments"],
    "tenant-green": ["mobile", "analytics"],
}


def _build_entities():
    virtualservices = []
    pools = []
    serviceengines = []
    controllers = []

    for tenant in TENANTS:
        tenant_uuid = tenant["uuid"]
        tenant_name = tenant["name"]
        apps = APPS_BY_TENANT.get(tenant_name, [])

        for index, app in enumerate(apps):
            # Mark one entity per tenant DOWN so state reporting is exercised.
            oper_state = "OPER_DOWN" if index == len(apps) - 1 else "OPER_UP"
            vs_uuid = f"virtualservice-{app}-{tenant_name}-uuid"
            pool_uuid = f"pool-{app}-{tenant_name}-uuid"
            vs_name = f"{app}-vs"
            pool_name = f"{app}-pool"

            num_servers = 4
            num_servers_up = 4 if oper_state == "OPER_UP" else 1
            health = 92.0 if oper_state == "OPER_UP" else 41.0
            profile = "APPLICATION_PROFILE_TYPE_HTTP"
            vip = f"10.{TENANTS.index(tenant)}.{index}.100"

            virtualservices.append(
                {
                    "name": vs_name,
                    "uuid": vs_uuid,
                    "tenant": tenant_uuid,
                    "tenant_name": tenant_name,
                    "oper_status": oper_state,
                    "enabled": True,
                    "fqdn": f"{app}.{tenant_name}.example.com",
                    "pool_uuid": pool_uuid,
                    "pool_name": pool_name,
                    "vip": vip,
                    "health_score": health,
                    "app_profile_type": profile,
                }
            )
            pools.append(
                {
                    "name": pool_name,
                    "uuid": pool_uuid,
                    "tenant": tenant_uuid,
                    "tenant_name": tenant_name,
                    "oper_status": oper_state,
                    "num_servers": num_servers,
                    "num_servers_up": num_servers_up,
                    "num_servers_enabled": num_servers,
                    "vs_uuid": vs_uuid,
                    "vs_name": vs_name,
                    "health_score": health,
                    "app_profile_type": profile,
                }
            )

        for se_index in range(1, 3):
            se_state = "OPER_UP"
            serviceengines.append(
                {
                    "name": f"se-{tenant_name}-{se_index}",
                    "uuid": f"serviceengine-{tenant_name}-{se_index}-uuid",
                    "tenant": tenant_uuid,
                    "tenant_name": tenant_name,
                    "oper_status": se_state,
                    "enable_state": "SE_STATE_ENABLED",
                    "mgmt_ip": f"10.{TENANTS.index(tenant)}.{se_index}.10",
                    "health_score": 95.0,
                    "vs_uuids": [
                        f"virtualservice-{app}-{tenant_name}-uuid" for app in apps
                    ],
                }
            )

        controllers.append(
            {
                "name": CLUSTER["name"],
                "uuid": CLUSTER["uuid"],
                "tenant": tenant_uuid,
                "tenant_name": tenant_name,
            }
        )

    return {
        "virtualservice": virtualservices,
        "pool": pools,
        "serviceengine": serviceengines,
        "controller": controllers,
    }


ENTITIES = _build_entities()


def iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")


def require_session(function):
    @wraps(function)
    def wrapper(*args, **kwargs):
        session_id = request.cookies.get("sessionid")
        if session_id and session_id in SESSIONS:
            return function(*args, **kwargs)
        basic = request.authorization
        if basic and USERS.get(basic.username) == basic.password:
            return function(*args, **kwargs)
        return (
            jsonify({"detail": "Authentication credentials were not provided."}),
            401,
        )

    return wrapper


def units_for(metric_id: str) -> str:
    if any(key in metric_id for key in ("cpu", "mem", "disk", "usage")):
        return "PERCENT"
    if "bandwidth" in metric_id:
        return "BITS_PER_SECOND"
    return "METRIC_COUNT"


def value_for(metric_id: str) -> float:
    if "error" in metric_id:
        return random.uniform(0, 5)
    if "cpu" in metric_id:
        return random.uniform(15, 60)
    if "mem" in metric_id:
        return random.uniform(40, 80)
    if "disk" in metric_id:
        return random.uniform(20, 50)
    if "bandwidth" in metric_id:
        return random.uniform(1e6, 5e8)
    if "response" in metric_id:
        return random.uniform(100, 1000)
    if "request" in metric_id:
        return random.uniform(80, 800)
    if "conn" in metric_id:
        return random.uniform(20, 500)
    return random.uniform(10, 100)


def build_results(entities, metric_ids, extra_header=None):
    results = []
    for entity in entities:
        series = []
        for metric_id in metric_ids:
            metric_id = metric_id.strip()
            if not metric_id:
                continue
            header = {
                "name": metric_id,
                "units": units_for(metric_id),
                "entity_uuid": entity["uuid"],
                "tenant_uuid": entity["tenant"],
                "tenant_name": entity.get("tenant_name"),
            }
            if extra_header:
                header.update(extra_header(entity))
            series.append(
                {
                    "header": header,
                    "data": [
                        {
                            "timestamp": iso_now(),
                            "value": round(value_for(metric_id), 2),
                        }
                    ],
                }
            )

        results.append({"entity_uuid": entity["uuid"], "series": series})

    return {"count": len(results), "results": results}


def parse_metrics_request():
    metric_ids = request.args.get("metric_id", "").split(",")
    return metric_ids


def resolve_tenant_scope_uuid():
    tenant_uuid = request.args.get("tenant_uuid") or request.headers.get(
        "X-Avi-Tenant-UUID"
    )
    if tenant_uuid:
        return tenant_uuid

    tenant_name = request.args.get("tenant") or request.headers.get("X-Avi-Tenant")
    if tenant_name:
        return TENANT_BY_NAME.get(tenant_name)

    return None


def scoped_entities(entity_type: str):
    tenant_uuid = resolve_tenant_scope_uuid()
    entities = ENTITIES[entity_type]
    if not tenant_uuid:
        return entities
    return [entity for entity in entities if entity["tenant"] == tenant_uuid]


@app.route("/login", methods=["POST"])
def login():
    data = request.get_json(silent=True) or request.form
    username = (data or {}).get("username")
    password = (data or {}).get("password")
    if USERS.get(username) == password:
        session_id = uuidlib.uuid4().hex
        SESSIONS.add(session_id)
        response = make_response(
            jsonify(
                {
                    "user_initialized": True,
                    "version": {"Product": "controller", "Version": "22.1.4"},
                    "user": {
                        "username": username,
                        "name": username,
                        "is_superuser": True,
                    },
                }
            )
        )
        response.set_cookie("sessionid", session_id)
        response.set_cookie("csrftoken", uuidlib.uuid4().hex)
        logger.info("login success for user %s", username)
        return response

    logger.info("login failed for user %s", username)
    return jsonify({"error": "Invalid credentials"}), 401


@app.route("/logout", methods=["POST"])
def logout():
    session_id = request.cookies.get("sessionid")
    SESSIONS.discard(session_id)
    return jsonify({}), 200


@app.route("/api/tenant", methods=["GET"])
@require_session
def get_tenants():
    return jsonify({"count": len(TENANTS), "results": TENANTS})


@app.route("/api/analytics/metrics/virtualservice", methods=["GET"])
@require_session
def get_virtualservice_metrics():
    logger.info("VirtualService metrics request: %s", dict(request.args))
    metric_ids = parse_metrics_request()
    return jsonify(build_results(scoped_entities("virtualservice"), metric_ids))


@app.route("/api/analytics/metrics/pool", methods=["GET"])
@require_session
def get_pool_metrics():
    logger.info("Pool metrics request: %s", dict(request.args))
    metric_ids = parse_metrics_request()
    return jsonify(
        build_results(
            scoped_entities("pool"),
            metric_ids,
            extra_header=lambda entity: {"pool_uuid": entity["uuid"]},
        )
    )


@app.route("/api/analytics/metrics/serviceengine", methods=["GET"])
@require_session
def get_serviceengine_metrics():
    logger.info("ServiceEngine metrics request: %s", dict(request.args))
    metric_ids = parse_metrics_request()
    return jsonify(
        build_results(
            scoped_entities("serviceengine"),
            metric_ids,
            extra_header=lambda entity: {"serviceengine_uuid": entity["uuid"]},
        )
    )


@app.route("/api/analytics/metrics/controller", methods=["GET"])
@require_session
def get_controller_metrics():
    logger.info("Controller metrics request: %s", dict(request.args))
    metric_ids = parse_metrics_request()
    entity_uuid = request.args.get("entity_uuid")
    if entity_uuid:
        # Per-node controller health: synthesize a series for the requested node
        # UUID (== node vm_uuid) so individual-node CPU/memory/disk can be
        # collected and alerted on, mirroring the live controller.
        tenant_uuid = resolve_tenant_scope_uuid() or TENANTS[0]["uuid"]
        tenant_name = next(
            (t["name"] for t in TENANTS if t["uuid"] == tenant_uuid), None
        )
        node = {
            "uuid": entity_uuid,
            "tenant": tenant_uuid,
            "tenant_name": tenant_name,
        }
        return jsonify(build_results([node], metric_ids))
    return jsonify(build_results(scoped_entities("controller"), metric_ids))


def obj_ref(entity_type: str, entity_uuid: str, name: str | None = None) -> str:
    base = request.host_url.rstrip("/")
    ref = f"{base}/api/{entity_type}/{entity_uuid}"
    if name and request.args.get("include_name", "").lower() in {"true", "1", "yes"}:
        ref += f"#{name}"
    return ref


def build_vs_inventory(entities):
    results = []
    for entity in entities:
        results.append(
            {
                "uuid": entity["uuid"],
                "url": obj_ref("virtualservice", entity["uuid"], entity["name"]),
                "app_profile_type": entity.get("app_profile_type"),
                "config": {
                    "uuid": entity["uuid"],
                    "name": entity["name"],
                    "enabled": entity.get("enabled", True),
                    "fqdn": entity.get("fqdn"),
                    "type": "VS_TYPE_NORMAL",
                    "tenant_ref": obj_ref("tenant", entity["tenant"], entity["tenant_name"]),
                    "pool_ref": obj_ref(
                        "pool", entity["pool_uuid"], entity["pool_name"]
                    ),
                    "cloud_ref": obj_ref("cloud", CLOUD["uuid"], CLOUD["name"]),
                    "se_group_ref": obj_ref(
                        "serviceenginegroup", SE_GROUP["uuid"], SE_GROUP["name"]
                    ),
                    "vip": [
                        {
                            "vip_id": "1",
                            "ip_address": {"addr": entity.get("vip"), "type": "V4"},
                        }
                    ],
                },
                "pools": [
                    {"ref": obj_ref("pool", entity["pool_uuid"], entity["pool_name"])}
                ],
                "health_score": {"health_score": entity.get("health_score", 0)},
                "alert": {"level": "ALERT_HIGH" if entity.get("oper_status") == "OPER_DOWN" else "ALERT_LOW"},
                "runtime": {
                    "oper_status": {"state": entity.get("oper_status", "OPER_UP")},
                    "percent_ses_up": 100 if entity.get("oper_status") == "OPER_UP" else 50,
                },
            }
        )
    return {"count": len(results), "results": results}


def build_pool_inventory(entities):
    results = []
    for entity in entities:
        results.append(
            {
                "uuid": entity["uuid"],
                "url": obj_ref("pool", entity["uuid"], entity["name"]),
                "app_profile_type": entity.get("app_profile_type"),
                "config": {
                    "uuid": entity["uuid"],
                    "name": entity["name"],
                    "tenant_ref": obj_ref("tenant", entity["tenant"], entity["tenant_name"]),
                    "cloud_ref": obj_ref("cloud", CLOUD["uuid"], CLOUD["name"]),
                },
                "virtualservices": [
                    {
                        "ref": obj_ref(
                            "virtualservice", entity["vs_uuid"], entity["vs_name"]
                        )
                    }
                ],
                "health_score": {"health_score": entity.get("health_score", 0)},
                "runtime": {
                    "oper_status": {"state": entity.get("oper_status", "OPER_UP")},
                    "num_servers": entity.get("num_servers", 0),
                    "num_servers_up": entity.get("num_servers_up", 0),
                    "num_servers_enabled": entity.get("num_servers_enabled", 0),
                    "percent_servers_up_total": int(
                        100
                        * entity.get("num_servers_up", 0)
                        / max(entity.get("num_servers", 1), 1)
                    ),
                    "percent_servers_up_enabled": int(
                        100
                        * entity.get("num_servers_up", 0)
                        / max(entity.get("num_servers_enabled", 1), 1)
                    ),
                },
            }
        )
    return {"count": len(results), "results": results}


def build_se_inventory(entities):
    results = []
    for entity in entities:
        results.append(
            {
                "uuid": entity["uuid"],
                "url": obj_ref("serviceengine", entity["uuid"], entity["name"]),
                "config": {
                    "uuid": entity["uuid"],
                    "name": entity["name"],
                    "enable_state": entity.get("enable_state", "SE_STATE_ENABLED"),
                    "mgmt_ip_address": {
                        "addr": entity.get("mgmt_ip", "0.0.0.0"),
                        "type": "V4",
                    },
                    "cloud_ref": obj_ref("cloud", CLOUD["uuid"], CLOUD["name"]),
                    "se_group_ref": obj_ref(
                        "serviceenginegroup", SE_GROUP["uuid"], SE_GROUP["name"]
                    ),
                    "host_ref": obj_ref(
                        "vimgrhostruntime", HOST["uuid"], HOST["name"]
                    ),
                    "vs_refs": [
                        obj_ref("virtualservice", vs_uuid)
                        for vs_uuid in entity.get("vs_uuids", [])
                    ],
                    "tenant_ref": obj_ref("tenant", entity["tenant"], entity["tenant_name"]),
                },
                "health_score": {"health_score": entity.get("health_score", 0)},
                "runtime": {
                    "oper_status": {"state": entity.get("oper_status", "OPER_UP")},
                    "power_state": "SE_POWER_ON",
                    "se_connected": True,
                },
            }
        )
    return {"count": len(results), "results": results}


@app.route("/api/vsinventory", methods=["GET"])
@app.route("/api/virtualservice-inventory", methods=["GET"])
@require_session
def get_vs_inventory():
    logger.info("VS inventory request: %s", dict(request.args))
    return jsonify(build_vs_inventory(scoped_entities("virtualservice")))


@app.route("/api/poolinventory", methods=["GET"])
@app.route("/api/pool-inventory", methods=["GET"])
@require_session
def get_pool_inventory():
    logger.info("Pool inventory request: %s", dict(request.args))
    return jsonify(build_pool_inventory(scoped_entities("pool")))


@app.route("/api/serviceengineinventory", methods=["GET"])
@app.route("/api/serviceengine-inventory", methods=["GET"])
@require_session
def get_se_inventory():
    logger.info("ServiceEngine inventory request: %s", dict(request.args))
    return jsonify(build_se_inventory(scoped_entities("serviceengine")))


@app.route("/api/cluster", methods=["GET"])
@require_session
def get_cluster():
    return jsonify(
        {
            "uuid": CLUSTER["uuid"],
            "name": CLUSTER["name"],
            "nodes": CLUSTER["nodes"],
        }
    )


@app.route("/api/cluster/runtime", methods=["GET"])
@require_session
def get_cluster_runtime():
    return jsonify(
        {
            "node_states": [
                {
                    "name": node["name"],
                    "role": node["role"],
                    "state": "CLUSTER_ACTIVE",
                    "mgmt_ip": node.get("ip", {}).get("addr"),
                }
                for node in CLUSTER["nodes"]
            ],
            "cluster_state": {"state": "CLUSTER_UP_HA_ACTIVE"},
        }
    )


@app.route("/health", methods=["GET"])
def health_check():
    return jsonify({"status": "healthy", "timestamp": iso_now(), "version": "22.1.4"})


@app.route("/", methods=["GET"])
def index():
    return jsonify(
        {
            "name": "Mock AVI Controller API",
            "version": "22.1.4",
            "description": (
                "Mock server for testing AVI Load Balancer Telegraf integration"
            ),
            "endpoints": [
                "POST /login",
                "/api/tenant",
                "/api/analytics/metrics/virtualservice",
                "/api/analytics/metrics/pool",
                "/api/analytics/metrics/serviceengine",
                "/api/analytics/metrics/controller",
                "/api/vsinventory",
                "/api/poolinventory",
                "/api/serviceengineinventory",
                "/api/cluster",
                "/api/cluster/runtime",
                "/health",
            ],
            "authentication": (
                "Session login via POST /login (admin:admin123 or aviuser:avipass); "
                "Basic Auth accepted as fallback"
            ),
        }
    )


@app.errorhandler(401)
def unauthorized(error):
    del error
    return jsonify({"detail": "Authentication credentials were not provided."}), 401


@app.errorhandler(404)
def not_found(error):
    del error
    return jsonify({"error": "Endpoint not found"}), 404


if __name__ == "__main__":
    print("🚀 Starting Mock AVI Controller API Server (emulating AVI 22.1.4)")
    print("📋 Credentials: admin:admin123 or aviuser:avipass")
    print("🔐 Auth: POST /login (session cookie); Basic Auth accepted as fallback")
    print("🔗 API available at: https://localhost:8443")
    print("💡 Use 'Ctrl+C' to stop the server")

    app.run(host="0.0.0.0", port=8443, debug=True, ssl_context="adhoc")
