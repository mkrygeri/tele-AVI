# Measurements & Data Model

This document describes every measurement the AVI → Kentik collector emits, what
tags and fields each one carries, **where each value is sourced** from the AVI
REST API, and **how derived fields are calculated**.

It is a companion to the collector script
[`avi-tenant-metrics.py`](../avi-tenant-metrics.py). If you change the collector,
update the relevant table here.

---

## 1. Measurements at a glance

| Measurement | Emitted for | Primary source |
|-------------|-------------|----------------|
| `/devices/avi/controller` | The controller cluster (one per tenant view) | Analytics + `/api/cluster` |
| `/devices/avi/virtualservice` | Each virtual service | Analytics + VS inventory |
| `/devices/avi/pool` | Each pool | Analytics + pool inventory |
| `/devices/avi/serviceengine` | Each service engine | Analytics + SE inventory |
| `/devices/avi/controller_node` | Each cluster member node | `/api/cluster` + `/api/cluster/runtime` + per-node analytics |
| `/devices/avi/vs_pool_link` | Each (virtual service, pool) association | VS inventory `pools[]` / `poolgroups[]` |

Measurement names follow an OpenConfig-style path. The slash is legal, unescaped,
in Influx line protocol.

---

## 2. Where the data comes from

The collector merges **two** AVI API families (three for the controller) into each
record:

### 2a. Analytics Metrics API — the numeric telemetry

```
GET /api/analytics/metrics/<entity>?metric_id=<csv>&step=300&limit=1&include_name=true
```

- `<entity>` = `virtualservice` | `pool` | `serviceengine` | `controller`
- `step=300` → 5-minute rollup; `limit=1` → most recent point only.
- Response shape: `results[].series[].header.name` (the metric id) plus
  `series[].data[].value` and `series[].data[].timestamp`.
- The metric ids requested per entity are fixed in the `METRIC_IDS` table in the
  collector (see [§4](#4-analytics-metric-fields-per-measurement)).
- **This API returns only `entity_uuid`** — no names, no operational state, no
  relationships. Those come from the Inventory API.

### 2b. Inventory API — names, state, and relationships

```
GET /api/virtualservice-inventory?include_name=true&page_size=200
GET /api/pool-inventory?include_name=true&page_size=200
GET /api/serviceengine-inventory?include_name=true&page_size=200
```

> **Path note:** live 22.1.x controllers serve **only** the hyphenated paths above.
> The short forms (`/api/vsinventory`, …) return `404`. The collector tries
> hyphenated first, then falls back, and caches whichever works.

- `include_name=true` makes every object reference come back as
  `https://host/api/pool/pool-<uuid>#<name>`, so the collector can resolve both a
  UUID and a friendly name from a single ref.
- Response shape per item: `config{…}`, `runtime{…}`, `health_score{…}`,
  `alert{…}`, plus relationship arrays (`pools[]`, `virtualservices[]`, …).
- Results are paginated via the `next` link.

### 2c. Cluster API — controller identity & state (controller only)

```
GET /api/cluster           → uuid, name, nodes[]
GET /api/cluster/runtime    → cluster_state.state, node_states[], nodes_count
```

The controller has no per-tenant inventory endpoint, so its name and state are
sourced here and applied to every controller record.

### 2d. How the sources are joined

- Inventory results are parsed into a lookup keyed by `entity_uuid`.
- When an analytics record is built, its `entity_uuid` is used to merge the
  matching inventory **tags** (name, oper_status, links, …) onto the metric line.
- Controller records additionally receive the cluster name/state as default tags
  and `up`/`node_count` as default fields.

### 2e. Two kinds of records per entity

Each entity can produce **two** line-protocol records:

| Record kind | Built by | Timestamp | Purpose |
|-------------|----------|-----------|---------|
| **State record** | `build_inventory_lines()` | collection time (`now`) | Guarantees the entity appears with its **name + numeric state** even when it has no analytics data. |
| **Metric record** | `build_line_protocol()` | analytics data point time | Carries the actual telemetry values, enriched with the same name/state/relationship tags. |

This is why, in Kentik, a virtual service shows both its state fields
(`up`, `oper_status_code`, `health_score`) and its traffic metrics
(`l4_server_avg_complete_conns`, …).

---

## 3. Tags, field encoding, and derived values

### 3a. Common tags on every record

| Tag | Source |
|-----|--------|
| `entity_uuid` | Analytics `header.entity_uuid` (or `pool_uuid` / `serviceengine_uuid`), or inventory `uuid` |
| `tenant_uuid` | Analytics `header.tenant_uuid` or the tenant being polled |
| `tenant_name` | Analytics `header.tenant_name` or tenant lookup |

Telegraf then adds these **global tags** to every record (from `telegraf.conf`):
`vendor`, `product`, `environment`, `location`, `device_name`, `ip_address`.

### 3b. Field value encoding (Influx line protocol)

| Python type | Encoded as | Example |
|-------------|-----------|---------|
| `int` | integer field (`i` suffix) | `up=1i`, `node_count=1i` |
| `float` | float field | `health_score=100.0` |
| `bool` | boolean | `true` / `false` |
| `str` | quoted string | `"text"` |

Metric values from the analytics API are always coerced to `float`.

### 3c. Metric-name normalization

Analytics metric ids are normalized into field names:

- Controller: the `controller_stats.` prefix is **stripped**
  (`controller_stats.avg_cpu_usage` → `avg_cpu_usage`).
- All entities: remaining dots become underscores
  (`l4_server.avg_complete_conns` → `l4_server_avg_complete_conns`).

### 3d. Derived fields — how they are calculated

| Field | Applies to | Calculation |
|-------|-----------|-------------|
| `up` | VS, pool, SE | `1` if `runtime.oper_status.state == "OPER_UP"`, else `0` |
| `up` | controller | `1` if `cluster_state.state` starts with `CLUSTER_UP`, else `0` |
| `oper_status_code` | VS, pool, SE | Index of `oper_status.state` in the OperationalStatus enum ([§5](#5-operationalstatus-enum)) |
| `admin_enabled` | VS | `1` if `config.enabled` is true, else `0` |
| `admin_enabled` | SE | `1` if `config.enable_state == "SE_STATE_ENABLED"`, else `0` |
| `num_virtualservices` | pool | Length of `runtime.virtualservices[]` |
| `num_virtualservices` | SE | Length of `config.vs_refs[]` |
| `node_count` | controller | Length of `cluster.nodes[]` (fallback `runtime.nodes_count`) |
| `health_score` | VS, pool, SE | `item.health_score.health_score` (0–100), passed through as float |

Object references (`pool_ref`, `cloud_ref`, `se_group_ref`, `host_ref`, …) are
split into a `uuid` and a `#name` suffix; the collector emits the name as a tag
and, where relevant, the uuid as a linking tag.

---

## 4. Analytics metric fields per measurement

These are the metric ids requested from the Analytics API. Each becomes a field
after [normalization](#3c-metric-name-normalization).

### `/devices/avi/virtualservice`

| Metric id | Field name |
|-----------|-----------|
| `l4_client.avg_complete_conns` | `l4_client_avg_complete_conns` |
| `l4_client.avg_new_established_conns` | `l4_client_avg_new_established_conns` |
| `l4_server.avg_complete_conns` | `l4_server_avg_complete_conns` |
| `l4_server.avg_new_established_conns` | `l4_server_avg_new_established_conns` |
| `l4_server.avg_pool_complete_conns` | `l4_server_avg_pool_complete_conns` |
| `l4_server.avg_pool_new_established_conns` | `l4_server_avg_pool_new_established_conns` |
| `l7_server.avg_complete_responses` | `l7_server_avg_complete_responses` |
| `l7_server.avg_client_complete_requests` | `l7_server_avg_client_complete_requests` |

> **Client vs. server side:** `l4_client.*` counts client→VS connections (the
> real VS traffic); `l4_server.*` counts VS→pool (backend) connections and often
> reads `0` for L7 VSes that reuse backend connections. The `avg_pool_*` variants
> are backend/pool-oriented and are most meaningful on the pool measurement.

### `/devices/avi/pool`

| Metric id | Field name |
|-----------|-----------|
| `l4_server.avg_complete_conns` | `l4_server_avg_complete_conns` |
| `l4_server.avg_new_established_conns` | `l4_server_avg_new_established_conns` |
| `l4_server.avg_pool_open_conns` | `l4_server_avg_pool_open_conns` |
| `l4_server.sum_connection_errors` | `l4_server_sum_connection_errors` |

### `/devices/avi/serviceengine`

| Metric id | Field name |
|-----------|-----------|
| `se_stats.avg_cpu_usage` | `se_stats_avg_cpu_usage` |
| `se_stats.avg_mem_usage` | `se_stats_avg_mem_usage` |
| `se_stats.avg_disk_usage` | `se_stats_avg_disk_usage` |
| `se_if.avg_bandwidth` | `se_if_avg_bandwidth` |

### `/devices/avi/controller`

All ids share the `controller_stats.` prefix, which is stripped, leaving fields
such as `avg_cpu_usage`, `avg_mem_usage`, `avg_disk_usage`,
`avg_disk_read_bytes`, `avg_disk_write_bytes`, `avg_num_active_vs`,
`max_num_active_vs`, `avg_num_ses`, `max_num_ses`, `avg_num_se_cores`,
`max_num_se_cores`, `avg_num_service_cores`, `max_num_service_cores`,
`avg_num_sockets`, `max_num_sockets`, `avg_num_backend_servers`,
`max_num_backend_servers`, `avg_total_se_throughput`, `max_total_se_throughput`,
`sum_total_se_bytes`, `sum_total_vs_bytes`, `sum_total_vs_client_bytes`,
`sum_total_vs_usage`, and the license-usage gauges
(`max_num_active_vs_lic_usage`, `max_num_ses_lic_usage`,
`max_num_sockets_lic_usage`, `max_num_service_cores_lic_usage`,
`max_se_cores_lic_usage`, `max_se_throughput_lic_usage`,
`max_be_servers_lic_usage`).

> Many of these read `0` until virtual services / service engines are deployed.

### `/devices/avi/controller_node`

Per-node subset of `controller_stats.*`, fetched from the controller analytics
endpoint filtered by each node's `entity_uuid` (= `vm_uuid`) so the values are for
that individual node, not the cluster aggregate: `avg_cpu_usage`, `avg_mem_usage`,
`avg_disk_usage`, `avg_disk_read_bytes`, `avg_disk_write_bytes`. Field names match
the `controller` measurement, so per-node vs. aggregate can be compared directly.

---

## 5. Per-measurement tag & field reference

The tables below list the **enrichment** tags/fields added from inventory/cluster
data (on top of the common tags in [§3a](#3a-common-tags-on-every-record) and the
analytics fields in [§4](#4-analytics-metric-fields-per-measurement)).

### `/devices/avi/virtualservice`

**Tags**

| Tag | Source | Notes |
|-----|--------|-------|
| `name` | `config.name` | Friendly VS name |
| `oper_status` | `runtime.oper_status.state` | Full enum string (e.g. `OPER_UP`) |
| `pool_uuid` | `config.pool_ref`, else first `pools[]` entry | VS to primary pool link |
| `pool_name` | same ref `#name` | Primary pool name; blank only when the VS has no pool (e.g. `VH_PARENT`) |
| `pool_group_uuid` | first `poolgroups[]` entry | Set when the VS fans out to an array of pools (VS inventory has no `pool_group_ref` in `config`) |
| `pool_group_name` | same ref `#name` | Pool group name (content-switching / SNI) |
| `fqdn` | `config.fqdn` | Configured FQDN |
| `vip_address` | first `config.vip[].ip_address`/`ip6_address` | Service IP |
| `vs_type` | `config.type` | `VS_TYPE_NORMAL` / `VH_PARENT` / `VH_CHILD` |
| `se_group_name` | `config.se_group_ref` `#name` | SE group placement |
| `cloud_name` | `config.cloud_ref` `#name` | Cloud |
| `app_profile_type` | `item.app_profile_type` | e.g. `APPLICATION_PROFILE_TYPE_HTTP` |
| `alert_level` | `item.alert.level` | e.g. `ALERT_HIGH` (present when alerting) |

**Fields**

| Field | Type | Source / derivation |
|-------|------|---------------------|
| `up` | int | Derived from `oper_status` ([§3d](#3d-derived-fields--how-they-are-calculated)) |
| `oper_status_code` | int | Enum index of `oper_status` |
| `health_score` | float | `item.health_score.health_score` |
| `admin_enabled` | int | `1` if `config.enabled` else `0` |
| `num_pools` | int | Count of backend pools the VS references — `pools[]` length (which expands pool-group members), else `1` for a single `pool_ref`, else `0`. **Always emitted** (including `0`) so pool-group / `VH_PARENT` VSes still appear when filtering on `num_pools`. `>1` = array of pools / pool group |
| `percent_ses_up` | float | `runtime.percent_ses_up` |

### `/devices/avi/pool`

**Tags**

| Tag | Source | Notes |
|-----|--------|-------|
| `name` | `config.name` | Friendly pool name |
| `oper_status` | `runtime.oper_status.state` | Full enum string |
| `virtualservice_uuid` | first `virtualservices[].ref` | **Pool → VS link** (first VS only; use `/devices/avi/vs_pool_link` for the complete many-to-many mapping) |
| `virtualservice_name` | same ref `#name` | **Pool → VS link** (first VS only) |
| `cloud_name` | `config.cloud_ref` `#name` | Cloud |
| `app_profile_type` | `item.app_profile_type` | Application profile |
| `alert_level` | `item.alert.level` | Present when alerting |

**Fields**

| Field | Type | Source / derivation |
|-------|------|---------------------|
| `up` | int | Derived from `oper_status` |
| `oper_status_code` | int | Enum index of `oper_status` |
| `health_score` | float | `item.health_score.health_score` |
| `num_virtualservices` | int | Length of `runtime.virtualservices[]` |
| `num_servers` | float | `runtime.num_servers` |
| `num_servers_up` | float | `runtime.num_servers_up` |
| `num_servers_enabled` | float | `runtime.num_servers_enabled` |
| `percent_servers_up_total` | float | `runtime.percent_servers_up_total` |
| `percent_servers_up_enabled` | float | `runtime.percent_servers_up_enabled` |

### `/devices/avi/vs_pool_link`

An **association (edge) record** — one line per `(virtual service, pool)` pair.
Because a metrics model can't hold a many-to-many relationship in single-valued
tags, this measurement makes the mapping joinable from either direction:

- **VS → pools:** filter on `virtualservice_uuid` to list every pool a VS uses
  (a pool-group VS emits one edge per member pool).
- **Pool → VSes:** filter on `pool_uuid` to list every VS that references a pool
  (a shared pool emits one edge per referencing VS).

Sourced from the VS inventory's expanded `pools[]` / `poolgroups[]` arrays, so it
covers direct single pools, pool-group members, and shared pools. `VH_PARENT`
VSes (no backend pools) emit no edges.

**Tags**

| Tag | Source | Notes |
|-----|--------|-------|
| `virtualservice_uuid` | VS `config.uuid` | The VS side of the edge |
| `virtualservice_name` | VS `config.name` | The VS side of the edge |
| `pool_uuid` | member `pools[].ref` | The pool side of the edge |
| `pool_name` | member `pools[].ref` `#name` | The pool side of the edge |
| `pool_group_uuid` | `poolgroups[].ref` | Present when the pool is reached via a pool group |
| `pool_group_name` | `poolgroups[].ref` `#name` | Present when via a pool group |
| `tenant_uuid` | tenant | Scoping tenant |
| `tenant_name` | tenant | Scoping tenant |

**Fields**

| Field | Type | Source / derivation |
|-------|------|---------------------|
| `linked` | int | Constant `1` — presence of the row *is* the association |

### `/devices/avi/serviceengine`

**Tags**

| Tag | Source | Notes |
|-----|--------|-------|
| `name` | `config.name` | Friendly SE name |
| `oper_status` | `runtime.oper_status.state` | Full enum string |
| `enable_state` | `config.enable_state` | e.g. `SE_STATE_ENABLED` |
| `mgmt_ip` | `config.mgmt_ip_address.addr` | Management IP |
| `se_group_name` | `config.se_group_ref` `#name` | SE group |
| `host_name` | `config.host_ref` `#name` | Hypervisor host |
| `cloud_name` | `config.cloud_ref` `#name` | Cloud |
| `alert_level` | `item.alert.level` | Present when alerting |

**Fields**

| Field | Type | Source / derivation |
|-------|------|---------------------|
| `up` | int | Derived from `oper_status` |
| `oper_status_code` | int | Enum index of `oper_status` |
| `health_score` | float | `item.health_score.health_score` |
| `admin_enabled` | int | `1` if `config.enable_state == SE_STATE_ENABLED` else `0` |
| `num_virtualservices` | int | Length of `config.vs_refs[]` (SE ↔ VS count) |

### `/devices/avi/controller`

**Tags** (applied to every controller record)

| Tag | Source | Notes |
|-----|--------|-------|
| `name` | `/api/cluster` `name` | Cluster name (e.g. `cluster-0-1`) |
| `cluster_uuid` | `/api/cluster` `uuid` | Cluster identifier |
| `cluster_state` | `/api/cluster/runtime` `cluster_state.state` | e.g. `CLUSTER_UP_NO_HA` |
| `controller_node` | first `cluster.nodes[].name`/`ip.addr` | First node name (legacy) |
| `node_name` | leader `cluster.nodes[].name` | Joins to `controller_node.node_name` |
| `node_uuid` | leader `cluster.nodes[].vm_uuid` | Node UUID; equals this record's `entity_uuid` and `controller_node.node_uuid` |
| `node_names` | all `cluster.nodes[].name` | Comma-joined; emitted only when the cluster has >1 node |
| `node_uuids` | all `cluster.nodes[].vm_uuid` | Comma-joined; emitted only when the cluster has >1 node |

**Fields**

| Field | Type | Source / derivation |
|-------|------|---------------------|
| `up` | int | `1` if `cluster_state` starts with `CLUSTER_UP` else `0` |
| `node_count` | int | Length of `cluster.nodes[]` (fallback `runtime.nodes_count`) |
| *controller_stats.\** | float | Analytics fields from [§4](#4-analytics-metric-fields-per-measurement) |

### `/devices/avi/controller_node`

One record **per cluster member**, emitted once per run (the cluster is global,
not tenant-scoped). Sourced by joining `/api/cluster` `nodes[]` (name + IP) with
`/api/cluster/runtime` `node_states[]` (role + state), keyed by node name. Falls
back to the runtime node list when `/api/cluster` omits `nodes[]`. Per-node
health metrics are then fetched from `/api/analytics/metrics/controller` filtered
by each node's `entity_uuid` (= its `vm_uuid`), giving individual-node CPU/memory/
disk usage for alerting on a single node rather than the cluster aggregate.

**Tags**

| Tag | Source | Notes |
|-----|--------|-------|
| `node_name` | `nodes[].name` (or runtime `node_states[].name`) | Node identity |
| `node_uuid` | `nodes[].vm_uuid` | Node UUID; equals the controller `entity_uuid` / `node_uuid` |
| `node_ip` | `nodes[].ip.addr`, else `public_ip_or_name` / runtime `mgmt_ip` | Node management IP |
| `cluster_name` | `/api/cluster` `name` | Correlates with the controller `name` tag |
| `role` | `nodes[].role` or runtime `node_states[].role` | e.g. `CLUSTER_LEADER` / follower |
| `node_state` | runtime `node_states[].state` | e.g. `CLUSTER_ACTIVE` (omitted if unknown) |

**Fields**

| Field | Type | Source / derivation |
|-------|------|---------------------|
| `member` | int | Always `1` — guarantees a field and counts configured members |
| `up` | int | `1` if `node_state` contains `ACTIVE` or starts with `CLUSTER_UP`, else `0`. Emitted only when a per-node state is known |
| `avg_cpu_usage` | float | Per-node CPU % — `controller_stats.avg_cpu_usage` filtered by this node's `entity_uuid` |
| `avg_mem_usage` | float | Per-node memory % — `controller_stats.avg_mem_usage` |
| `avg_disk_usage` | float | Per-node disk % — `controller_stats.avg_disk_usage` |
| `avg_disk_read_bytes` | float | Per-node disk read bytes/s — `controller_stats.avg_disk_read_bytes` |
| `avg_disk_write_bytes` | float | Per-node disk write bytes/s — `controller_stats.avg_disk_write_bytes` |

> Per-node metric fields are only present when the analytics endpoint returns data
> for that node; identity + `member`/`up` are always emitted so a node still shows
> up even if its metrics are briefly unavailable.

---

## 6. OperationalStatus enum

`oper_status_code` is the index of the `oper_status` string in this list. The
ordering is fixed in the collector so dashboards and alerts can rely on stable
numeric values.

| Code | State | Code | State |
|-----:|-------|-----:|-------|
| 0 | `OPER_UP` | 10 | `OPER_ERROR_DISABLED` |
| 1 | `OPER_DOWN` | 11 | `OPER_AWAIT_MANUAL_PLACEMENT` |
| 2 | `OPER_CREATING` | 12 | `OPER_UPGRADING` |
| 3 | `OPER_RESOURCES` | 13 | `OPER_SE_PROCESSING` |
| 4 | `OPER_INACTIVE` | 14 | `OPER_PARTITIONED` |
| 5 | `OPER_DISABLED` | 15 | `OPER_DISABLING` |
| 6 | `OPER_UNUSED` | 16 | `OPER_FAILED` |
| 7 | `OPER_UNKNOWN` | 17 | `OPER_UNAVAIL` |
| 8 | `OPER_PROCESSING` | 18 | `OPER_AGGREGATE_DOWN` |
| 9 | `OPER_INITIALIZING` | | |

Alerting tip: `up == 0` flags any non-`OPER_UP` state; use `oper_status_code`
(or the `oper_status` string) to distinguish *why* (e.g. `OPER_DISABLED` = admin
action vs `OPER_RESOURCES` = no SE capacity).

---

## 7. Example records

Line protocol as delivered to Kentik (timestamps trimmed). Global Telegraf tags
omitted for brevity.

**Virtual service — state record + metric record**

```
/devices/avi/virtualservice,name=web-vs,oper_status=OPER_UP,pool_name=web-pool,pool_uuid=pool-051a…,num_pools=1i,vip_address=10.90.0.10,vs_type=VS_TYPE_NORMAL,se_group_name=Default-Group,cloud_name=Default-Cloud,tenant_name=admin,entity_uuid=virtualservice-5813… up=1i,oper_status_code=0i,health_score=100.0,admin_enabled=1i,num_pools=1i,percent_ses_up=100.0
/devices/avi/virtualservice,name=web-vs,pool_name=web-pool,tenant_name=admin,entity_uuid=virtualservice-5813… l4_server_avg_complete_conns=0.0,l7_server_avg_complete_responses=0.0
```

**Pool — state record**

```
/devices/avi/pool,name=web-pool,oper_status=OPER_UP,virtualservice_name=web-vs,cloud_name=Default-Cloud,tenant_name=admin,entity_uuid=pool-051a… up=1i,oper_status_code=0i,health_score=100.0,num_virtualservices=1i,num_servers=2.0,num_servers_up=2.0
```

**VS ↔ Pool — association (edge) records**

```
/devices/avi/vs_pool_link,virtualservice_name=web-vs,virtualservice_uuid=virtualservice-2d2c…,pool_name=web-pool,pool_uuid=pool-09f5…,tenant_name=admin,tenant_uuid=admin linked=1i
/devices/avi/vs_pool_link,virtualservice_name=api-vs,virtualservice_uuid=virtualservice-b0a3…,pool_name=p2,pool_uuid=pool-2…,pool_group_name=blue-pg,pool_group_uuid=pg-blue,tenant_name=tenant-blue,tenant_uuid=tenant-9911… linked=1i
```

**Controller — enriched metric record**

```
/devices/avi/controller,name=cluster-0-1,cluster_uuid=cluster-0407ee32…,cluster_state=CLUSTER_UP_NO_HA,controller_node=198.47.119.104,node_name=198.47.119.104,node_uuid=564d9383…,tenant_name=admin,entity_uuid=564d9383… up=1i,node_count=1i,avg_cpu_usage=5.75,avg_mem_usage=84.0,avg_num_active_vs=4.0
```

**Controller node — per-node record**

```
/devices/avi/controller_node,cluster_name=cluster-0-1,node_name=198.47.119.104,node_uuid=564d9383…,node_ip=198.47.119.104,role=CLUSTER_LEADER,node_state=CLUSTER_ACTIVE avg_cpu_usage=5.2,avg_mem_usage=82.0,avg_disk_usage=20.0,avg_disk_read_bytes=0.0,avg_disk_write_bytes=98539.07,member=1i,up=1i
```

---

## 8. Regenerating / verifying

Run the collector directly to inspect raw line protocol:

```bash
set -a && source .env && set +a
python avi-tenant-metrics.py
```

To validate delivery end-to-end (the project's end goal), send through Telegraf's
Kentik output and confirm `Wrote batch of N metrics` on `outputs.http` with no
`E!` errors. See [DEPLOYMENT.md](DEPLOYMENT.md) for the full Telegraf run.
