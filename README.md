# WeMadeIt — URL Shortener

A production-grade URL shortener built for the MLH PE Hackathon.

**Stack:** Flask · Peewee ORM · PostgreSQL · Redis · Nginx · Prometheus · Grafana · uv

---

## Architecture

```
                        ┌─────────────────────────────────────────┐
                        │             Docker Compose              │
                        │                                         │
  ┌────────┐  :5000     │  ┌─────────┐       ┌──────────────┐    │
  │ Client │ ─────────► │  │  Nginx  │──────►│   App (x3)   │    │
  └────────┘            │  └─────────┘       │  gunicorn    │    │
                        │                    │  Flask/Peewee│    │
                        │  ┌─────────┐       └──────┬───┬───┘    │
                        │  │Prometheus│◄────────────┘   │        │
                        │  │  :9090  │                  │        │
                        │  └────┬────┘       ┌──────────▼──────┐ │
                        │       │            │   PostgreSQL     │ │
                        │  ┌────▼────┐       │     :5432        │ │
                        │  │ Grafana │       └─────────────────┘ │
                        │  │  :3001  │                           │
                        │  └─────────┘       ┌─────────────────┐ │
                        │                    │      Redis       │ │
                        │                    │     :6379        │ │
                        └────────────────────┴─────────────────┴─┘
```

---

## API Reference

| Method | Path | Description | Status Codes |
|--------|------|-------------|--------------|
| `POST` | `/shorten` | Create a shortened URL | 201, 400, 503 |
| `GET` | `/<short_code>` | Redirect to original URL | 302, 404, 410, 503 |
| `GET` | `/urls` | List all URLs (optional `?active=true\|false`) | 200, 503 |
| `GET` | `/urls/<id>` | Get a single URL by ID | 200, 404, 503 |
| `PUT` | `/urls/<id>` | Update title, original_url, or is_active | 200, 404, 503 |
| `DELETE` | `/urls/<id>` | Soft-delete a URL (sets is_active=False) | 200, 404, 503 |
| `GET` | `/health` | Health check | 200 |
| `GET` | `/metrics` | JSON app metrics | 200 |
| `GET` | `/metrics/prometheus` | Prometheus text exposition | 200 |

### POST /shorten — request body

```json
{
  "url": "https://example.com",   // required, must start with http:// or https://
  "title": "My Link",             // optional
  "user_id": 1                    // optional
}
```

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_NAME` | `hackathon_db` | PostgreSQL database name |
| `DATABASE_HOST` | `localhost` | PostgreSQL host |
| `DATABASE_PORT` | `5432` | PostgreSQL port |
| `DATABASE_USER` | `postgres` | PostgreSQL user |
| `DATABASE_PASSWORD` | `postgres` | PostgreSQL password |
| `REDIS_HOST` | `localhost` | Redis host |
| `REDIS_PORT` | `6379` | Redis port |
| `DISCORD_WEBHOOK_URL` | _(unset)_ | Discord webhook for alerts (optional) |

---

## Quick Start — Local Development

```bash
# 1. Install uv (if not already installed)
curl -LsSf https://astral.sh/uv/install.sh | sh

# 2. Clone and install dependencies
git clone <repo-url> && cd WeMadeIt_PE_Project
uv sync

# 3. Create databases
createdb hackathon_db
createdb hackathon_test_db

# 4. Configure environment
cp .env.example .env   # edit if your DB credentials differ

# 5. Seed the database (place CSVs in seeds/ first)
python seed.py

# 6. Run the development server
uv run run.py

# 7. Verify
curl http://localhost:5000/health
# → {"status": "ok"}
```

---

## Quick Start — Docker

```bash
# 1. Build and start all services
docker compose up --build -d

# 2. Seed the database
docker compose run --rm seed

# 3. Verify
curl http://localhost:5000/health

# 4. Open Grafana
open http://localhost:3001   # admin / hackathon
```

---

## Running Tests

```bash
# Unit + integration tests
uv run pytest -v

# With coverage report
uv run pytest --cov=app --cov-report=term-missing -v

# Load test (requires app running)
uv run locust --host=http://localhost:5000
```

---

## Project Structure

```
WeMadeIt_PE_Project/
├── app/
│   ├── __init__.py          # App factory, hooks, error handlers
│   ├── alerts.py            # Health checks, Discord alerts, CLI command
│   ├── cache.py             # Redis cache helpers
│   ├── database.py          # DatabaseProxy, BaseModel, connection hooks
│   ├── logging_config.py    # JSON structured logging
│   ├── metrics_store.py     # In-process Prometheus counters
│   ├── models/
│   │   ├── user.py          # User model
│   │   ├── url.py           # ShortenedURL model
│   │   └── event.py         # Event model
│   └── routes/
│       ├── metrics.py       # /metrics and /metrics/prometheus
│       └── urls.py          # URL CRUD and redirect routes
├── tests/
│   ├── conftest.py          # Fixtures (test_app, client, seed_data)
│   ├── test_models.py       # Model unit tests
│   └── test_routes.py       # Route integration tests
├── docs/
│   ├── DECISION_LOG.md
│   ├── DEPLOY_GUIDE.md
│   ├── FAILURE_MODES.md
│   ├── RUNBOOK.md
│   └── CAPACITY_PLAN.md
├── seeds/                   # CSV seed files (download from platform)
├── grafana/provisioning/    # Auto-provisioned Grafana datasource
├── seed.py                  # Table reset + CSV bulk loader
├── locustfile.py            # Load test scenarios
├── Dockerfile               # Production image
├── docker-compose.yml       # Full stack orchestration
├── nginx.conf               # Reverse proxy + load balancer config
├── prometheus.yml           # Prometheus scrape config
└── .github/workflows/
    └── test.yml             # CI: test on push/PR to main
```

---

## Seed Data

Download CSV files from the [MLH PE Hackathon](https://mlh-pe-hackathon.com) platform and place them in `seeds/`:

| File | Columns |
|------|---------|
| `seeds/users.csv` | `id`, `username`, `email`, `created_at` |
| `seeds/urls.csv` | `id`, `user_id`, `short_code`, `original_url`, `title`, `is_active`, `created_at`, `updated_at` |
| `seeds/events.csv` | `id`, `url_id`, `user_id`, `event_type`, `timestamp`, `details` |

```bash
python seed.py
# Users loaded: 500
# ShortenedURLs loaded: 1000
# Events loaded: 5000
# Sequences reset
```

> **Warning:** `seed.py` drops and recreates all tables. Do not run against production data.
