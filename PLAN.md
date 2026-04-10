# Demo Implementation Plan

FastAPI + HTMX frontend that visually shows the orchestrator → sandboxed search flow, deployable on Railway.

## Stack

- **FastAPI** — backend, SSE progress stream, admin API
- **HTMX** + `sse-ext` — real-time UI updates without JS framework
- **CSS** — animated dots, connecting line between agent boxes
- **Railway** — `Dockerfile` + `railway.json`

## File Layout

```
demo/
├── main.py              # FastAPI app
├── agent.py             # Orchestrator logic with progress callbacks
├── templates/
│   ├── index.html       # Demo UI: orchestrator + agent boxes, log
│   └── admin.html       # Admin: credentials form
├── static/
│   └── style.css        # Agent box layout, animated dots, line
├── Dockerfile
└── railway.json
```

## Routes

| Route | Description |
|---|---|
| `GET /` | Demo page |
| `POST /search` | Submit query → returns `job_id` |
| `GET /stream/{job_id}` | SSE endpoint — streams progress events |
| `GET /admin` | Credentials form |
| `POST /admin` | Store creds in-memory |

## SSE Event Sequence

Each event has a `type` and `data` payload. HTMX swaps UI elements on receipt.

```
orchestrator:start   → highlight orchestrator box
secret:check         → log "Checking Secrets Manager..."
stack:check          → log "Checking CloudFormation stack..."
stack:creating       → log "Deploying Lambda sandbox (~30–60s)..." + animate line
stack:ready          → log "Stack ready"
lambda:invoking      → highlight agent box, animate dots
lambda:done          → show result, stop animation
error                → show error state
```

## Agent Callbacks

`agent.py` wraps `invoke_search.py` logic with a `on_event(type, message)` callback arg passed through each stage. The SSE endpoint passes an `asyncio.Queue` as the callback target; `main.py` reads from the queue and yields SSE frames.

## UI Layout

```
┌─────────────────┐          ┌─────────────────┐
│   Orchestrator  │ ───···─▶ │  Search Agent   │
│                 │          │   (Lambda)      │
└─────────────────┘          └─────────────────┘

━━━━━━━━━━━━━━ Activity Log ━━━━━━━━━━━━━━
[10:04:01] Checking Secrets Manager...
[10:04:01] Stack already exists — skipping deploy
[10:04:02] Invoking Lambda sandbox...
[10:04:05] Result received ✓
```

- Boxes highlighted (border + glow) when active
- Connecting line animates with moving dots while Lambda is running
- Log entries append at bottom via `hx-swap-oob`

## Credentials (Admin Page)

Fields: `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_SESSION_TOKEN` (optional), `AWS_REGION` (default `us-east-1`), `OPENAI_API_KEY`.

Stored in a module-level dict in `main.py`. boto3 clients created with explicit `aws_access_key_id` etc. kwargs (not default chain) so in-memory creds take effect immediately.

## Railway Deployment

- `Dockerfile`: python:3.11-slim, `pip install -r requirements.txt`, `uvicorn main:app --host 0.0.0.0 --port $PORT`
- `railway.json`: sets `PORT` env var
- No persistent volume needed — creds re-entered on each deploy
