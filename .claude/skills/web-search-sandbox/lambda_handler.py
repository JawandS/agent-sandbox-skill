"""
lambda_handler.py — AWS Lambda entry point for the web-search sandbox.

Fetches the OpenAI API key from Secrets Manager, calls the OpenAI Responses
API with the web_search_preview tool, and returns a structured, filtered
response. Only the fields defined in the return statement ever leave this
function — raw OpenAI response data is discarded.

This file is the source of truth for the Lambda logic. The CloudFormation
template (infra/sandbox_template.yaml) embeds this code inline via ZipFile.
Keep it under ~4KB to stay within the CloudFormation inline code limit.
"""

import json
import urllib.request
import boto3
import datetime


def handler(event, context):
    sm = boto3.client("secretsmanager", region_name="us-east-1")
    secret = sm.get_secret_value(SecretId="openai-api-key")["SecretString"]

    api_key = json.loads(secret)["api_key"] if secret.strip().startswith("{") else secret.strip()

    query = event.get("query", "")
    if not query:
        return {"error": "Missing required field: query"}

    payload = json.dumps({
        "model": "gpt-4o-mini",
        "tools": [{"type": "web_search_preview"}],
        "input": query,
    }).encode()

    req = urllib.request.Request(
        "https://api.openai.com/v1/responses",
        data=payload,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
    )

    with urllib.request.urlopen(req, timeout=25) as resp:
        data = json.loads(resp.read())

    message = next(o for o in data["output"] if o["type"] == "message")
    content = message["content"][0]
    text = content["text"]

    annotations = content.get("annotations", [])

    sources = [
        {
            "title": a.get("title", ""),
            "url": a["url"],
            "snippet": text[a["start_index"]: a["end_index"]],
        }
        for a in annotations
        if a["type"] == "url_citation"
    ]

    return {
        "query": query,
        "summary": text,
        "sources": sources,
        "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
    }
