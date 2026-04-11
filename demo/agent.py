"""
agent.py — Orchestrator logic that wraps invoke_search.py with progress callbacks.

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

# Works both locally (demo/../infra/) and in Docker (/app/infra/)
_here = os.path.dirname(os.path.abspath(__file__))
_candidates = [
    os.path.join(_here, "infra", "sandbox_template.yaml"),
    os.path.join(_here, "..", "infra", "sandbox_template.yaml"),
]
TEMPLATE_PATH = next((p for p in _candidates if os.path.exists(p)), _candidates[-1])


def _client(service: str, credentials: dict):
    """Create a boto3 client with explicit credentials from the in-memory store."""
    kwargs = {
        "region_name": credentials.get("region", "us-east-1"),
        "aws_access_key_id": credentials["aws_access_key_id"],
        "aws_secret_access_key": credentials["aws_secret_access_key"],
    }
    if credentials.get("aws_session_token"):
        kwargs["aws_session_token"] = credentials["aws_session_token"]
    return boto3.client(service, **kwargs)


def _ensure_secret(credentials: dict):
    """Verify the OpenAI secret exists in Secrets Manager (managed externally via .env)."""
    sm = _client("secretsmanager", credentials)
    try:
        sm.describe_secret(SecretId=SECRET_NAME)
    except ClientError as e:
        if e.response["Error"]["Code"] == "ResourceNotFoundException":
            raise RuntimeError(
                f"Secret '{SECRET_NAME}' not found in Secrets Manager. "
                "Run scripts/invoke_search.py once to seed it from .env."
            )
        raise


def _get_stack_status(credentials: dict):
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


async def run_search(query: str, credentials: dict, on_event) -> dict:
    """
    Run the full orchestrator flow, emitting progress events at each stage.

    Args:
        query: The search query.
        credentials: Dict with aws_access_key_id, aws_secret_access_key,
                     optionally aws_session_token, region, and openai_api_key.
        on_event: Async callable(type: str, message: str).

    Returns:
        The Lambda result dict {query, summary, sources, timestamp}.
    """
    loop = asyncio.get_event_loop()

    await on_event("orchestrator:start", "Orchestrator activated")

    # --- Secrets Manager ---
    await on_event("secret:check", "Checking Secrets Manager for OpenAI key...")
    await loop.run_in_executor(None, _ensure_secret, credentials)

    # --- CloudFormation stack ---
    await on_event("stack:check", "Checking CloudFormation stack...")
    status = await loop.run_in_executor(None, _get_stack_status, credentials)

    if status is None:
        await on_event("stack:creating", "Deploying Lambda sandbox (~30–60s)...")
        await loop.run_in_executor(None, _create_stack, credentials)
        await on_event("stack:ready", "Stack deployed successfully")
    elif status == "CREATE_IN_PROGRESS":
        await on_event("stack:creating", "Stack creation already in progress, waiting...")
        cfn = await loop.run_in_executor(
            None, lambda: _client("cloudformation", credentials)
        )
        waiter = cfn.get_waiter("stack_create_complete")
        await loop.run_in_executor(
            None,
            lambda: waiter.wait(
                StackName=STACK_NAME, WaiterConfig={"Delay": 5, "MaxAttempts": 60}
            ),
        )
        await on_event("stack:ready", "Stack ready")
    elif status == "CREATE_COMPLETE":
        await on_event("stack:ready", "Stack already exists — skipping deploy")
    else:
        raise RuntimeError(f"Stack in unexpected state: {status}")

    # --- Lambda invocation ---
    await on_event("lambda:invoking", f'Invoking Lambda with query: "{query}"')
    result = await loop.run_in_executor(None, _invoke_lambda, query, credentials)
    await on_event("lambda:done", json.dumps(result))

    return result
