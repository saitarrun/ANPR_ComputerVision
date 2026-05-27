# ANPR — Automatic Number Plate Recognition

Industrial-grade ANPR pipeline. Live video → plate detection → OCR → watchlist alerts → audit-logged storage.

## Status

Phase-0 (M0–M4): laptop webcam + iPhone demo. ~12 dev-days. See `/Users/saitarrunpitta/Claude/config/plans/witty-wibbling-plum.md` for the full plan.

## Stack

- Python 3.11, FastAPI, SQLAlchemy 2, Alembic, Celery + Redis.
- YOLOv8 (Ultralytics) for plate detection, PaddleOCR + CRNN for OCR, ByteTrack (supervision) for multi-frame fusion.
- Postgres + MinIO + Prometheus + Grafana.
- React + Vite + TanStack Query dashboard.

## Prerequisites

- macOS or Linux.
- Python 3.11+ via `pyenv` or `uv`.
- **OrbStack** (not Docker Desktop): `brew install --cask orbstack` → launch once → `docker context use orbstack`.
- `uv` package manager: `curl -LsSf https://astral.sh/uv/install.sh | sh`.

## Quickstart

```bash
# 1. Install deps
uv sync

# 2. Bring up infra (postgres, redis, minio, prometheus, grafana)
make up

# 3. Run DB migrations
make migrate

# 4. Laptop webcam demo (Phase-0)
make demo-webcam

# 5. iPhone Continuity Camera demo
make demo-iphone
```

## Repo Layout

```
anpr_core/    detect, ocr, pipeline, tracking, postproc, quality, privacy
api/          FastAPI app + WebSocket live feed
workers/      Celery batch tasks
db/           SQLAlchemy models + Alembic migrations
ui/           React + Vite dashboard
ingest/       webcam, iPhone, RTSP, file adapters
training/     YOLO + OCR fine-tune scripts
benchmarks/   accuracy + latency harness
tests/        pytest unit / integration / e2e
ops/          Dockerfile, docker-compose, k8s, grafana, prometheus
scripts/      dev utilities
config/       YAML configs per env, per region
```

## Make Targets

| Target | What |
|---|---|
| `make up` | Start postgres + redis + minio + prometheus + grafana via OrbStack |
| `make down` | Stop infra |
| `make migrate` | Run Alembic migrations |
| `make demo-webcam` | Live laptop-camera plate detection window |
| `make demo-iphone` | Live iPhone (Continuity Camera) plate detection window |
| `make test` | Unit + integration tests |
| `make lint` | Ruff + mypy |
| `make fmt` | Ruff format |
| `make bench` | Accuracy + latency benchmarks |

## License

Proprietary — internal use only.
