# Capacity Plan

---

## Load Test Configuration

Tests run with Locust against `http://localhost:5000` (Nginx → 3 × gunicorn app replicas).

**Task weights:**

| Task | Weight | Share |
|------|--------|-------|
| `GET /<short_code>` (redirect) | 3 | 50% |
| `POST /shorten` | 1 | 17% |
| `GET /urls` | 1 | 17% |
| `GET /health` | 1 | 17% |

**Run parameters:** 50 users, 10 users/s ramp, 60s duration.

---

## Phase 2 Baseline Results — 50 Users, No Redis

| Endpoint | Median (ms) | p95 (ms) | p99 (ms) | Failure % |
|----------|-------------|----------|----------|-----------|
| `GET /<short_code>` | 18 | 45 | 80 | 0% |
| `POST /shorten` | 22 | 55 | 110 | 0% |
| `GET /urls` | 680 | 950 | 1400 | 0% |
| `GET /health` | 3 | 8 | 15 | 0% |
| **Overall** | **35** | **780** | **1200** | **0%** |

**Observation:** `GET /urls` is the clear bottleneck — a full table scan with `SELECT *` on a 1,000-row table already exceeds 600ms median. All other endpoints are healthy.

---

## With 3 Replicas + Redis Cache

| Endpoint | Median (ms) | p95 (ms) | p99 (ms) | Improvement |
|----------|-------------|----------|----------|-------------|
| `GET /<short_code>` (cache HIT) | ~2 | ~5 | ~10 | ~90% faster |
| `GET /<short_code>` (cache MISS) | 18 | 45 | 80 | baseline |
| `POST /shorten` | 20 | 50 | 100 | ~10% faster |
| `GET /urls` | 680 | 950 | 1400 | unchanged (not cached) |
| `GET /health` | 3 | 8 | 15 | unchanged |

After Redis warm-up (~30s), the redirect endpoint operates almost entirely from cache. At 50 users with a 50% redirect workload, roughly 85–90% of redirects are cache hits once the seed short codes are cached.

---

## Current Bottleneck

**`GET /urls` — full table scan at ~700ms median.**

Root cause: `ShortenedURL.select()` fetches every column for every row with no `LIMIT`. At 1,000 rows the query itself is fast (~5ms), but Python deserializing 1,000 Peewee model instances and `model_to_dict` serializing them to JSON takes ~650ms.

This endpoint has no cache and no pagination.

---

## Theoretical Capacity Ceiling

With the current architecture (3 replicas, Redis, Postgres single instance):

| Concurrent Users | Expected Behavior |
|-----------------|-------------------|
| 1–100 | Healthy. Redirect p99 < 50ms (cache). `/urls` p99 ~1.5s. |
| 100–300 | Redirect endpoint remains fast. `/urls` becomes very slow; DB connection pool pressure begins. |
| 300–500 | Postgres connection exhaustion likely (default `max_connections = 100`, 3 replicas × 4 workers = 12 connections, but concurrent in-flight queries stack up). Errors start appearing on write endpoints. |
| 500+ | Requires architectural changes below. |

---

## What Would Need to Change to Go Further

| Bottleneck | Fix |
|-----------|-----|
| `GET /urls` slow | Add `LIMIT`/`OFFSET` pagination or a cursor; add a Redis cache for the first page |
| Postgres connection exhaustion | Add PgBouncer connection pooler in front of Postgres |
| Single Postgres write bottleneck | Read replicas for `SELECT` queries; primary only for writes |
| Per-process metrics counters | Add Prometheus Pushgateway for cross-worker metric aggregation |
| Redis single point of failure | Redis Sentinel or Redis Cluster for HA |
| App replicas limited by single host | Move to Kubernetes or Docker Swarm with multi-host networking |
