# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
uv sync                                          # install dependencies
uv run python scripts/invoke_search.py "<query>" # deploy stack (first time) and run a search
uv run python scripts/teardown.py               # destroy stack + secret (idempotent)

cd demo && uv run uvicorn main:app --reload      # start FastAPI demo on http://localhost:8000
```

AWS credentials must be in `~/.aws/credentials`. `OPENAI_API_KEY` goes in `.env` at the repo root — `invoke_search.py` seeds it into Secrets Manager automatically on first run.

## Architecture

The core idea: web search results are untrusted and may contain prompt-injection payloads. This project isolates each search inside an ephemeral AWS Lambda so raw web content never reaches the orchestrator's context — only a structured JSON response is returned.

**Execution flow:**

```
Orchestrator (scripts/invoke_search.py or demo/agent.py)
    │  boto3 invoke (sync)
    ▼
Lambda (web-search-sandbox-fn)
    1. fetch OPENAI_API_KEY from Secrets Manager
    2. call GPT-4o-mini with web_search_preview
    3. return { query, summary, sources[], timestamp }
    │
    ▼
Orchestrator  ←  filtered schema only, raw content discarded
```

**Infrastructure** (`infra/sandbox_template.yaml`): CloudFormation stack named `web-search-sandbox` that deploys the Lambda. Uses the pre-existing AWS Academy `LabRole` — `iam:CreateRole` is not available. Stack is created on first call and destroyed at session end via the Stop hook in `.claude/settings.json`.

**Demo app** (`demo/`): FastAPI app with SSE streaming. `main.py` handles routes and SSE; `agent.py` contains all AWS orchestration logic with `on_event` callbacks for real-time progress. Visit `/admin` first to paste AWS Academy credentials (including session token), then `/` to run queries with animated diagram feedback.

**Skills** (`skills/`): Two Claude Code skills — `web-search-sandbox` (invoke the sandbox) and `web-search-teardown` (manual cleanup). The Stop hook auto-runs teardown at session end.

**Railway deployment**: `Dockerfile` + `railway.json` are configured — run `railway up` from repo root. The demo app resolves `infra/sandbox_template.yaml` relative to its location (handles both local and container paths).

## Key constraint

AWS Academy accounts cannot create IAM roles. All Lambda execution uses the pre-existing `LabRole` ARN, resolved at deploy time via `iam:GetRole`.
