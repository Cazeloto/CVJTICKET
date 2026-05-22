from __future__ import annotations

import os
import sys
import threading
import time
import webbrowser
from pathlib import Path

IS_FROZEN = bool(getattr(sys, "frozen", False))

if IS_FROZEN:
    os.environ["FLET_FORCE_WEB_SERVER"] = "1"
    exe_dir = Path(sys.executable).resolve().parent
    server_log = open(exe_dir / "flet_server.log", "a", encoding="utf-8")
    if sys.stdout is None:
        sys.stdout = server_log
    if sys.stderr is None:
        sys.stderr = server_log
    if sys.stdin is None:
        sys.stdin = open(os.devnull, "r", encoding="utf-8")

import flet as ft

from cvjfilas.core.constants import ASSETS_DIR, APP_PORT
from cvjfilas.core.logging_setup import setup_logging
from cvjfilas.ui.router import app

BASE_DIR = Path(__file__).resolve().parent
LOG = setup_logging(BASE_DIR)

PORT = int(os.getenv("APP_PORT", str(APP_PORT)))

LOG.info("BOOT CVJFILAS (modular)")
LOG.info("Assets dir: %s (exists=%s)", str(ASSETS_DIR), ASSETS_DIR.exists())
LOG.info("Host: 0.0.0.0")
LOG.info("Port: %s", PORT)

def open_browser_once():
    time.sleep(1.5)
    webbrowser.open(f"http://127.0.0.1:{PORT}")


if IS_FROZEN:
    threading.Thread(target=open_browser_once, daemon=True).start()

ft.run(
    app,
    host="0.0.0.0",
    port=PORT,
    assets_dir=str(ASSETS_DIR),
    view=ft.AppView.WEB_BROWSER,
)
