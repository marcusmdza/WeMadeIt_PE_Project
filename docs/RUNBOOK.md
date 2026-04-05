# Runbook

Operational playbook for diagnosing and resolving production incidents.

---

## Alert: Service Down

**Signal:** Discord alert `:red_circle: Service degraded`, `/metrics` returns `"database_status": "disconnected"`, or `GET /health` returns non-200.

### Diagnosis

```bash
# 1. Check which containers are running
docker compose ps

# 2. Check recent logs for the failing service
docker compose logs --tail=50 app
docker compose logs --tail=50 db
docker compose logs --tail=50 redis

# 3. Run the built-in health check
docker compose exec app flask check-alerts
```

### Fix: App container down

```bash
docker compose up -d app        # restart
docker compose ps               # confirm running
curl http://localhost:5000/health
```

### Fix: Database container down

```bash
docker compose up -d db         # restart
# Wait for healthcheck to pass (up to 50s)
docker compose ps               # confirm "healthy"
docker compose up -d app        # restart app to reconnect
```

### Fix: Redis container down

```bash
docker compose up -d redis
docker compose ps               # confirm "healthy"
# App falls back to DB automatically; no restart needed
```

---

## Alert: High Error Rate

**Signal:** Discord alert `:warning: High error rate: N errors in the last 60s`, or `total_errors` rising steeply in Grafana.

### Diagnosis

```bash
# 1. Check which endpoints are failing
docker compose logs --tail=200 app | grep '"status": [45]'

# 2. Check DB connectivity
docker compose exec app flask check-alerts

# 3. Look at recent 5xx errors specifically
docker compose logs app | grep '"status": 5'
```

### Common causes and fixes

| Cause | Fix |
|-------|-----|
| DB overloaded | Scale app down to reduce connection count: `docker compose up -d --scale app=1` |
| Bad deploy introduced a bug | Roll back: `git checkout <prev>` + `docker compose up -d --build app` |
| Redis down causing slow DB fallback | `docker compose up -d redis` |
| Client sending malformed requests | Check logs for `400` errors; no action needed on server side |

---

## Alert: High Latency

**Signal:** `http_request_duration_seconds` p99 > 1s in Grafana, or user reports of slow redirects.

### Diagnosis

```bash
# 1. Check cache hit rate in Prometheus
# Query: rate(app_cache_hits_total[5m]) / (rate(app_cache_hits_total[5m]) + rate(app_cache_misses_total[5m]))
# Low hit rate means Redis isn't helping — check Redis:
docker compose exec redis redis-cli info stats | grep hits

# 2. Check DB connection count
docker compose exec db psql -U postgres -c "SELECT count(*) FROM pg_stat_activity;"

# 3. Check if the slow endpoint is /urls (full table scan)
docker compose logs app | grep '"/urls"' | grep -v '"status": 200'

# 4. Check app replica resource usage
docker stats
```

### Fixes

| Cause | Fix |
|-------|-----|
| Redis down (all requests hitting DB) | `docker compose up -d redis` |
| Too few app replicas | `docker compose up -d --scale app=5` |
| `GET /urls` slow at scale | Add pagination or limit the query (known bottleneck — see CAPACITY_PLAN.md) |
| DB connection pool exhausted | Scale app replicas down or increase Postgres `max_connections` |

---

## Alert: Database Unreachable

**Signal:** All routes return `503`, `flask check-alerts` reports `db: disconnected`.

### Step-by-step diagnosis

```bash
# 1. Is the container running?
docker compose ps db

# 2. If not running, restart it
docker compose up -d db

# 3. If running, check if it's healthy
docker compose exec db pg_isready -U postgres

# 4. Check Postgres logs for errors
docker compose logs --tail=100 db

# 5. If healthy but app can't connect, restart app to re-establish connections
docker compose restart app

# 6. If the volume is corrupted (rare), you may need to recreate it
# WARNING: This deletes all data
docker compose down -v
docker compose up -d db
docker compose run --rm seed   # re-seed from CSVs
```

### Verify recovery

```bash
docker compose exec app flask check-alerts
# → All services healthy: {'db': 'connected', 'redis': 'connected'}

curl http://localhost:5000/health
# → {"status": "ok"}
```
