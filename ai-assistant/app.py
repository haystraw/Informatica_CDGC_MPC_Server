"""
AI Assistant — FastAPI app.

Routes:
  GET  /              → redirect to /ui
  GET  /ui            → web chat UI (token gate)
  POST /chat          → chat API (requires X-IDMC-Token header or cookie)
  GET  /health        → health check
"""
VERSION = "20260529"

import logging
import os
from pathlib import Path

import httpx

from fastapi import FastAPI, Request, Cookie
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from mcp_client import McpClient, mcp_session
from gemini import chat
from token_auth import decode_token, TokenError

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-8s %(message)s")
logger = logging.getLogger("ai_assistant")

MCP_SERVER_URL = os.environ.get("MCP_SERVER_URL", "").rstrip("/") + "/mcp"

app = FastAPI(title="IDMC AI Assistant")
app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")


# ---------------------------------------------------------------------------
# Token resolution — header takes priority, then cookie
# ---------------------------------------------------------------------------

def _resolve_token(request: Request, cookie_token: str | None) -> str | None:
    token = request.headers.get("X-IDMC-Token", "").strip()
    if not token and cookie_token:
        token = cookie_token.strip()
    return token or None


# ---------------------------------------------------------------------------
# Chat API
# ---------------------------------------------------------------------------

class ChatRequest(BaseModel):
    message: str
    history: list[dict] = []
    pod: str = ""


@app.post("/chat")
async def chat_endpoint(
    body: ChatRequest,
    request: Request,
    idmc_token: str | None = Cookie(default=None),
):
    token = _resolve_token(request, idmc_token)
    if not token:
        return JSONResponse({"error": "No token. Please enroll first."}, status_code=401)

    try:
        decode_token(token)  # validate without hitting Informatica
    except TokenError as e:
        return JSONResponse({"error": str(e)}, status_code=401)

    if not MCP_SERVER_URL or MCP_SERVER_URL == "/mcp":
        return JSONResponse({"error": "MCP_SERVER_URL is not configured."}, status_code=500)

    try:
        mcp = McpClient(server_url=MCP_SERVER_URL, token=token)
        async with mcp_session(MCP_SERVER_URL, token) as session:
            mcp.set_session(session)
            response, trace = await chat(
                user_message=body.message,
                mcp=mcp,
                history=body.history,
                pod=body.pod,
            )
        return JSONResponse({"response": response, "trace": trace})
    except Exception as e:
        logger.exception("Chat error")
        return JSONResponse({"error": str(e)}, status_code=500)


# ---------------------------------------------------------------------------
# Token info — decode token and fetch org name from IDMC
# ---------------------------------------------------------------------------

@app.post("/token-info")
async def token_info(request: Request):
    body = await request.json()
    token = body.get("token", "").strip()
    if not token:
        return JSONResponse({"error": "No token provided"}, status_code=400)

    try:
        creds = decode_token(token)
    except TokenError as e:
        return JSONResponse({"error": str(e)}, status_code=401)

    pod      = creds.get("pod", "")
    username = creds.get("username", "")

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                f"https://{pod}.informaticacloud.com/identity-service/api/v1/Login",
                json={"username": username, "password": creds.get("password", "")},
                headers={"Content-Type": "application/json"},
            )
        if resp.status_code == 200:
            data = resp.json()
            org_name = data.get("orgName") or data.get("currentOrgName") or pod
        else:
            org_name = pod
    except Exception:
        org_name = pod

    return JSONResponse({
        "username": username,
        "pod": pod,
        "org_name": org_name,
    })


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

@app.get("/health")
async def health():
    return {"status": "ok", "version": VERSION}


# ---------------------------------------------------------------------------
# Web UI — served from static/index.html
# ---------------------------------------------------------------------------

@app.get("/ui", response_class=HTMLResponse)
async def ui():
    html_path = Path(__file__).parent / "static" / "index.html"
    return HTMLResponse(html_path.read_text(encoding="utf-8"))


@app.get("/", response_class=HTMLResponse)
async def root():
    return HTMLResponse('<meta http-equiv="refresh" content="0;url=/ui">', status_code=302)
