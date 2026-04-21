---
name: web-search-teardown
description: Use when the session is ending or you are done with web searches and want to destroy the sandbox infrastructure. Deletes the CloudFormation stack created by web-search-sandbox.
---

# Web Search Teardown

Deletes the web-search sandbox CloudFormation stack, destroying the Lambda
function and its scoped IAM role. Safe to run even if the stack was never
created or has already been deleted.

## When to Use

- At the end of a session after using `web-search-sandbox`
- When you want to explicitly confirm all sandbox resources are gone

Note: The Claude Code Stop hook calls this automatically at session end.
Manual invocation is only needed if you want to tear down mid-session.

## Usage

```bash
cd /home/js/cloud-computing/agent-sandbox-skill
uv run python .claude/skills/web-search-teardown/teardown.py
```

The script will:
1. Check if the stack exists
2. If yes: delete it and wait for `DELETE_COMPLETE`
3. If no: exit cleanly with no error

Expected output on success:
```
Deleting stack 'web-search-sandbox' (current status: CREATE_COMPLETE)...
Stack deleted successfully.
```

Expected output if stack never existed:
```
Stack does not exist. Nothing to tear down.
```
