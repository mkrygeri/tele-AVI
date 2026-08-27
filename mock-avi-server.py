#!/usr/bin/env python3
"""
Mock AVI Controller API Server

Emulates the parts of the VMware AVI (NSX ALB) Controller 22.1.4 REST API that
the Telegraf configuration in this repo depends on:

  * Session login:  POST /login  (JSON body {"username","password"}) -> sets a
    `sessionid` + `csrftoken` cookie.  AVI does NOT accept HTTP Basic Auth by
    default, so the metric endpoints require the session cookie.  (HTTP Basic
    Auth is still accepted here as a convenience fallback for ad-hoc testing.)
  * Analytics metrics:  GET /api/analytics/metrics/<entity>  returning the real
    AVI response shape:
        { "count": N, "results": [ { "entity_uuid": "..",
            "series": [ { "header": { "name": "<metric_id>", "units": "..",
                                      "entity_uuid": "..", .. },
                          "data":   [ { "timestamp": "<ISO8601>",
                                        "value": <number> } ] } ] } ] }

This mirrors swagger/metrics.yaml (MetricsQueryResponse) so the same Telegraf
config works against both this mock and a real controller.
"""

from flask import Flask, jsonify, request, make_response
import random
import logging
import uuid as uuidlib
from functools import wraps
from datetime import datetime, timezone

app = Flask(__name__)
# Preserve dict insertion order (real AVI returns "header" before "data"; the
# telegraf json_v2 object parser is sensitive to this key order).
app.json.sort_keys = False

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Mock credentials
USERS = {
    "admin": "admin123",
    "aviuser": "avipass",
}

# Valid session ids handed out by /login
SESSIONS = set()


def iso_now():
    """Timestamp in AVI's ISO-8601 UTC format, e.g. 2026-08-27T00:30:00+00:00."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")


def require_session(f):
    """Allow a valid AVI session cookie or (as a fallback) HTTP Basic Auth."""
    @wraps(f)
    def wrapper(*args, **kwargs):
        sid = request.cookies.get("sessionid")
        if sid and sid in SESSIONS:
            return f(*args, **kwargs)
        basic = request.authorization
        if basic and USERS.get(basic.username) == basic.password:
            return f(*args, **kwargs)
        return jsonify({"detail": "Authentication credentials were not provided."}), 401
    return wrapper


def units_for(metric_id):
    if "cpu" in metric_id or "mem" in metric_id or "disk" in metric_id or "usage" in metric_id:
        return "PERCENT"
    if "bandwidth" in metric_id:
        return "BITS_PER_SECOND"
    return "METRIC_COUNT"


def value_for(metric_id):
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


def build_results(entities, metric_ids, limit, extra_header=None):
    """Build a real-AVI MetricsQueryResponse for the given entities/metrics.

    A real operational controller reports every configured entity, so all
    entities are returned. `limit` mirrors AVI semantics (data points per
    series); we emit the latest sample, which is what limit=1 requests.
    """
    results = []
    for ent in entities:
        series = []
        for metric_id in metric_ids:
            metric_id = metric_id.strip()
            if not metric_id:
                continue
            header = {
                "name": metric_id,
                "units": units_for(metric_id),
                "entity_uuid": ent["uuid"],
                "tenant_uuid": ent.get("tenant", "admin"),
            }
            if extra_header:
                header.update(extra_header(ent))
            series.append({
                "header": header,
                "data": [{"timestamp": iso_now(), "value": round(value_for(metric_id), 2)}],
            })
        results.append({"entity_uuid": ent["uuid"], "series": series})
    return {"count": len(results), "results": results}


def parse_metrics_request():
    metric_ids = request.args.get("metric_id", "").split(",")
    limit = int(request.args.get("limit", 1) or 1)
    return metric_ids, limit


@app.route("/login", methods=["POST"])
def login():
    """AVI session login. Accepts JSON or form-encoded username/password."""
    data = request.get_json(silent=True) or request.form
    username = (data or {}).get("username")
    password = (data or {}).get("password")
    if USERS.get(username) == password:
        sid = uuidlib.uuid4().hex
        SESSIONS.add(sid)
        resp = make_response(jsonify({
            "user_initialized": True,
            "version": {"Product": "controller", "Version": "22.1.4"},
            "user": {"username": username, "name": username, "is_superuser": True},
        }))
        resp.set_cookie("sessionid", sid)
        resp.set_cookie("csrftoken", uuidlib.uuid4().hex)
        logger.info("login success for user %s", username)
        return resp
    logger.info("login failed for user %s", username)
    return jsonify({"error": "Invalid credentials"}), 401


@app.route("/logout", methods=["POST"])
def logout():
    sid = request.cookies.get("sessionid")
    SESSIONS.discard(sid)
    return jsonify({}), 200


@app.route("/api/tenant", methods=["GET"])
@require_session
def get_tenants():
    return jsonify({
        "count": 1,
        "results": [
            {"uuid": "admin", "name": "admin", "local": True},
        ],
    })


@app.route("/api/analytics/metrics/virtualservice", methods=["GET"])
@require_session
def get_virtualservice_metrics():
    logger.info("VirtualService metrics request: %s", dict(request.args))
    metric_ids, limit = parse_metrics_request()
    entities = [
        {"name": "web-app-vs", "uuid": "virtualservice-web-app-uuid-1234", "tenant": "admin"},
        {"name": "api-vs", "uuid": "virtualservice-api-uuid-5678", "tenant": "admin"},
        {"name": "mobile-vs", "uuid": "virtualservice-mobile-uuid-9012", "tenant": "admin"},
        {"name": "auth-vs", "uuid": "virtualservice-auth-uuid-3456", "tenant": "admin"},
        {"name": "checkout-vs", "uuid": "virtualservice-checkout-uuid-7890", "tenant": "admin"},
    ]
    return jsonify(build_results(entities, metric_ids, limit))


@app.route("/api/analytics/metrics/pool", methods=["GET"])
@require_session
def get_pool_metrics():
    logger.info("Pool metrics request: %s", dict(request.args))
    metric_ids, limit = parse_metrics_request()
    entities = [
        {"name": "web-app-pool", "uuid": "pool-web-app-uuid-1234", "tenant": "admin"},
        {"name": "api-pool", "uuid": "pool-api-uuid-5678", "tenant": "admin"},
        {"name": "mobile-pool", "uuid": "pool-mobile-uuid-9012", "tenant": "admin"},
        {"name": "auth-pool", "uuid": "pool-auth-uuid-3456", "tenant": "admin"},
        {"name": "database-pool", "uuid": "pool-db-uuid-7890", "tenant": "admin"},
    ]
    return jsonify(build_results(
        entities, metric_ids, limit,
        extra_header=lambda ent: {"pool_uuid": ent["uuid"]},
    ))


@app.route("/api/analytics/metrics/serviceengine", methods=["GET"])
@require_session
def get_serviceengine_metrics():
    logger.info("ServiceEngine metrics request: %s", dict(request.args))
    metric_ids, limit = parse_metrics_request()
    entities = [
        {"name": "se-1", "uuid": "serviceengine-uuid-1111", "tenant": "admin"},
        {"name": "se-2", "uuid": "serviceengine-uuid-2222", "tenant": "admin"},
        {"name": "se-3", "uuid": "serviceengine-uuid-3333", "tenant": "admin"},
    ]
    return jsonify(build_results(
        entities, metric_ids, limit,
        extra_header=lambda ent: {"serviceengine_uuid": ent["uuid"]},
    ))


@app.route("/api/analytics/metrics/controller", methods=["GET"])
@require_session
def get_controller_metrics():
    logger.info("Controller metrics request: %s", dict(request.args))
    metric_ids, limit = parse_metrics_request()
    entities = [
        {"name": "avi-controller-1", "uuid": "controller-uuid-1234-primary"},
    ]
    return jsonify(build_results(entities, metric_ids, limit))


@app.route("/health", methods=["GET"])
def health_check():
    return jsonify({"status": "healthy", "timestamp": iso_now(), "version": "mock-avi-22.1.4"})


@app.route("/", methods=["GET"])
def index():
    return jsonify({
        "name": "Mock AVI Controller API",
        "version": "22.1.4",
        "description": "Mock server for testing AVI Load Balancer Telegraf integration",
        "endpoints": [
            "POST /login",
            "/api/tenant",
            "/api/analytics/metrics/virtualservice",
            "/api/analytics/metrics/pool",
            "/api/analytics/metrics/serviceengine",
            "/api/analytics/metrics/controller",
            "/health",
        ],
        "authentication": "Session login via POST /login (admin:admin123 or aviuser:avipass); Basic Auth accepted as fallback",
    })


@app.errorhandler(401)
def unauthorized(error):
    return jsonify({"detail": "Authentication credentials were not provided."}), 401


@app.errorhandler(404)
def not_found(error):
    return jsonify({"error": "Endpoint not found"}), 404


if __name__ == "__main__":
    print("🚀 Starting Mock AVI Controller API Server (emulating AVI 22.1.4)")
    print("📋 Credentials: admin:admin123 or aviuser:avipass")
    print("🔐 Auth: POST /login (session cookie); Basic Auth accepted as fallback")
    print("🔗 API available at: https://localhost:8443")
    print("💡 Use 'Ctrl+C' to stop the server")

    app.run(
        host="0.0.0.0",
        port=8443,
        debug=True,
        ssl_context="adhoc",  # self-signed cert for HTTPS
    )
