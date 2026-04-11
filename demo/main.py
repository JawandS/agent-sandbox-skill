"""
main.py — FastAPI demo app for the agent sandbox skill.

Routes:
  GET  /              Demo UI
  POST /search        Submit a query → returns {job_id}
  GET  /stream/{id}   SSE progress stream for a job
  GET  /admin         Credentials form
  POST /admin         Store credentials in-memory
"""

import asyncio
import json
import uuid
from typing import AsyncGenerator

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from agent import get_infra_status, run_search, run_teardown

app = FastAPI(title="Agent Sandbox Demo")
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# In-memory stores
_credentials: dict = {}
_jobs: dict[str, asyncio.Queue] = {}


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(request, "index.html", {"has_creds": bool(_credentials)})


@app.get("/admin", response_class=HTMLResponse)
async def admin_get(request: Request):
    return templates.TemplateResponse(
        request, "admin.html", {"saved": False, "creds": _credentials}
    )


@app.post("/admin", response_class=HTMLResponse)
async def admin_post(
    request: Request,
    creds_block: str = Form(...),
    region: str = Form("us-east-1"),
):
    parsed = {}
    for line in creds_block.splitlines():
        line = line.strip()
        if "=" in line and not line.startswith("#"):
            key, _, value = line.partition("=")
            parsed[key.strip().lower()] = value.strip()

    missing = [k for k in ("aws_access_key_id", "aws_secret_access_key") if k not in parsed]
    if missing:
        return templates.TemplateResponse(
            request,
            "admin.html",
            {"saved": False, "error": f"Missing fields: {', '.join(missing)}", "creds": _credentials},
        )

    _credentials.update(
        {
            "aws_access_key_id": parsed["aws_access_key_id"],
            "aws_secret_access_key": parsed["aws_secret_access_key"],
            "aws_session_token": parsed.get("aws_session_token") or None,
            "region": region or "us-east-1",
            "creds_block": creds_block,
        }
    )
    return templates.TemplateResponse(
        request, "admin.html", {"saved": True, "creds": _credentials}
    )


@app.post("/admin/json")
async def admin_post_json(creds_block: str = Form(...), region: str = Form("us-east-1")):
    """Same as POST /admin but returns JSON — used by the modal on the index page."""
    parsed = {}
    for line in creds_block.splitlines():
        line = line.strip()
        if "=" in line and not line.startswith("#"):
            key, _, value = line.partition("=")
            parsed[key.strip().lower()] = value.strip()

    missing = [k for k in ("aws_access_key_id", "aws_secret_access_key") if k not in parsed]
    if missing:
        return JSONResponse({"error": f"Missing fields: {', '.join(missing)}"}, status_code=400)

    _credentials.update(
        {
            "aws_access_key_id": parsed["aws_access_key_id"],
            "aws_secret_access_key": parsed["aws_secret_access_key"],
            "aws_session_token": parsed.get("aws_session_token") or None,
            "region": region or "us-east-1",
            "creds_block": creds_block,
        }
    )
    return JSONResponse({"ok": True})


# ---------------------------------------------------------------------------
# Status + Teardown
# ---------------------------------------------------------------------------


@app.get("/status")
async def status():
    if not _credentials:
        return JSONResponse({"secret": "unknown", "stack": "unknown"})
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, get_infra_status, dict(_credentials))
    return JSONResponse(result)


@app.post("/teardown")
async def teardown():
    if not _credentials:
        return JSONResponse({"error": "No credentials set."}, status_code=400)

    job_id = str(uuid.uuid4())
    queue: asyncio.Queue = asyncio.Queue()
    _jobs[job_id] = queue

    async def on_event(event_type: str, message: str):
        await queue.put({"type": event_type, "message": message})

    async def run():
        try:
            await run_teardown(dict(_credentials), on_event)
        except Exception as exc:
            await queue.put({"type": "error", "message": str(exc)})
        finally:
            await queue.put(None)

    asyncio.create_task(run())
    return JSONResponse({"job_id": job_id})


# ---------------------------------------------------------------------------
# Search + SSE
# ---------------------------------------------------------------------------


@app.post("/search")
async def search(request: Request):
    body = await request.json()
    query = (body.get("query") or "").strip()
    if not query:
        return JSONResponse({"error": "query is required"}, status_code=400)
    if not _credentials:
        return JSONResponse({"error": "No credentials set. Visit /admin first."}, status_code=400)

    job_id = str(uuid.uuid4())
    queue: asyncio.Queue = asyncio.Queue()
    _jobs[job_id] = queue

    async def on_event(event_type: str, message: str):
        await queue.put({"type": event_type, "message": message})

    async def run():
        try:
            await run_search(query, dict(_credentials), on_event)
        except Exception as exc:
            await queue.put({"type": "error", "message": str(exc)})
        finally:
            await queue.put(None)  # sentinel

    asyncio.create_task(run())
    return JSONResponse({"job_id": job_id})


@app.get("/stream/{job_id}")
async def stream(job_id: str):
    queue = _jobs.get(job_id)
    if queue is None:
        return JSONResponse({"error": "Unknown job"}, status_code=404)

    async def event_generator() -> AsyncGenerator[str, None]:
        try:
            while True:
                item = await asyncio.wait_for(queue.get(), timeout=120)
                if item is None:
                    yield "event: done\ndata: {}\n\n"
                    break
                payload = json.dumps(item)
                yield f"event: progress\ndata: {payload}\n\n"
        except asyncio.TimeoutError:
            yield 'event: error\ndata: {"type":"error","message":"Timed out waiting for result"}\n\n'
        finally:
            _jobs.pop(job_id, None)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
