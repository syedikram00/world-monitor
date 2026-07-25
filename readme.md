# World Monitor

A multi-service system that continuously ingests real-world news and weather data, stores it, exposes operational metrics, visualizes both application and cluster health, and serves a live dashboard with on-demand AI summarization of news articles. Built as a deliberately multi-component project — not one app, but several small services working together, each with its own deployment lifecycle.

## What It Does

- Continuously fetches live news (Currents API) and weather (OpenWeatherMap) for a fixed set of cities
- Stores news as a deduplicated catalog and weather as a growing time series
- Exposes Prometheus metrics on its own ingestion health (success/failure counts, duration, records processed)
- Serves a separate, lightweight dashboard reading directly from the database — weather cards and a news feed
- Summarizes any news article on demand using Gemini Flash, displayed inline in the dashboard
- Surfaces both application metrics and full Kubernetes cluster health (nodes, containers, cluster state) through Prometheus and Grafana

## Why It's Structured as Multiple Services

Everything here could technically live in one FastAPI app. It doesn't, deliberately:

- **The ingestion service** only writes. It runs continuously, fetches on an internal schedule, and exposes metrics about its own health.
- **The dashboard service** only reads. It has no ingestion logic, no scheduler, no write path — it queries Postgres and serves pages.

Splitting these means the ingestion service can keep running (and being monitored) independently of whether anyone is looking at the dashboard, and the dashboard can be scaled, restarted, or redeployed without ever affecting data collection. This mirrors a real production pattern: separating a system's write path from its read path.

## Architecture

```
                    ┌─────────────────────┐
                    │  Ingestion Service    │
                    │  (long-running)       │
                    │                        │
                    │  - fetches news/weather│
                    │  - writes to Postgres  │
                    │  - exposes /metrics    │
                    └──────────┬─────────────┘
                               │
                    ┌──────────▼─────────────┐
                    │     PostgreSQL          │
                    │  news_events            │
                    │  weather_readings        │
                    └──────────┬─────────────┘
                               │
                    ┌──────────▼─────────────┐
                    │   Dashboard Service      │
                    │  (reads Postgres only)   │
                    │                          │
                    │  - weather cards         │
                    │  - news feed             │
                    │  - on-demand AI summary  │
                    │    (Gemini Flash)        │
                    └──────────────────────────┘

    ┌───────────────┐        ┌──────────────────┐
    │   Prometheus   │◄───────┤ scrapes ingestion │
    │                │        │ service /metrics  │
    │  + cluster      │◄──────┤ + node/cadvisor/  │
    │    metrics      │        │ kube-state-metrics│
    └───────┬────────┘        └──────────────────┘
            │
    ┌───────▼────────┐
    │    Grafana      │
    │  - app health   │
    │  - K8s health   │
    │  - Postgres data│
    └─────────────────┘
```

## Tech Stack

| Layer | Tool |
|---|---|
| Ingestion service | Python, `prometheus_client` |
| Dashboard service | Python, FastAPI, Jinja2 |
| AI summarization | Gemini Flash (on-demand, per-article) |
| Database | PostgreSQL, SQLAlchemy |
| External APIs | Currents API (news), OpenWeatherMap (weather) |
| Metrics | Prometheus |
| Visualization | Grafana |
| Testing | Pytest (external APIs and DB mocked) |
| Containerization | Docker |
| CI/CD | GitHub Actions |
| Container Registry | Docker Hub |
| Orchestration | Kubernetes (kind, multi-node) |
| Packaging | Helm (official Prometheus and Grafana charts; raw manifests for app services) |

## Project Structure

```
world-monitor/                    # ingestion service
├── app.py / main.py               # long-running loop + /metrics
├── fetcher.py                     # external API calls
├── models.py                      # SQLAlchemy schema
├── service.py                     # fetch → validate → store logic
├── tests/
├── Dockerfile
├── docker-compose.yml             # local dev: app + Postgres + Prometheus
├── prometheus.yml                 # local scrape config
├── k8s/
│   ├── secret.yaml
│   ├── postgres-deployment.yaml
│   ├── postgres-service.yaml
│   ├── world-monitor-app-deployment.yaml
│   └── world-monitor-app-service.yaml
└── .github/workflows/ci.yml

dashboard-api/                    # separate, read-only dashboard service
├── app/main.py
├── templates/index.html
├── static/style.css
├── Dockerfile
├── k8s/
│   ├── dashboard-deployment.yaml
│   └── dashboard-service.yaml
└── .github/workflows/ci.yml
```

## Database Schema

**`news_events`** — a catalog, not a time series. `url` has a unique constraint; every insert uses `ON CONFLICT (url) DO NOTHING` so repeated headlines across ingestion cycles are silently skipped rather than duplicated, and the check-and-skip happens atomically at the database level rather than via a separate `SELECT` first, avoiding a race condition between concurrent writers.

**`weather_readings`** — a time series by design. A new row is inserted every cycle rather than updating an existing one per city, specifically to preserve history and allow trend analysis over time. The dashboard queries the most recent reading per city using Postgres's `DISTINCT ON`.

## Prometheus Metrics

| Metric | Type | Purpose |
|---|---|---|
| `ingestion_cycles_success_total` | Counter | Total successful ingestion runs |
| `ingestion_cycles_failure_total` | Counter | Total failed ingestion runs |
| `ingestion_duration_seconds` | Gauge | Duration of the most recent cycle |
| `news_articles_inserted_last_cycle` | Gauge | New articles actually inserted last cycle |
| `weather_cities_fetched_last_cycle` | Gauge | Cities successfully fetched last cycle |

### Why a long-running service instead of a CronJob

The initial design considered a Kubernetes CronJob for ingestion, matching the pattern used in an earlier project. It was deliberately rejected here: Prometheus works by scraping a `/metrics` HTTP endpoint on its own schedule, and a CronJob's pod exists only for the duration of a single run — there is nothing there for Prometheus to scrape between runs. Since this ingestion job only ever needs a single replica (multiple replicas would duplicate every API call and every write), there was no reason to keep the CronJob pattern purely for consistency with a past project. A single long-running process, sleeping between cycles on its own internal timer and exposing `/metrics` continuously via `prometheus_client`'s built-in HTTP server, fits the actual constraint correctly.

## Running Locally

**Ingestion service + Postgres + Prometheus:**
```bash
cd world-monitor
docker compose up --build
```
Prometheus UI: `http://localhost:9090` — check Status → Targets to confirm `application_tracker` is `UP`.

**Dashboard service** (separately, pointed at the same Postgres):
```bash
cd dashboard-api
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```
Visit `http://localhost:8000/`.

## Running Tests

```bash
python -m pytest tests/
```
Both external API calls and the database session are mocked. No real network calls or database connection are required to run the suite, which matters directly for CI — the GitHub Actions runner has neither a real Postgres instance nor real API credentials available to it, and none are configured as CI secrets, since none are needed.

## Deploying to Kubernetes

**1. Apply secrets and the ingestion stack:**
```bash
kubectl apply -f world-monitor/k8s/secret.yaml
kubectl apply -f world-monitor/k8s/postgres-deployment.yaml
kubectl apply -f world-monitor/k8s/postgres-service.yaml
kubectl apply -f world-monitor/k8s/world-monitor-app-deployment.yaml
kubectl apply -f world-monitor/k8s/world-monitor-app-service.yaml
```

**2. Apply the dashboard service:**
```bash
kubectl apply -f dashboard-api/k8s/dashboard-deployment.yaml
kubectl apply -f dashboard-api/k8s/dashboard-service.yaml
```

**3. Install Prometheus and Grafana via their official Helm charts:**
```bash
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo add grafana https://grafana.github.io/helm-charts
helm repo update

helm install my-prometheus prometheus-community/prometheus -f values-override.yml --namespace monitoring --create-namespace
helm install grafana grafana/grafana --namespace monitoring
```

### A real cross-namespace networking lesson

Prometheus (installed into a `monitoring` namespace) initially failed to scrape the ingestion service (running in `world-monitor-namespace`) even with a correct scrape config, because a bare Kubernetes service name only resolves within its own namespace by default. The fix was using the fully-qualified internal DNS name:

```
world-monitor-app-service.world-monitor-namespace.svc.cluster.local:8001
```

rather than the short `world-monitor-app-service:8001` form that works only for same-namespace communication.

## Secrets

API keys (`CURRENTS_API_KEY`, `OPENWEATHER_API_KEY`) and the database connection string are stored in a Kubernetes `Secret`, never as plain-text values in a committed Deployment manifest. The app Deployment consumes most of these via `envFrom.secretRef` (bulk-importing every key in the Secret as an environment variable) and pulls `DATABASE_URL` individually via `valueFrom.secretKeyRef`, since it's referenced by name directly in the code.

## AI Summarization

Each news article in the dashboard has a "Summarize with AI" button. On click, the dashboard service sends the article's title and description to Gemini Flash and displays the returned summary inline, directly in the article's card. This is deliberately on-demand rather than precomputed during ingestion — most fetched articles are never read, so summarizing all of them upfront would waste API calls on content nobody looks at.

## CI/CD

Each service has its own GitHub Actions workflow: run tests → build the Docker image → push to Docker Hub, tagged both `latest` and by commit SHA. No API keys or database credentials exist as CI secrets, since the test suite never touches either a real API or a real database.

## What This Project Demonstrates

- Deliberately splitting a system by responsibility (write path vs. read path) into independently deployable services, rather than one monolith
- Recognizing an architectural mismatch before building it wrong: identifying that Prometheus's pull-based scraping model is fundamentally incompatible with a short-lived CronJob, and choosing a long-running service instead, justified by an actual constraint (single-replica requirement) rather than habit
- Correct database-level concurrency handling (`ON CONFLICT DO NOTHING`) chosen specifically to avoid a race condition inherent to a check-then-insert approach
- Instrumenting a Python service with Prometheus client metrics, using the appropriate metric type (Counter vs. Gauge) for each measurement based on what it actually represents
- Diagnosing a real, non-obvious Kubernetes networking issue (cross-namespace service DNS resolution) by reasoning from first principles about how the failure could occur, not by guesswork
- Installing and configuring third-party, pre-built Helm charts (Prometheus, Grafana) rather than authoring every manifest from scratch, recognizing when that's the appropriate choice versus writing a custom chart
- Scoping an "add AI" request into something concrete and genuinely useful (on-demand, per-article summarization) rather than a vague feature
- Secrets handled via Kubernetes Secrets throughout, never committed in plain text

## Future Improvements

- Grafana dashboards for ingestion health and Kubernetes cluster health (data is already flowing into Prometheus; panels not yet built)
- GitOps via ArgoCD — replacing manual `kubectl apply` / `helm upgrade` with automatic, Git-driven sync across all five services in this project
- Log aggregation (Loki) alongside the existing metrics, for full observability rather than metrics-only
- Precompute and cache AI summaries for frequently-viewed articles rather than always calling the API fresh
- Ingress in place of direct Service access, consistent with earlier projects