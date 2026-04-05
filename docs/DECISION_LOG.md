# Decision Log

Records why key technology choices were made, so future contributors understand the reasoning rather than just the outcome.

---

## Flask over Django / FastAPI

**Decision:** Use Flask as the web framework.

**Why:** Flask's minimal surface area is a strong fit for a hackathon project where speed of implementation matters. Django brings too much — an ORM, admin, auth, and migrations — that we'd spend time disabling or working around. FastAPI is a reasonable alternative but requires async-aware database access; Peewee is synchronous, so mixing it with async would add complexity with no concrete benefit at this scale. Flask lets us wire only what we need: a request context, error handlers, and blueprints.

**Trade-off accepted:** Flask has no built-in async support, so it will scale via processes (gunicorn workers) rather than coroutines. That is fine for the current load profile.

---

## Peewee over SQLAlchemy

**Decision:** Use Peewee ORM instead of SQLAlchemy.

**Why:** SQLAlchemy is the industry standard but comes with a steep learning curve — sessions, units of work, and the expression language are powerful but add cognitive overhead for a focused sprint. Peewee has a simpler mental model: models map directly to tables, queries are chainable methods, and there is no session to manage. `DatabaseProxy` makes it trivial to swap the underlying database for tests. `playhouse.shortcuts.model_to_dict` gives us JSON serialization in one line.

**Trade-off accepted:** Peewee has fewer migration tools and a smaller ecosystem. At hackathon scale, we manage schema changes by recreating tables; in production you'd add a migration library (e.g. `peewee-migrate`).

---

## Redis for Caching

**Decision:** Cache `GET /<short_code>` lookups in Redis with a 5-minute TTL.

**Why:** The redirect endpoint is the highest-traffic path — every click on a shortened link hits it. Without caching, every redirect requires a Postgres read. At 50 concurrent users with 3× weighted redirect tasks in the load test, Postgres becomes the bottleneck quickly. Redis keeps hot short codes in memory with sub-millisecond lookup, reducing DB load and cutting p99 latency on redirects significantly.

**Why 5-minute TTL:** Long enough to absorb traffic spikes on popular links. Short enough that updates (title change, deactivation) propagate within a reasonable window. Cache invalidation on PUT and DELETE ensures correctness for explicit changes.

**Trade-off accepted:** Each gunicorn worker maintains its own Redis connection. Under 3 replicas × 4 workers = 12 connections, this is well within Redis's default limits. Cache is per-process, not shared across workers for counters — but the redirect cache is stored in Redis itself so all workers share it.

---

## Nginx as Load Balancer

**Decision:** Put Nginx in front of the gunicorn workers rather than exposing gunicorn directly.

**Why:** Nginx is battle-tested at handling connection management, slow clients, and static file serving. gunicorn is not designed to be internet-facing — it has no connection timeout handling for slow clients (Slowloris attacks) and no request buffering. Nginx handles the edge concerns and proxies clean, fast requests to gunicorn. Docker Compose DNS round-robins `app:5000` across all three replicas automatically, so the single upstream block is sufficient for load balancing.

**Trade-off accepted:** Adds one network hop. Acceptable because the hop is on a Docker bridge network (sub-millisecond) and the operational benefit outweighs it.

---

## Prometheus + Grafana over Datadog / New Relic

**Decision:** Self-host Prometheus for metrics collection and Grafana for dashboards.

**Why:** Both are free, open-source, and compose-native. Datadog and New Relic are excellent but require account setup, API keys, and send data to third-party servers — unsuitable for a self-contained hackathon submission. Prometheus's pull model means the app only needs to expose an HTTP endpoint; no agent to install or sidecar to run. Grafana auto-provisions the Prometheus datasource via a YAML file, so the monitoring stack is fully reproducible with a single `docker compose up`.

**Trade-off accepted:** Per-process metrics (counters reset on restart, no cross-worker aggregation without a push gateway). Sufficient for a hackathon demonstration; a production setup would add a Prometheus Pushgateway or use a client library with proper multiprocess support.
