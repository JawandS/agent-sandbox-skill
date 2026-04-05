# Cloud-Native Security for Multi-Agent AI Systems

> **CSCI 420 – Cloud Computing | William & Mary | Spring 2026**
> **Project Type:** Cloudify Your Interest
> **Team size:** 2–3 students

---

## Overview

This project investigates how cloud-native principles — isolation, ephemeral environments, and resource lifecycle management — can be applied to securing multi-agent AI systems. The central question: **can cloud sandboxing enforce meaningful security boundaries between agents operating at different trust levels?**

We demonstrate this through a two-agent system where an orchestrator delegates tasks to sub-agents that run inside fresh, isolated cloud sandboxes. Each sub-agent spins up, does its work, filters its output, and tears down its own resources — giving us a model for containing prompt injection and supply-chain threats at the infrastructure level.

---

## Motivation

Multi-agent AI systems face a class of threats that traditional application security wasn't designed for:

- **Prompt injection** — a malicious input to one agent can hijack the behavior of others in the pipeline
- **Supply-chain vulnerabilities** — tools, plugins, or sub-agents pulled in at runtime may carry adversarial payloads
- **Over-privileged context propagation** — agents sharing memory or credentials can leak sensitive state laterally

Cloud infrastructure already has proven primitives for isolation: containers, VMs, VPCs, IAM roles. This project asks whether those primitives, applied to agent lifecycles, can provide a practical security model.

---

## Deliverables

| # | Deliverable | Description |
|---|------------|-------------|
| 1 | **Sub-agent creation skill** | Spawns a sub-agent and simultaneously provisions a cloud sandbox (container or lightweight VM on AWS) with appropriately scoped IAM permissions |
| 2 | **Response & teardown skill** | Handles sub-agent response — applies context filtering to strip sensitive/irrelevant data — then tears down all cloud resources on completion |
| 3 | **Two-agent demo** | End-to-end demonstration using both skills: orchestrator receives a task → delegates to sandboxed sub-agent → receives filtered result → sandbox destroyed |
| 4 | **Written analysis** | 3–5 page paper linking cloud isolation primitives to agent security challenges, with the demo as a proof of concept |

---

## Technical Approach

```
┌─────────────────────────────────────────────────────┐
│                  Orchestrator Agent                  │
│              (trusted, persistent env)               │
└──────────────────────┬──────────────────────────────┘
                       │ task dispatch
                       ▼
         ┌─────────────────────────┐
         │   Sub-agent Creation    │  ← Skill 1
         │  + Cloud Sandbox Spin-up│
         │  (fresh container / VM) │
         └────────────┬────────────┘
                      │ executes in isolation
                      ▼
         ┌─────────────────────────┐
         │      Sub-Agent          │
         │  (ephemeral, scoped IAM)│
         │  · does work            │
         │  · filters context      │
         └────────────┬────────────┘
                      │ cleaned result
                      ▼
         ┌─────────────────────────┐
         │  Response + Teardown    │  ← Skill 2
         │  · returns result       │
         │  · destroys all cloud   │
         │    resources            │
         └─────────────────────────┘
```

**Cloud primitives used:**
- **AWS EC2 / containers** — ephemeral runtime isolation
- **IAM roles** — least-privilege permissions scoped per sub-agent
- **VPCs** — network-level isolation between sandbox and host environment
- **CloudFormation** — programmatic resource lifecycle management

---

## Written Analysis — Scope

The writeup will cover:

1. **Background** — how existing agent frameworks handle (or fail to handle) trust boundaries
2. **Cloud isolation primitives** — containers vs. VMs, IAM scoping, VPC segmentation, and their security trade-offs (connecting to course material on multitenancy and ephemeral runtimes)
3. **Threat model** — how the sandbox architecture addresses prompt injection and supply-chain attacks
4. **Demo walkthrough** — the two-agent system as a proof of concept
5. **Limitations and open questions** — what this approach doesn't solve; directions for future work

---

## Course Requirements

| Requirement | Details |
|-------------|---------|
| **Team** | 2–3 students (Cloudify Your Interest track) |
| **Proposal** | 1-paragraph description — **due Wednesday, April 1** |
| **Written paper** | 3–5 pages — **due April 23** |
| **Presentation** | 5 minutes, live or pre-recorded — **shared in class April 28 or 30** *(no extensions)* |

**Grading criteria:**
- Correctness of technical content in the writeup
- Clarity of the presentation
- Insightfulness brought to the topic

---

## Repo Structure (planned)

```
.
├── README.md
├── demo/
│   ├── orchestrator.py        # orchestrator agent
│   └── subagent.py            # sub-agent logic
├── skills/
│   ├── create_sandbox.py      # Skill 1: sub-agent + cloud sandbox creation
│   └── respond_and_teardown.py # Skill 2: context filter + resource teardown
├── infra/
│   └── sandbox_template.yaml  # CloudFormation / IaC for sandbox provisioning
└── writeup/
    └── paper.md               # 3–5 page written analysis
```

---

## Connection to Course Topics

| Course Topic | How It Appears Here |
|---|---|
| Containers vs. VMs | Isolation trade-off for sub-agent sandboxes |
| Multitenancy | Modeling agents at different trust levels as "tenants" |
| Ephemeral runtimes | Sub-agents as fully disposable execution environments |
| IAM & VPCs | Enforcing least-privilege and network isolation per agent |
| Resource lifecycle management | Automated teardown as a security property, not just cost hygiene |