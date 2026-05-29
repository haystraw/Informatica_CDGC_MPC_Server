"""
IDMC MCP Server — container entry point.

Adds enrollment UI routes directly onto the FastMCP app, then runs it via
mcp.run() so the MCP task group is properly initialised. Token auth is handled
via a raw ASGI middleware that never buffers the response stream.
"""
VERSION = "20260529"

import logging
import os
import textwrap
from datetime import datetime, timedelta
from typing import Optional
import threading

logger = logging.getLogger("idmc.mcp")

from fastapi import Form, Query, Request
from fastapi.responses import HTMLResponse
from starlette.responses import Response
from starlette.types import ASGIApp, Receive, Scope, Send

from token_auth import TokenError, create_token, decode_token
from auth import request_credentials

# ---------------------------------------------------------------------------
# Config from environment
# ---------------------------------------------------------------------------
ENROLL_PASSWORD = os.environ.get("ENROLL_PASSWORD", "").strip()
ENCRYPTION_KEY  = os.environ.get("ENCRYPTION_KEY", "").strip()

# ---------------------------------------------------------------------------
# Brute-force lockout — per IP, in memory
# ---------------------------------------------------------------------------
_lockout_lock = threading.Lock()
_failed_attempts: dict = {}

MAX_ATTEMPTS    = 3
LOCKOUT_MINUTES = 5


def _get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _check_lockout(ip: str) -> Optional[str]:
    with _lockout_lock:
        state = _failed_attempts.get(ip)
        if not state:
            return None
        if state["locked_until"] and datetime.utcnow() < state["locked_until"]:
            remaining = int((state["locked_until"] - datetime.utcnow()).total_seconds() / 60) + 1
            return f"Too many failed attempts. Try again in {remaining} minute(s)."
        return None


def _record_failure(ip: str) -> Optional[str]:
    with _lockout_lock:
        state = _failed_attempts.setdefault(ip, {"count": 0, "locked_until": None})
        state["count"] += 1
        if state["count"] >= MAX_ATTEMPTS:
            state["locked_until"] = datetime.utcnow() + timedelta(minutes=LOCKOUT_MINUTES)
            return f"Too many failed attempts. This connection is frozen for {LOCKOUT_MINUTES} minutes."
        remaining = MAX_ATTEMPTS - state["count"]
        return f"Incorrect password. {remaining} attempt(s) remaining before lockout."


def _clear_failures(ip: str) -> None:
    with _lockout_lock:
        _failed_attempts.pop(ip, None)


# ---------------------------------------------------------------------------
# Import MCP server instance — must come after env config above
# ---------------------------------------------------------------------------
from server import mcp  # noqa: E402


# ---------------------------------------------------------------------------
# Token middleware — raw ASGI, never buffers the stream
# ---------------------------------------------------------------------------

class TokenMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and scope.get("path", "").startswith("/mcp"):
            headers = dict(scope.get("headers", []))
            token = headers.get(b"x-idmc-token", b"").decode().strip()

            if not token:
                await Response('{"error": "X-IDMC-Token header is required"}',
                               status_code=401, media_type="application/json")(scope, receive, send)
                return

            try:
                creds = decode_token(token)
            except TokenError as e:
                await Response(f'{{"error": "{e}"}}',
                               status_code=401, media_type="application/json")(scope, receive, send)
                return

            forwarded = headers.get(b"x-forwarded-for", b"").decode()
            ip = forwarded.split(",")[0].strip() if forwarded else (scope.get("client") or ("?", 0))[0]
            logger.info("MCP connect: pod=%s user=%s ip=%s path=%s",
                        creds.get("pod", "?"), creds.get("username", "?"),
                        ip, scope.get("path", "?"))

            tok = request_credentials.set(creds)
            try:
                await self.app(scope, receive, send)
            finally:
                request_credentials.reset(tok)
            return

        await self.app(scope, receive, send)


# ---------------------------------------------------------------------------
# Enroll UI helpers
# ---------------------------------------------------------------------------

_CSS = """
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
           background: #f5f5f5; color: #333; padding: 40px 20px; }
    .container { max-width: 720px; margin: 0 auto; }
    header { background: #1a56a0; color: white; border-radius: 8px 8px 0 0; padding: 24px 32px; }
    header h1 { font-size: 1.5rem; font-weight: 600; }
    header p  { margin-top: 6px; opacity: 0.85; font-size: 0.95rem; }
    .card { background: white; border-radius: 0 0 8px 8px; padding: 32px;
            box-shadow: 0 2px 8px rgba(0,0,0,.1); }
    label { display: block; font-weight: 500; margin-bottom: 6px; margin-top: 20px; }
    label:first-of-type { margin-top: 0; }
    input[type=text], input[type=password] { width: 100%; padding: 10px 12px;
        border: 1px solid #ccc; border-radius: 6px; font-size: 1rem; }
    input:focus { outline: none; border-color: #1a56a0; box-shadow: 0 0 0 3px rgba(26,86,160,.15); }
    .hint { font-size: 0.82rem; color: #666; margin-top: 4px; }
    button { margin-top: 24px; background: #1a56a0; color: white; border: none;
             padding: 11px 28px; border-radius: 6px; font-size: 1rem; cursor: pointer; font-weight: 500; }
    button:hover { background: #154480; }
    .error { background: #fff0f0; border: 1px solid #f5c6c6; color: #c0392b;
             border-radius: 6px; padding: 12px 16px; margin-top: 20px; }
    .result { margin-top: 32px; border-top: 2px solid #e8e8e8; padding-top: 24px; }
    .result h2 { font-size: 1.1rem; margin-bottom: 8px; margin-top: 20px; color: #1a56a0; }
    .result h2:first-child { margin-top: 0; }
    .result p { font-size: 0.9rem; color: #555; margin-bottom: 8px; }
    textarea { width: 100%; font-family: "SFMono-Regular", Consolas, monospace;
               font-size: 0.82rem; padding: 12px; border: 1px solid #ccc;
               border-radius: 6px; background: #fafafa; resize: vertical; height: 80px; }
    code { background: #f0f0f0; padding: 2px 5px; border-radius: 3px; font-size: 0.85em; }
"""

def _page(body: str) -> str:
    return f"""<!DOCTYPE html><html lang="en"><head>
  <meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>IDMC MCP Server — Enrollment</title><style>{_CSS}</style></head>
<body><div class="container">
  <header><h1>IDMC MCP Server</h1>
    <p>Enroll your Informatica credentials to generate a connection token.</p></header>
  <div class="card">{body}</div>
</div></body></html>"""

def _password_gate(error: str = "") -> str:
    err = f'<div class="error">{error}</div>' if error else ""
    return _page(f"""
      <form method="POST" action="/enroll">
        <input type="hidden" name="step" value="auth">
        <label for="ep">Enrollment Password</label>
        <input type="password" id="ep" name="enroll_password"
               placeholder="Enter the enrollment password" required autofocus>
        <button type="submit">Continue</button>
      </form>{err}""")

def _credentials_form(verified_password: str, error: str = "", pod: str = "") -> str:
    err = f'<div class="error">{error}</div>' if error else ""
    return _page(f"""
      <form method="POST" action="/enroll">
        <input type="hidden" name="step" value="enroll">
        <input type="hidden" name="enroll_password" value="{verified_password}">
        <label for="pod">IDMC Pod</label>
        <input type="text" id="pod" name="pod" value="{pod}"
               placeholder="e.g. dm-us" required autofocus>
        <div class="hint">Prefix from your IDMC login URL:
          <em>https://&lt;pod&gt;.informaticacloud.com</em></div>
        <label for="username">Username</label>
        <input type="text" id="username" name="username"
               placeholder="your.email@company.com" required>
        <label for="password">Password</label>
        <input type="password" id="password" name="password"
               placeholder="Your IDMC password" required>
        <button type="submit">Generate Token</button>
      </form>{err}""")

def _results_page(token: str, pod: str, server_url: str) -> str:
    mcp_url = f"{server_url}/mcp"

    claude_code_config = textwrap.dedent(f"""\
        {{
          "mcpServers": {{
            "idmc": {{
              "type": "http",
              "url": "{mcp_url}",
              "headers": {{
                "X-IDMC-Token": "{token}"
              }}
            }}
          }}
        }}""")

    claude_desktop_config = textwrap.dedent(f"""\
        {{
          "mcpServers": {{
            "idmc": {{
              "type": "http",
              "url": "{mcp_url}",
              "headers": {{
                "X-IDMC-Token": "{token}"
              }}
            }}
          }}
        }}""")

    return _page(f"""
      <div class="result">
        <h2>Your Token</h2>
        <p>Copy this token and keep it private — it contains your encrypted credentials.</p>
        <textarea readonly onclick="this.select()">{token}</textarea>

        <h2>Claude Code (VS Code / CLI)</h2>
        <p>Add to <code>~/.claude/settings.json</code> (Windows: <code>%USERPROFILE%\.claude\settings.json</code>):</p>
        <textarea readonly onclick="this.select()" style="height:180px">{claude_code_config}</textarea>

        <h2>Claude Desktop</h2>
        <p>Add to <code>%APPDATA%\Claude\claude_desktop_config.json</code>
           (Windows) or <code>~/Library/Application Support/Claude/claude_desktop_config.json</code> (macOS):</p>
        <textarea readonly onclick="this.select()" style="height:180px">{claude_desktop_config}</textarea>

        <h2>Any other MCP client</h2>
        <p>URL: <code>{mcp_url}</code><br>
           Header: <code>X-IDMC-Token: {token}</code></p>
      </div>""")


# ---------------------------------------------------------------------------
# Register enrollment routes on the MCP app's internal FastAPI router
# ---------------------------------------------------------------------------

@mcp.custom_route("/enroll", methods=["GET"])
async def enroll_get(request: Request) -> HTMLResponse:
    p = request.query_params.get("p")
    if p is not None:
        if not ENROLL_PASSWORD:
            return HTMLResponse(_password_gate(error="Server misconfiguration: ENROLL_PASSWORD is not set."), status_code=500)
        ip = _get_client_ip(request)
        if msg := _check_lockout(ip):
            return HTMLResponse(_password_gate(error=msg), status_code=429)
        if p != ENROLL_PASSWORD:
            return HTMLResponse(_password_gate(error=_record_failure(ip)), status_code=403)
        _clear_failures(ip)
        return HTMLResponse(_credentials_form(verified_password=p))
    return HTMLResponse(_password_gate())


@mcp.custom_route("/enroll", methods=["POST"])
async def enroll_post(request: Request) -> HTMLResponse:
    if not ENROLL_PASSWORD:
        return HTMLResponse(_password_gate(error="Server misconfiguration: ENROLL_PASSWORD is not set."), status_code=500)
    if not ENCRYPTION_KEY:
        return HTMLResponse(_password_gate(error="Server misconfiguration: ENCRYPTION_KEY is not set."), status_code=500)

    form = await request.form()
    step             = form.get("step", "")
    enroll_password  = form.get("enroll_password", "")
    pod              = form.get("pod", "")
    username         = form.get("username", "")
    password         = form.get("password", "")

    ip = _get_client_ip(request)
    if msg := _check_lockout(ip):
        return HTMLResponse(_password_gate(error=msg), status_code=429)
    if enroll_password != ENROLL_PASSWORD:
        return HTMLResponse(_password_gate(error=_record_failure(ip)), status_code=403)
    _clear_failures(ip)

    if step == "auth":
        return HTMLResponse(_credentials_form(verified_password=enroll_password))

    try:
        token = create_token(pod=pod.strip(), username=username.strip(), password=password)
    except TokenError as e:
        return HTMLResponse(_credentials_form(verified_password=enroll_password, error=str(e), pod=pod), status_code=500)

    server_url = str(request.base_url).rstrip("/")
    return HTMLResponse(_results_page(token=token, pod=pod.strip(), server_url=server_url))


@mcp.custom_route("/", methods=["GET"])
async def root(request: Request) -> HTMLResponse:
    return HTMLResponse('<meta http-equiv="refresh" content="0;url=/enroll">', status_code=302)


# ---------------------------------------------------------------------------
# Wire up token middleware and expose the ASGI app for uvicorn
# ---------------------------------------------------------------------------

app = TokenMiddleware(mcp.streamable_http_app())
