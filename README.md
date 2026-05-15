# MicroApp-VerticalForge

Industry Vertical Pack generator for LumApps Agent Hub. Takes one customer's custom Micro-app, abstracts it into a reusable Vertical Pack, applies governance, publishes to the platform Pack Library.

This repo is the **API surface + service skeleton** — engines for AST abstraction and pack signing are stubbed at clear seams. Drop them in, plug the same routes, ship.

```
   Custom Micro-app           Forge Pipeline                Vertical Pack
   (one customer)      ──►   ingest → abstract       ──►   (N customers)
                              → govern → sign
```

## Route surface

```
# Forge jobs
POST   /api/forge/jobs                       Submit source + target industry
GET    /api/forge/jobs/{job_id}              Poll job state
GET    /api/forge/jobs/{job_id}/stream       SSE feed of stage updates
POST   /api/forge/jobs/{job_id}/cancel       Cancel a running job
POST   /api/forge/jobs/{job_id}/publish      Push completed pack to library

# Pack library
GET    /api/packs                            List packs (filter by industry)
GET    /api/packs/{pack_id}                  Pack manifest + version history
POST   /api/packs/{pack_id}/deploy           Deploy to one or more tenants
GET    /api/packs/{pack_id}/customers        Who has it installed

# Catalog
GET    /api/industries                       Supported industries + customer counts

GET    /health                               Liveness probe
```

## Layout

```
src/
├── main.py              FastAPI app, lifespan, router wiring
├── config.py            Pydantic settings
├── auth/
│   ├── oidc.py          JWT/JWKS verifier (per-tenant SSO)
│   └── deps.py          require_user, require_scope
├── models/
│   ├── forge.py         ForgeJob, ForgeStage, ForgeStatus
│   ├── pack.py          VerticalPack, Manifest, Governance, Industry
│   └── events.py        SSE event schema
├── api/routes/
│   ├── forge.py         /api/forge/*
│   ├── packs.py         /api/packs/*
│   └── industries.py    /api/industries
├── services/
│   ├── forge_engine.py  Pipeline driver (ingest → abstract → govern → sign)
│   └── pack_registry.py In-memory registry — swap for Postgres in prod
└── utils/
    └── tracing.py       Correlation-id middleware + structlog setup
```

## Run

```bash
cp .env.example .env
pip install -e .
uvicorn src.main:app --reload --port 8000
# OpenAPI at http://localhost:8000/docs
```

Submit a forge job:
```bash
curl -X POST http://localhost:8000/api/forge/jobs \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d @examples/forge_request.json
```

## Tests

```bash
pytest -q
```

## Notes for the reviewer

- The forge **pipeline stages are real DAG nodes**; the per-stage logic (AST parsing, governance application, pack signing) is stubbed with clear TODO seams. The route surface, validation, auth, eventing, and DAG driver are all implemented.
- Governance configuration is data-driven (Pydantic `GovernanceConfig`) so the same routes power retail/manufacturing/hospitality/tech — each industry plugs different defaults.
- Pack publishing is idempotent (versioned). Re-publishing a pack with the same `(name, version)` returns 409.
