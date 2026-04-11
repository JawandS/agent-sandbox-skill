"""
agent.py — Orchestrator logic with progress callbacks.

Each stage calls `on_event(type, message)` so the SSE endpoint can stream
real-time updates to the frontend.
"""

import asyncio
import json
import os

import boto3
from botocore.exceptions import ClientError

STACK_NAME = "web-search-sandbox"
FUNCTION_NAME = "web-search-sandbox-fn"
SECRET_NAME = "openai-api-key"

_here = os.path.dirname(os.path.abspath(__file__))
_candidates = [
    os.path.join(_here, "infra", "sandbox_template.yaml"),
    os.path.join(_here, "..", "infra", "sandbox_template.yaml"),
]
TEMPLATE_PATH = next((p for p in _candidates if os.path.exists(p)), _candidates[-1])


def _client(service: str, credentials: dict):
    kwargs = {
        "region_name": credentials.get("region", "us-east-1"),
        "aws_access_key_id": credentials["aws_access_key_id"],
        "aws_secret_access_key": credentials["aws_secret_access_key"],
    }
    if credentials.get("aws_session_token"):
        kwargs["aws_session_token"] = credentials["aws_session_token"]
    return boto3.client(service, **kwargs)


def _check_secret(credentials: dict) -> bool:
    """Return True if secret exists, False if not."""
    sm = _client("secretsmanager", credentials)
    try:
        sm.describe_secret(SecretId=SECRET_NAME)
        return True
    except ClientError as e:
        if e.response["Error"]["Code"] == "ResourceNotFoundException":
            return False
        raise


def _get_stack_status(credentials: dict):
    """Return stack status string, or None if stack doesn't exist."""
    cfn = _client("cloudformation", credentials)
    try:
        resp = cfn.describe_stacks(StackName=STACK_NAME)
        return resp["Stacks"][0]["StackStatus"]
    except ClientError as e:
        if "does not exist" in str(e):
            return None
        raise


def _get_lab_role_arn(credentials: dict) -> str:
    iam = _client("iam", credentials)
    role = iam.get_role(RoleName="LabRole")
    return role["Role"]["Arn"]


def _create_stack(credentials: dict):
    cfn = _client("cloudformation", credentials)
    with open(TEMPLATE_PATH) as f:
        template_body = f.read()
    lab_role_arn = _get_lab_role_arn(credentials)
    cfn.create_stack(
        StackName=STACK_NAME,
        TemplateBody=template_body,
        Parameters=[{"ParameterKey": "LabRoleArn", "ParameterValue": lab_role_arn}],
        Capabilities=["CAPABILITY_IAM"],
    )
    waiter = cfn.get_waiter("stack_create_complete")
    waiter.wait(StackName=STACK_NAME, WaiterConfig={"Delay": 5, "MaxAttempts": 60})


def _delete_stack(credentials: dict):
    cfn = _client("cloudformation", credentials)
    try:
        resp = cfn.describe_stacks(StackName=STACK_NAME)
        status = resp["Stacks"][0]["StackStatus"]
    except ClientError as e:
        if "does not exist" in str(e):
            return
        raise
    if status == "DELETE_COMPLETE":
        return
    if status != "DELETE_IN_PROGRESS":
        cfn.delete_stack(StackName=STACK_NAME)
    waiter = cfn.get_waiter("stack_delete_complete")
    waiter.wait(StackName=STACK_NAME, WaiterConfig={"Delay": 5, "MaxAttempts": 60})


def _invoke_lambda(query: str, credentials: dict) -> dict:
    lc = _client("lambda", credentials)
    response = lc.invoke(
        FunctionName=FUNCTION_NAME,
        InvocationType="RequestResponse",
        Payload=json.dumps({"query": query}).encode(),
    )
    payload = json.loads(response["Payload"].read())
    if response.get("FunctionError"):
        raise RuntimeError(f"Lambda error: {payload}")
    return payload


def get_infra_status(credentials: dict) -> dict:
    """Synchronously check secret + stack status. Safe to call from executor."""
    result = {"secret": "unknown", "stack": "unknown"}
    try:
        result["secret"] = "set" if _check_secret(credentials) else "not_set"
    except Exception:
        pass
    try:
        status = _get_stack_status(credentials)
        if status == "CREATE_COMPLETE":
            result["stack"] = "active"
        elif status is None or status == "DELETE_COMPLETE":
            result["stack"] = "inactive"
        elif status in ("CREATE_IN_PROGRESS", "DELETE_IN_PROGRESS"):
            result["stack"] = "deploying" if "CREATE" in status else "deleting"
        else:
            result["stack"] = "unknown"
    except Exception:
        pass
    return result


async def run_search(query: str, credentials: dict, on_event) -> dict:
    loop = asyncio.get_event_loop()

    await on_event("orchestrator:start", "Orchestrator activated")

    # --- Secrets Manager ---
    await on_event("secret:check", "Checking Secrets Manager for OpenAI key...")
    secret_exists = await loop.run_in_executor(None, _check_secret, credentials)
    if secret_exists:
        await on_event("secret:found", "OpenAI key confirmed in Secrets Manager")
    else:
        await on_event("secret:missing", (
            f"Secret '{SECRET_NAME}' not found. "
            "Run scripts/invoke_search.py once to seed it from .env."
        ))
        raise RuntimeError(f"Secret '{SECRET_NAME}' not found in Secrets Manager")

    # --- CloudFormation stack ---
    await on_event("stack:check", "Checking CloudFormation stack...")
    status = await loop.run_in_executor(None, _get_stack_status, credentials)

    if status is None:
        await on_event("stack:creating", "Deploying Lambda sandbox (~30–60s)...")
        await loop.run_in_executor(None, _create_stack, credentials)
        await on_event("stack:ready", "Stack deployed successfully")
    elif status == "CREATE_IN_PROGRESS":
        await on_event("stack:creating", "Stack creation in progress, waiting...")
        cfn = await loop.run_in_executor(None, lambda: _client("cloudformation", credentials))
        waiter = cfn.get_waiter("stack_create_complete")
        await loop.run_in_executor(
            None, lambda: waiter.wait(StackName=STACK_NAME, WaiterConfig={"Delay": 5, "MaxAttempts": 60})
        )
        await on_event("stack:ready", "Stack ready")
    elif status == "CREATE_COMPLETE":
        await on_event("stack:ready", "Stack already active — skipping deploy")
    else:
        raise RuntimeError(f"Stack in unexpected state: {status}")

    # --- Lambda invocation ---
    await on_event("lambda:invoking", f'Invoking Lambda sandbox with query: "{query}"')
    result = await loop.run_in_executor(None, _invoke_lambda, query, credentials)
    await on_event("lambda:done", json.dumps(result))

    return result


async def run_teardown(credentials: dict, on_event) -> None:
    loop = asyncio.get_event_loop()

    await on_event("teardown:start", "Ending session — starting cleanup...")

    status = await loop.run_in_executor(None, _get_stack_status, credentials)
    if status is None or status == "DELETE_COMPLETE":
        await on_event("teardown:stack_done", "Stack already inactive — nothing to delete")
    else:
        await on_event("teardown:stack_deleting", f"Deleting CloudFormation stack (status: {status})...")
        await loop.run_in_executor(None, _delete_stack, credentials)
        await on_event("teardown:stack_done", "Stack deleted")

    await on_event("teardown:done", "Session ended. All cloud resources removed.")
