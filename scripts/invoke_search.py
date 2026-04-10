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
SECRET_NAME = "openai-api-key"

# Paths relative to this script's location.
TEMPLATE_PATH = os.path.join(os.path.dirname(__file__), "..", "infra", "sandbox_template.yaml")
ENV_PATH = os.path.join(os.path.dirname(__file__), "..", ".env")


def load_dotenv(path):
    """
    Parse a .env file and return a dict of key/value pairs.

    Handles plain values, single-quoted, and double-quoted values.
    Ignores blank lines and comments (#).

    Args:
        path (str): Path to the .env file.

    Returns:
        dict: Parsed key/value pairs.
    """
    env = {}
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            env[key.strip()] = value.strip().strip('"').strip("'")
    return env


def ensure_secret():
    """
    Ensure the OpenAI API key exists in Secrets Manager.

    If the secret already exists, does nothing (fast path).
    If it doesn't exist, reads OPENAI_API_KEY from the .env file in the
    project root and creates the secret.

    Raises:
        FileNotFoundError: If the .env file is missing and the secret doesn't exist.
        KeyError: If OPENAI_API_KEY is not present in the .env file.
    """
    sm = boto3.client("secretsmanager", region_name=REGION)

    try:
        sm.describe_secret(SecretId=SECRET_NAME)
        # Secret already exists — nothing to do.
        return
    except ClientError as e:
        if e.response["Error"]["Code"] != "ResourceNotFoundException":
            raise

    # Secret not found — load from .env and create it.
    print(f"Secret '{SECRET_NAME}' not found. Loading from .env...")
    env = load_dotenv(ENV_PATH)
    api_key = env["OPENAI_API_KEY"]

    sm.create_secret(
        Name=SECRET_NAME,
        SecretString=api_key,
        Description="OpenAI API key for web-search sandbox Lambda",
    )
    print(f"Secret '{SECRET_NAME}' created in Secrets Manager.")


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


def get_lab_role_arn():
    """
    Resolve the LabRole ARN for this AWS Academy account.

    AWS Academy accounts have a pre-existing 'LabRole' that must be used
    instead of creating IAM roles (iam:CreateRole is not permitted).

    Returns:
        str: The LabRole ARN, e.g. arn:aws:iam::123456789012:role/LabRole
    """
    iam = boto3.client("iam", region_name=REGION)
    role = iam.get_role(RoleName="LabRole")
    return role["Role"]["Arn"]


def create_stack(cfn):
    """
    Deploy the sandbox CloudFormation stack and block until creation completes.

    Passes the LabRole ARN as a parameter so the Lambda can assume it.
    Polls every 5 seconds, times out after 5 minutes.

    Args:
        cfn: boto3 CloudFormation client.
    """
    with open(TEMPLATE_PATH) as f:
        template_body = f.read()

    lab_role_arn = get_lab_role_arn()

    print(f"Creating stack '{STACK_NAME}'...")
    cfn.create_stack(
        StackName=STACK_NAME,
        TemplateBody=template_body,
        Parameters=[
            {"ParameterKey": "LabRoleArn", "ParameterValue": lab_role_arn},
        ],
        Capabilities=["CAPABILITY_IAM"],
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

    ensure_secret()   # push API key from .env to Secrets Manager if not already there
    ensure_stack()    # deploy CFN stack if not already up
    result = invoke_lambda(query)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
