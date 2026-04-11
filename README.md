# Cloud-Native Security for Multi-Agent AI Systems

> CSCI 420 – Cloud Computing | William & Mary | Spring 2026

Sandboxes AI web-search calls inside an ephemeral AWS Lambda so prompt-injection payloads in web content never reach the orchestrator's context.

---

## Setup

**Requirements:** AWS Academy credentials, Python 3.11+, [uv](https://docs.astral.sh/uv/), OpenAI API key

```bash
uv sync

# Add OpenAI key — only needed once to seed Secrets Manager
echo "OPENAI_API_KEY=sk-..." > .env

# First run: seeds Secrets Manager + deploys CloudFormation stack (~30–60s) + runs search
uv run python scripts/invoke_search.py "your query"

# Tear down when done (also runs automatically via the Claude Code Stop hook)
uv run python scripts/teardown.py
```

**AWS credentials** go in `~/.aws/credentials` (standard Academy export). The stack and secret persist across searches within a session.

---

## Repo layout

```
infra/
  sandbox_template.yaml     CloudFormation — Lambda + LabRole wiring
scripts/
  invoke_search.py          ensure stack → invoke Lambda → print result
  teardown.py               delete stack + secret (idempotent)
  lambda_handler.py         Lambda source of truth (also embedded inline in CFN)
skills/
  web-search-sandbox/       Claude Code skill — sandboxed web search
  web-search-teardown/      Claude Code skill — destroy sandbox resources
demo/
  main.py                   FastAPI app (SSE progress stream, admin page)
  agent.py                  orchestrator logic with on_event callbacks
  templates/                index.html (diagram + log), admin.html (AWS creds form)
  static/style.css           dark theme, animated connector dots
  requirements.txt
Dockerfile                  repo-root build context → copies demo/ + infra/
railway.json                Railway deployment config
```

---

## Skills

| Skill | Trigger | What it does |
|---|---|---|
| `web-search-sandbox` | `use the web-search-sandbox skill` | Ensures stack is up, invokes Lambda, returns `{query, summary, sources[], timestamp}` |
| `web-search-teardown` | `use the web-search-teardown skill` | Deletes CFN stack and Secrets Manager secret |

The Stop hook in `.claude/settings.json` runs teardown automatically at session end.

---

## Demo

FastAPI app that visualises the orchestrator → Lambda flow in real time via SSE.

```bash
cd demo
uv run uvicorn main:app --reload
# → http://localhost:8000
```

1. Visit `/admin` — paste AWS Academy credentials (session token included)
2. Visit `/` — enter a query and watch the diagram animate through each stage

The OpenAI key is never entered in the UI — it's read from Secrets Manager (seeded by `invoke_search.py` on first run).

**Deploy to Railway:** `railway up` from repo root — `Dockerfile` + `railway.json` are already configured.

---

## How the sandbox works

```
Orchestrator
    │  boto3 invoke (sync)
    ▼
Lambda (web-search-sandbox-fn)
    1. fetch OPENAI_API_KEY from Secrets Manager
    2. call GPT-4o-mini with web_search_preview tool
    3. return { query, summary, sources[], timestamp }
    │
    ▼
Orchestrator  ←  filtered result only, raw web content discarded
```

The Lambda's IAM role (`LabRole`) is scoped to one secret + CloudWatch Logs — no lateral movement from inside the sandbox. The CFN stack is destroyed at session end, leaving no persistent attack surface.
