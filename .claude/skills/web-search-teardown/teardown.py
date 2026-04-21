"""
teardown.py — Delete the web-search sandbox CloudFormation stack.

Safe to run when no stack exists (idempotent). Called automatically by the
Claude Code Stop hook at session end, and manually via the web-search-teardown
skill.

Usage:
    uv run python .claude/skills/web-search-teardown/teardown.py
"""

import sys
import boto3
from botocore.exceptions import ClientError

STACK_NAME = "web-search-sandbox"
REGION = "us-east-1"


def main():
    cfn = boto3.client("cloudformation", region_name=REGION)

    try:
        resp = cfn.describe_stacks(StackName=STACK_NAME)
        status = resp["Stacks"][0]["StackStatus"]
    except ClientError as e:
        if "does not exist" in str(e):
            print("Stack does not exist. Nothing to tear down.")
            return
        raise

    if status == "DELETE_COMPLETE":
        print("Stack already deleted.")
        return

    if status == "DELETE_IN_PROGRESS":
        print("Stack deletion already in progress, waiting...")
    else:
        print(f"Deleting stack '{STACK_NAME}' (current status: {status})...")
        cfn.delete_stack(StackName=STACK_NAME)

    waiter = cfn.get_waiter("stack_delete_complete")
    waiter.wait(StackName=STACK_NAME, WaiterConfig={"Delay": 5, "MaxAttempts": 60})
    print("Stack deleted successfully.")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"Teardown error (non-fatal): {e}", file=sys.stderr)
        sys.exit(0)
