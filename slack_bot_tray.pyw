VERSION = "20260528"

import ctypes
import logging
import os
import subprocess
import threading
from collections import deque
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import scrolledtext

# pythonw.exe has no console. AllocConsole() creates a hidden one so child
# processes (claude.exe, Node/MCP) can inherit it instead of spawning their own.
ctypes.windll.kernel32.AllocConsole()
_hwnd = ctypes.windll.kernel32.GetConsoleWindow()
if _hwnd:
    ctypes.windll.user32.ShowWindow(_hwnd, 0)

from dotenv import load_dotenv
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler


class _NoSignalSocketModeHandler(SocketModeHandler):
    """SocketModeHandler without the SIGINT registration that fails off-main-thread."""
    def start(self):
        self.connect()
        from threading import Event
        Event().wait()
import pystray
from PIL import Image, ImageDraw

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

# ── State ─────────────────────────────────────────────────────────────────────

tray_icon: pystray.Icon | None = None
log_text_widget: scrolledtext.ScrolledText | None = None
root: tk.Tk | None = None


# ── Logging ───────────────────────────────────────────────────────────────────

class _WidgetHandler(logging.Handler):
    """Appends log records to the tkinter ScrolledText widget."""

    def emit(self, record: logging.LogRecord):
        msg = self.format(record)
        if root:
            root.after(0, lambda m=msg: _append_log_text(m))
        if tray_icon and record.levelno >= logging.INFO:
            try:
                tray_icon.title = f"CDGC Bot — {record.getMessage()[:60]}"
            except Exception:
                pass


def _append_log_text(entry: str):
    if log_text_widget:
        log_text_widget.config(state="normal")
        log_text_widget.insert(tk.END, entry + "\n")
        log_text_widget.see(tk.END)
        log_text_widget.config(state="disabled")


_widget_handler = _WidgetHandler()
_widget_handler.setFormatter(logging.Formatter("%(asctime)s  %(levelname)-8s  %(message)s", datefmt="%H:%M:%S"))

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        _widget_handler,
    ],
)
log = logging.getLogger("cdgc_bot")

# ── Slack / Claude ────────────────────────────────────────────────────────────

app = App(token=os.environ["SLACK_BOT_TOKEN"])


def run_claude(prompt: str) -> str:
    log.info("PROMPT  %s", prompt[:200])

    si = subprocess.STARTUPINFO()
    si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    si.wShowWindow = subprocess.SW_HIDE

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
        startupinfo=si,
    )

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


# ── System tray ───────────────────────────────────────────────────────────────

def _make_icon_image() -> Image.Image:
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse([2, 2, 62, 62], fill=(54, 197, 240, 255))
    d.ellipse([8, 8, 56, 56], fill=(36, 41, 47, 255))
    d.ellipse([22, 22, 42, 42], fill=(54, 197, 240, 200))
    return img


def _show_log(icon=None, item=None):
    if root:
        root.after(0, _do_show)


def _do_show():
    root.deiconify()
    root.lift()
    root.focus_force()


def _hide_log():
    root.withdraw()


def _exit_app(icon=None, item=None):
    log.info("Shutting down…")
    if tray_icon:
        tray_icon.stop()
    if root:
        root.after(0, root.destroy)


def _run_tray():
    global tray_icon
    menu = pystray.Menu(
        pystray.MenuItem("Show Log", _show_log, default=True),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Exit", _exit_app),
    )
    tray_icon = pystray.Icon(
        "CDGC Slack Bot",
        _make_icon_image(),
        "CDGC Slack Bot — starting…",
        menu,
    )
    tray_icon.run()


# ── Tkinter log window ────────────────────────────────────────────────────────

def _build_log_window():
    global root, log_text_widget

    root = tk.Tk()
    root.title("CDGC Slack Bot")
    root.geometry("720x460")
    root.protocol("WM_DELETE_WINDOW", _hide_log)

    toolbar = tk.Frame(root, bd=1, relief=tk.RAISED, bg="#2d2d2d")
    tk.Label(toolbar, text="CDGC Slack Bot", fg="#36c5f0", bg="#2d2d2d",
             font=("Segoe UI", 10, "bold")).pack(side=tk.LEFT, padx=8, pady=4)
    tk.Button(toolbar, text="Clear", command=_clear_log,
              bg="#3a3a3a", fg="#cccccc", relief=tk.FLAT,
              padx=6).pack(side=tk.RIGHT, padx=4, pady=3)
    toolbar.pack(side=tk.TOP, fill=tk.X)

    log_text_widget = tk.Text(
        root, state="disabled", wrap=tk.NONE,
        font=("Consolas", 9), bg="#1e1e1e", fg="#d4d4d4",
        insertbackground="white", relief=tk.FLAT,
    )
    v_scroll = tk.Scrollbar(root, orient=tk.VERTICAL, command=log_text_widget.yview)
    h_scroll = tk.Scrollbar(root, orient=tk.HORIZONTAL, command=log_text_widget.xview)
    log_text_widget.configure(yscrollcommand=v_scroll.set, xscrollcommand=h_scroll.set)

    h_scroll.pack(side=tk.BOTTOM, fill=tk.X)
    v_scroll.pack(side=tk.RIGHT, fill=tk.Y)
    log_text_widget.pack(fill=tk.BOTH, expand=True)

    root.withdraw()  # hidden until tray click


def _clear_log():
    if log_text_widget:
        log_text_widget.config(state="normal")
        log_text_widget.delete("1.0", tk.END)
        log_text_widget.config(state="disabled")


# ── Entry point ───────────────────────────────────────────────────────────────

def _start_slack():
    log.info("Connecting to Slack…")
    handler = _NoSignalSocketModeHandler(app, os.environ["SLACK_APP_TOKEN"])
    log.info("Connected to Slack, listening…")
    handler.start()


if __name__ == "__main__":
    _build_log_window()

    threading.Thread(target=_run_tray, daemon=True).start()
    threading.Thread(target=_start_slack, daemon=True).start()

    root.mainloop()
