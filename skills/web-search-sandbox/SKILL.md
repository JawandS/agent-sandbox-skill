---
name: web-search-sandbox
description: Use when you need to search the web. Runs the search in an isolated AWS Lambda sandbox to guard against prompt injection from search results.
---

# Web Search Sandbox

Performs a web search inside an ephemeral AWS Lambda sandbox. The sandbox is
created on first use and persists for the session. Results are filtered to a
strict schema before being returned — raw search content never touches the
orchestrator environment directly.

## When to Use

Use this skill instead of a direct web search any time you need to look up
current information. The sandbox contains any prompt injection attempts in
search results within the Lambda execution environment.

## Usage

Run the following command, replacing `<query>` with your search terms:

```bash
cd /home/js/cloud-computing/agent-sandbox-skill
python scripts/invoke_search.py "<query>"
```

**First call in a session:** The script will create the CloudFormation stack
(~30–60 seconds) before invoking the Lambda. Subsequent calls skip directly
to invocation.

## Response Schema

The script returns JSON with exactly these fields — nothing else:

```json
{
  "query": "the search query you provided",
  "summary": "plain-text answer from GPT-4o-mini with web search",
  "sources": [
    {
      "title": "Page title",
      "url": "https://...",
      "snippet": "Relevant excerpt from the page"
    }
  ],
  "timestamp": "2026-04-10T12:00:00Z"
}
```

## Teardown

The sandbox stack is automatically deleted at session end via the Claude Code
Stop hook. To delete it manually, use the `web-search-teardown` skill or run:

```bash
python scripts/teardown.py
```

## Prerequisites

- AWS credentials configured in `~/.aws/credentials`
- `OPENAI_API_KEY=sk-...` present in the `.env` file at the project root
- Dependencies installed: `uv sync`

On first run the script automatically pushes `OPENAI_API_KEY` from `.env` into
AWS Secrets Manager (`openai-api-key`). No manual secret setup required.
