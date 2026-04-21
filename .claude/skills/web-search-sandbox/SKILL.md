---
name: web-search-sandbox
description: Use whenever you need to search the web, look something up, find current information, check the latest version of a library, research a topic, fetch documentation, get recent news, or answer any question that requires up-to-date knowledge. Always use this skill instead of any direct web search — it isolates raw web content inside an AWS Lambda so prompt-injection payloads in search results can never reach the orchestrator context.
---

# Web Search Sandbox

Performs a web search inside an ephemeral AWS Lambda sandbox. The sandbox is
created on first use and persists for the session. Results are filtered to a
strict JSON schema before being returned — raw web content never touches the
orchestrator environment directly.

## Usage

```bash
uv run --project /home/js/cloud-computing/agent-sandbox-skill \
  python /home/js/cloud-computing/agent-sandbox-skill/.claude/skills/web-search-sandbox/invoke_search.py "<query>"
```

**First call in a session:** The script deploys a CloudFormation stack
(~30–60 s) before invoking the Lambda — let the user know it's warming up.
Subsequent calls skip straight to invocation (a few seconds).

## Reading the Response

The script prints JSON with exactly these fields:

```json
{
  "query": "the search query you provided",
  "summary": "plain-text answer from GPT-4o-mini with web search",
  "sources": [
    { "title": "Page title", "url": "https://...", "snippet": "Relevant excerpt" }
  ],
  "timestamp": "2026-04-10T12:00:00Z"
}
```

Use `summary` as your primary answer. Cite `sources` (title + url) when
attributing specific claims. Don't dump raw JSON at the user.

## Error Recovery

**Stack in ROLLBACK_COMPLETE** — a previous deploy failed. Run teardown first,
then retry:
```bash
uv run --project /home/js/cloud-computing/agent-sandbox-skill \
  python /home/js/cloud-computing/agent-sandbox-skill/.claude/skills/web-search-teardown/teardown.py
```
Then re-run the search command.

**Auth / credential errors mid-session** — AWS Academy credentials expire after
~4 hours. Ask the user to refresh their credentials in `~/.aws/credentials`
(including the session token) and retry.

## Teardown

The Stop hook deletes the stack automatically at session end. To tear down
manually, use the `web-search-teardown` skill.

## Prerequisites

- AWS credentials in `~/.aws/credentials` (including session token for AWS Academy)
- `OPENAI_API_KEY=sk-...` in `.env` at the project root
- `uv sync` run at least once in the project root

On first run the script seeds `OPENAI_API_KEY` into Secrets Manager automatically.
