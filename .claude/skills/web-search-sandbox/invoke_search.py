"""
invoke_search.py — Ensure the web-search sandbox CFN stack exists, then invoke
the Lambda with the given query and print the structured JSON result.

Usage:
    python .claude/skills/web-search-sandbox/invoke_search.py "your search query here"

The stack is created on first call and reused for subsequent calls in the same
session. Call teardown.py (or the web-search-teardown skill) when done.
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
TEMPLATE_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "..", "infra", "sandbox_template.yaml")
ENV_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "..", ".env")


def load_dotenv(path):
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
    sm = boto3.client("secretsmanager", region_name=REGION)

    try:
        sm.describe_secret(SecretId=SECRET_NAME)
        return
    except ClientError as e:
        if e.response["Error"]["Code"] != "ResourceNotFoundException":
            raise

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
    try:
        resp = cfn.describe_stacks(StackName=STACK_NAME)
        return resp["Stacks"][0]["StackStatus"]
    except ClientError as e:
        if "does not exist" in str(e):
            return None
        raise


def get_lab_role_arn():
    iam = boto3.client("iam", region_name=REGION)
    role = iam.get_role(RoleName="LabRole")
    return role["Role"]["Arn"]


def create_stack(cfn):
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
    cfn = boto3.client("cloudformation", region_name=REGION)
    status = get_stack_status(cfn)

    if status is None:
        create_stack(cfn)
    elif status == "CREATE_IN_PROGRESS":
        print("Stack creation in progress, waiting...")
        waiter = cfn.get_waiter("stack_create_complete")
        waiter.wait(StackName=STACK_NAME, WaiterConfig={"Delay": 5, "MaxAttempts": 60})
    elif status == "ROLLBACK_COMPLETE":
        resp = cfn.describe_stack_events(StackName=STACK_NAME)
        failed = [
            e["ResourceStatusReason"]
            for e in resp["StackEvents"]
            if "FAILED" in e.get("ResourceStatus", "")
        ]
        raise RuntimeError(f"Stack in ROLLBACK_COMPLETE. Failures: {failed}")
    elif status != "CREATE_COMPLETE":
        raise RuntimeError(f"Stack in unexpected state: {status}")


def invoke_lambda(query):
    lambda_client = boto3.client("lambda", region_name=REGION)
    response = lambda_client.invoke(
        FunctionName=FUNCTION_NAME,
        InvocationType="RequestResponse",
        Payload=json.dumps({"query": query}).encode(),
    )

    payload = json.loads(response["Payload"].read())

    if response.get("FunctionError"):
        raise RuntimeError(f"Lambda function error: {payload}")

    return payload


def main():
    if len(sys.argv) < 2:
        print("Usage: uv run python .claude/skills/web-search-sandbox/invoke_search.py <query>")
        sys.exit(1)

    query = " ".join(sys.argv[1:])

    ensure_secret()
    ensure_stack()
    result = invoke_lambda(query)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
