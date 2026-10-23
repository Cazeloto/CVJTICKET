"""Ponto de entrada do CVJTICKET.

Inicializa o logger, configura o ambiente de execução congelada (PyInstaller)
e sobe o servidor Flet na porta configurada.

Variáveis de ambiente relevantes:
    APP_PORT  — porta HTTP (padrão: 8123, definida em cvjfilas/core/constants.py)

Quando executado como .exe (IS_FROZEN=True):
    - Força o modo web server (sem janela nativa)
    - Redireciona stdout/stderr para flet_server.log no diretório do executável
    - Abre o navegador automaticamente após 1,5 s
"""
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

LOG.info("BOOT CVJTICKET")
LOG.info("Assets dir: %s (exists=%s)", ASSETS_DIR, ASSETS_DIR.exists())
LOG.info("Port: %s", PORT)


def _open_browser() -> None:
    """Aguarda 1,5 s e abre o navegador padrão apontando para o servidor local."""
    time.sleep(1.5)
    webbrowser.open(f"http://127.0.0.1:{PORT}")


if IS_FROZEN:
    threading.Thread(target=_open_browser, daemon=True).start()

ft.run(
    app,
    host="0.0.0.0",
    port=PORT,
    assets_dir=str(ASSETS_DIR),
    view=ft.AppView.WEB_BROWSER,
)
