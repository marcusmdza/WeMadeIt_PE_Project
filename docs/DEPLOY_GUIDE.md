# Deploy Guide

---

## Prerequisites

- Docker 24+ and Docker Compose v2
- `seeds/` directory populated with CSV files from the platform
- `.env` file (copy from `.env.example`)

---

## First Deploy

```bash
# 1. Build images and start all services in the background
docker compose up --build -d

# 2. Check all services are healthy
docker compose ps

# 3. Seed the database (runs once, then exits)
docker compose run --rm seed

# 4. Verify the app is serving traffic
curl http://localhost:5000/health
# → {"status": "ok"}

# 5. Open monitoring
open http://localhost:3001   # Grafana — admin / hackathon
open http://localhost:9090   # Prometheus
```

---

## Scaling

Scale app replicas up or down without downtime. Nginx load-balances across all replicas automatically via Docker Compose DNS.

```bash
# Scale to 5 replicas
docker compose up -d --scale app=5

# Scale back to 3 (default)
docker compose up -d --scale app=3

# Scale to 1 for debugging
docker compose up -d --scale app=1
```

> Note: `deploy.replicas: 3` in `docker-compose.yml` sets the default. The `--scale` flag overrides it at runtime without changing the file.

---

## Deploying a Code Update

```bash
# 1. Pull the latest code
git pull origin main

# 2. Rebuild and restart only the app service (zero-downtime via Nginx)
docker compose up -d --build app

# 3. Verify the new version is running
docker compose ps
curl http://localhost:5000/health
```

---

## Rolling Back

```bash
# 1. Stop the running app containers
docker compose stop app

# 2. Check out the previous commit or release tag
git checkout <previous-commit-or-tag>

# 3. Rebuild and restart from the previous code
docker compose up -d --build app

# 4. Verify
curl http://localhost:5000/health
```

To roll back to a specific git tag:
```bash
git tag                          # list tags
git checkout v1.0.0              # check out tag
docker compose up -d --build app
```

---

## Viewing Logs

```bash
# All services
docker compose logs -f

# App only (tailed, last 100 lines)
docker compose logs -f --tail=100 app

# Nginx access log
docker compose logs -f nginx

# Database
docker compose logs -f db
```

---

## Stopping and Teardown

```bash
# Stop all services (preserves volumes)
docker compose down

# Stop and remove all data volumes (DESTRUCTIVE — deletes DB data)
docker compose down -v

# Stop a single service
docker compose stop app
```

---

## Re-seeding

```bash
# Drop tables, reload all CSVs, reset sequences
docker compose run --rm seed
```

> This is destructive. All existing URL and event data will be replaced.

---

## Running Health Checks Manually

```bash
# Check DB and Redis from inside a running app container
docker compose exec app flask check-alerts
# → All services healthy: {'db': 'connected', 'redis': 'connected'}
```
