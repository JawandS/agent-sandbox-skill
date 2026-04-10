# Cloud-Native Security for Multi-Agent AI Systems

> **CSCI 420 – Cloud Computing | William & Mary | Spring 2026**
> **Project Type:** Cloudify Your Interest

---

## Quickstart

**Prerequisites:** AWS Academy account with credentials in `~/.aws/credentials`, Python 3.11+, [uv](https://docs.astral.sh/uv/)

```bash
# 1. Install dependencies
uv sync

# 2. Add your OpenAI API key to .env
echo "OPENAI_API_KEY=sk-..." > .env

# 3. Run a search — first run bootstraps everything automatically:
#    - pushes OPENAI_API_KEY from .env into AWS Secrets Manager
#    - deploys the CloudFormation sandbox stack (~30–60s, one-time per session)
#    - invokes the Lambda and returns a structured, filtered result
uv run python scripts/invoke_search.py "your search query"

# 4. Tear down sandbox resources when done
uv run python scripts/teardown.py
```

> The sandbox stack persists across searches within a session and is
> automatically deleted by the Claude Code Stop hook when the session ends.

---

## Overview

This project investigates how cloud-native principles — isolation, ephemeral environments, and resource lifecycle management — can be applied to securing multi-agent AI systems. The central question: **can cloud sandboxing enforce meaningful security boundaries between agents operating at different trust levels?**

The threat we address is **prompt injection via web search**: when an AI agent fetches live web content, a malicious page can embed instructions that hijack the agent's behavior. We contain this by running all web searches inside an ephemeral AWS Lambda sandbox. The sandbox fetches and processes the content, then returns only a filtered, schema-constrained result — raw web content never reaches the orchestrator's context.

---

## Motivation

Multi-agent AI systems face a class of threats that traditional application security wasn't designed for:

- **Prompt injection** — malicious content in tool outputs (e.g. web search results) can hijack agent behavior
- **Over-privileged context propagation** — agents sharing memory or credentials can leak sensitive state laterally
- **Supply-chain vulnerabilities** — tools or sub-agents pulled in at runtime may carry adversarial payloads

Cloud infrastructure has proven primitives for isolation: serverless functions, IAM roles, Secrets Manager. This project applies those primitives to agent tool calls, using web search as a concrete proof of concept.

---

## Deliverables

| # | Deliverable | Status | Description |
|---|------------|--------|-------------|
| 1 | **`web-search-sandbox` skill** | ✅ Complete | Claude Code skill that provisions a Lambda sandbox on first use and invokes it for each search |
| 2 | **`web-search-teardown` skill** | ✅ Complete | Destroys all sandbox resources; called manually or automatically via Stop hook |
| 3 | **Two-agent demo** | In progress | End-to-end demonstration: orchestrator → sandboxed search → filtered result → teardown |
| 4 | **Written analysis** | In progress | 3–5 page paper — due April 23 |

---

## How It Works

```
┌─────────────────────────────────────────────────────┐
│              Orchestrator (Claude Code)              │
│         uses web-search-sandbox skill                │
└──────────────────────┬──────────────────────────────┘
                       │ boto3 invoke (synchronous)
                       ▼
         ┌─────────────────────────────┐
         │     AWS Lambda Function     │  ← deployed via CloudFormation
         │     (web-search-sandbox-fn) │
         │                             │
         │  1. fetch API key from      │
         │     Secrets Manager         │
         │  2. call OpenAI GPT-4o-mini │
         │     with web_search_preview │
         │  3. extract & filter result │
         └────────────┬────────────────┘
                      │ { query, summary, sources[], timestamp }
                      ▼
┌─────────────────────────────────────────────────────┐
│              Orchestrator (Claude Code)              │
│  uses result — raw web content never seen here       │
│  uses web-search-teardown skill at session end       │
└─────────────────────────────────────────────────────┘
```

**Security properties:**
- The Lambda's IAM role (`LabRole`) is scoped to Secrets Manager and CloudWatch Logs only — no other AWS resources are accessible from inside the sandbox
- The structured response schema (`query`, `summary`, `sources[]`, `timestamp`) is enforced in the Lambda — any injected content outside this schema is discarded before the result crosses back to the orchestrator
- The CloudFormation stack (and with it the Lambda execution environment) is destroyed at session end, leaving no persistent attack surface

---

## Repo Structure

```
.
├── infra/
│   └── sandbox_template.yaml     # CloudFormation: Lambda function (uses LabRole)
├── scripts/
│   ├── invoke_search.py          # Skill 1 backend: ensure stack + invoke Lambda
│   ├── teardown.py               # Skill 2 backend: delete stack (idempotent)
│   └── lambda_handler.py         # Lambda source of truth (embedded inline in CFN)
├── skills/
│   ├── web-search-sandbox/
│   │   └── SKILL.md              # Claude Code skill: sandboxed web search
│   └── web-search-teardown/
│       └── SKILL.md              # Claude Code skill: destroy sandbox resources
├── .claude/
│   └── settings.json             # Stop hook: auto-teardown at session end
├── pyproject.toml
└── README.md
```

---

## Cloud Primitives Used

| Primitive | Role in This Project |
|---|---|
| **AWS Lambda** | Ephemeral, isolated execution environment for each search session |
| **CloudFormation** | Programmatic lifecycle management — stack created at session start, destroyed at end |
| **AWS Secrets Manager** | API key stored outside the agent's context; fetched only inside the sandbox |
| **IAM (LabRole)** | Least-privilege execution — Lambda can only read one secret and write logs |
| **Claude Code hooks** | Session-end automation — Stop hook triggers teardown without manual intervention |

---

## Connection to Course Topics

| Course Topic | How It Appears Here |
|---|---|
| Ephemeral runtimes | Lambda sandbox is created per-session and destroyed on exit — the runtime is fully disposable |
| Resource lifecycle management | CloudFormation stack creation/deletion is the security boundary, not just cost hygiene |
| IAM & least privilege | Lambda role is scoped to one secret; no lateral movement possible from inside the sandbox |
| Multitenancy | Orchestrator and sandbox are modeled as separate tenants with an explicit trust boundary |
| Containers vs. serverless | Lambda (Firecracker microVM) chosen for instant teardown; paper discusses Fargate/EC2 trade-offs |

---

## Written Analysis — Scope

1. **Background** — how existing agent frameworks handle (or fail to handle) trust boundaries
2. **Cloud isolation primitives** — serverless vs. containers vs. VMs, IAM scoping, and their security trade-offs
3. **Threat model** — how the sandbox architecture addresses prompt injection via web search
4. **Demo walkthrough** — the two-skill system as a proof of concept
5. **Limitations** — what this approach doesn't solve (e.g. response content still trusted, no VPC isolation in Lambda default networking)

---

## Course Requirements

| Requirement | Details |
|-------------|---------|
| **Proposal** | 1-paragraph description — **due April 1** ✅ |
| **Written paper** | 3–5 pages — **due April 23** |
| **Presentation** | 5 minutes — **April 28 or 30** *(no extensions)* |
