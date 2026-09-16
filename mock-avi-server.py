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

ENTITIES = {
    "virtualservice": [
        {
            "name": "web-app-vs",
            "uuid": "virtualservice-web-app-uuid-1234",
            "tenant": TENANTS[0]["uuid"],
            "tenant_name": TENANTS[0]["name"],
        },
        {
            "name": "api-vs",
            "uuid": "virtualservice-api-uuid-5678",
            "tenant": TENANTS[1]["uuid"],
            "tenant_name": TENANTS[1]["name"],
        },
        {
            "name": "mobile-vs",
            "uuid": "virtualservice-mobile-uuid-9012",
            "tenant": TENANTS[2]["uuid"],
            "tenant_name": TENANTS[2]["name"],
        },
    ],
    "pool": [
        {
            "name": "web-app-pool",
            "uuid": "pool-web-app-uuid-1234",
            "tenant": TENANTS[0]["uuid"],
            "tenant_name": TENANTS[0]["name"],
        },
        {
            "name": "api-pool",
            "uuid": "pool-api-uuid-5678",
            "tenant": TENANTS[1]["uuid"],
            "tenant_name": TENANTS[1]["name"],
        },
        {
            "name": "mobile-pool",
            "uuid": "pool-mobile-uuid-9012",
            "tenant": TENANTS[2]["uuid"],
            "tenant_name": TENANTS[2]["name"],
        },
    ],
    "serviceengine": [
        {
            "name": "se-1",
            "uuid": "serviceengine-uuid-1111",
            "tenant": TENANTS[0]["uuid"],
            "tenant_name": TENANTS[0]["name"],
        },
        {
            "name": "se-2",
            "uuid": "serviceengine-uuid-2222",
            "tenant": TENANTS[1]["uuid"],
            "tenant_name": TENANTS[1]["name"],
        },
        {
            "name": "se-3",
            "uuid": "serviceengine-uuid-3333",
            "tenant": TENANTS[2]["uuid"],
            "tenant_name": TENANTS[2]["name"],
        },
    ],
    "controller": [
        {
            "name": "avi-controller-admin",
            "uuid": "controller-admin-uuid-1234",
            "tenant": TENANTS[0]["uuid"],
            "tenant_name": TENANTS[0]["name"],
        },
        {
            "name": "avi-controller-blue",
            "uuid": "controller-blue-uuid-5678",
            "tenant": TENANTS[1]["uuid"],
            "tenant_name": TENANTS[1]["name"],
        },
        {
            "name": "avi-controller-green",
            "uuid": "controller-green-uuid-9012",
            "tenant": TENANTS[2]["uuid"],
            "tenant_name": TENANTS[2]["name"],
        },
    ],
}


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
    return jsonify(build_results(scoped_entities("controller"), metric_ids))


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
