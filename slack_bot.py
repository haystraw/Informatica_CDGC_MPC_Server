VERSION = "20260528"

import logging
import os
import subprocess
import threading
from pathlib import Path

from dotenv import load_dotenv
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

load_dotenv(Path(__file__).parent / "slack.env")

CLAUDE_EXE = r"C:\Users\scott.hayes\.local\bin\claude.exe"
MCP_CONFIG = r"c:/Toolbox/Python/Projects/CDGC MCP Server/.mcp.json"
LOG_FILE = Path(__file__).parent / "slack_bot.log"
SYSTEM_PROMPT = (
    "You are a data governance assistant with access to the Informatica Cloud Data "
    "Governance & Catalog (CDGC). Help users search assets, explore business terms, "
    "check classifications, review data quality, and answer questions about the catalog. "
    "Be concise. Format responses for Slack (use *bold*, _italic_, and bullet lists). "
    "Avoid markdown code blocks unless showing a search query."
)

# ── Logging setup ─────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger("cdgc_bot")

# ── Slack app ─────────────────────────────────────────────────────────────────

app = App(token=os.environ["SLACK_BOT_TOKEN"])


def run_claude(prompt: str) -> str:
    log.info("PROMPT  %s", prompt[:200])

    proc = subprocess.Popen(
        [
            CLAUDE_EXE,
            "-p", prompt,
            "--mcp-config", MCP_CONFIG,
            "--append-system-prompt", SYSTEM_PROMPT,
            "--dangerously-skip-permissions",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
    )

    # Stream stderr (MCP activity, tool calls, progress) to the log in real time
    def stream_stderr():
        for line in proc.stderr:
            line = line.rstrip()
            if line:
                log.debug("claude| %s", line)

    stderr_thread = threading.Thread(target=stream_stderr, daemon=True)
    stderr_thread.start()

    try:
        stdout, _ = proc.communicate(timeout=300)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.communicate()
        log.error("Claude timed out after 300 s")
        return "Error: Claude timed out. Try a simpler question."

    stderr_thread.join(timeout=2)

    output = stdout.strip()
    if proc.returncode != 0 and not output:
        log.error("Claude exited %d with no stdout", proc.returncode)
        return "Error: Claude exited with no output."

    log.info("REPLY   %s", output[:200])
    return output or "No response."


def handle_message(body, client):
    event = body.get("event", {})
    text = event.get("text", "")
    channel = event.get("channel")
    thread_ts = event.get("thread_ts") or event.get("ts")

    bot_id = client.auth_test()["user_id"]
    text = text.replace(f"<@{bot_id}>", "").strip()

    if not text:
        return

    log.info("MESSAGE channel=%s text=%s", channel, text[:100])

    placeholder = client.chat_postMessage(
        channel=channel,
        thread_ts=thread_ts,
        text="_Thinking..._",
    )

    def respond():
        response = run_claude(text)
        client.chat_update(channel=channel, ts=placeholder["ts"], text=response)

    threading.Thread(target=respond, daemon=True).start()


@app.event("app_mention")
def on_mention(body, client):
    handle_message(body, client)


@app.event("message")
def on_dm(body, client):
    event = body.get("event", {})
    if event.get("channel_type") == "im" and not event.get("bot_id"):
        handle_message(body, client)


if __name__ == "__main__":
    log.info("Starting CDGC Slack bot — log: %s", LOG_FILE)
    handler = SocketModeHandler(app, os.environ["SLACK_APP_TOKEN"])
    log.info("Connected to Slack, listening…")
    handler.start()
