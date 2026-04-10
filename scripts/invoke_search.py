"""
invoke_search.py — Ensure the web-search sandbox CFN stack exists, then invoke
the Lambda with the given query and print the structured JSON result.

Usage:
    python scripts/invoke_search.py "your search query here"

The stack is created on first call and reused for subsequent calls in the same
session. Call scripts/teardown.py (or the web-search-teardown skill) when done.
"""

import json
import sys
import os
import boto3
from botocore.exceptions import ClientError

STACK_NAME = "web-search-sandbox"
FUNCTION_NAME = "web-search-sandbox-fn"
REGION = "us-east-1"

# Path to the CloudFormation template, relative to this script's location.
TEMPLATE_PATH = os.path.join(os.path.dirname(__file__), "..", "infra", "sandbox_template.yaml")


def get_stack_status(cfn):
    """
    Return the current CloudFormation stack status, or None if it doesn't exist.

    Args:
        cfn: boto3 CloudFormation client.

    Returns:
        str | None: Stack status string (e.g. 'CREATE_COMPLETE') or None.
    """
    try:
        resp = cfn.describe_stacks(StackName=STACK_NAME)
        return resp["Stacks"][0]["StackStatus"]
    except ClientError as e:
        if "does not exist" in str(e):
            return None
        raise


def create_stack(cfn):
    """
    Deploy the sandbox CloudFormation stack and block until creation completes.

    Uses CAPABILITY_NAMED_IAM because the template creates a named IAM role
    (web-search-sandbox-role). Polls every 5 seconds, times out after 5 minutes.

    Args:
        cfn: boto3 CloudFormation client.
    """
    with open(TEMPLATE_PATH) as f:
        template_body = f.read()

    print(f"Creating stack '{STACK_NAME}'...")
    cfn.create_stack(
        StackName=STACK_NAME,
        TemplateBody=template_body,
        Capabilities=["CAPABILITY_NAMED_IAM"],
    )
    waiter = cfn.get_waiter("stack_create_complete")
    waiter.wait(StackName=STACK_NAME, WaiterConfig={"Delay": 5, "MaxAttempts": 60})
    print("Stack created.")


def ensure_stack():
    """
    Ensure the sandbox stack is in CREATE_COMPLETE before invoking Lambda.

    On first call: creates the stack and waits.
    On subsequent calls: stack already exists, returns immediately (fast path).
    On unexpected states: raises RuntimeError with diagnostic info.
    """
    cfn = boto3.client("cloudformation", region_name=REGION)
    status = get_stack_status(cfn)

    if status is None:
        # First call this session — create the stack.
        create_stack(cfn)
    elif status == "CREATE_IN_PROGRESS":
        # Another process started creation (e.g. concurrent call); just wait.
        print("Stack creation in progress, waiting...")
        waiter = cfn.get_waiter("stack_create_complete")
        waiter.wait(StackName=STACK_NAME, WaiterConfig={"Delay": 5, "MaxAttempts": 60})
    elif status == "ROLLBACK_COMPLETE":
        # Stack failed to create previously. Surface the failure reason.
        resp = cfn.describe_stack_events(StackName=STACK_NAME)
        failed = [
            e["ResourceStatusReason"]
            for e in resp["StackEvents"]
            if "FAILED" in e.get("ResourceStatus", "")
        ]
        raise RuntimeError(f"Stack in ROLLBACK_COMPLETE. Failures: {failed}")
    elif status != "CREATE_COMPLETE":
        raise RuntimeError(f"Stack in unexpected state: {status}")
    # CREATE_COMPLETE — stack is ready, fall through.


def invoke_lambda(query):
    """
    Invoke the sandbox Lambda synchronously and return the parsed JSON result.

    Args:
        query (str): The search query to pass to the Lambda.

    Returns:
        dict: Structured response with keys: query, summary, sources, timestamp.

    Raises:
        RuntimeError: If the Lambda returns a function-level error.
    """
    lambda_client = boto3.client("lambda", region_name=REGION)
    response = lambda_client.invoke(
        FunctionName=FUNCTION_NAME,
        InvocationType="RequestResponse",  # synchronous — blocks until Lambda returns
        Payload=json.dumps({"query": query}).encode(),
    )

    payload = json.loads(response["Payload"].read())

    # FunctionError is set when the Lambda itself raised an exception.
    # This is separate from HTTP-level errors (which raise botocore exceptions).
    if response.get("FunctionError"):
        raise RuntimeError(f"Lambda function error: {payload}")

    return payload


def main():
    if len(sys.argv) < 2:
        print("Usage: python scripts/invoke_search.py <query>")
        sys.exit(1)

    query = " ".join(sys.argv[1:])

    ensure_stack()
    result = invoke_lambda(query)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
