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
    """
    Handle a web search request inside the sandbox.

    Args:
        event (dict): Must contain a 'query' key with the search string.
        context: Lambda context object (unused).

    Returns:
        dict: Structured response with keys: query, summary, sources, timestamp.
              Returns {"error": "..."} on validation failure.
    """
    # Fetch the OpenAI API key from Secrets Manager at runtime.
    # The IAM role attached to this Lambda permits GetSecretValue only on this
    # specific secret — no other AWS resources are accessible.
    sm = boto3.client("secretsmanager", region_name="us-east-1")
    secret = sm.get_secret_value(SecretId="openai-api-key")["SecretString"]

    # Support both plain-string secrets ("sk-...") and JSON objects ({"api_key": "sk-..."})
    api_key = json.loads(secret)["api_key"] if secret.strip().startswith("{") else secret.strip()

    query = event.get("query", "")
    if not query:
        return {"error": "Missing required field: query"}

    # Call the OpenAI Responses API with the web_search_preview tool enabled.
    # gpt-4o-mini performs the search and synthesises a plain-text answer.
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

    # The Responses API returns an 'output' array containing both
    # web_search_call items (metadata) and message items (the actual answer).
    # We only need the message.
    message = next(o for o in data["output"] if o["type"] == "message")
    content = message["content"][0]
    text = content["text"]

    # url_citation annotations map character ranges in `text` back to source URLs.
    # We use start_index/end_index to extract the relevant snippet for each source.
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

    # Return only the filtered schema. Nothing from the raw OpenAI response
    # (model metadata, token counts, tool call details, etc.) is included.
    return {
        "query": query,
        "summary": text,
        "sources": sources,
        "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
    }
