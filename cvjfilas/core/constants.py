from __future__ import annotations
from pathlib import Path
import os

BASE_DIR = Path(__file__).resolve().parents[2]  # project root
ASSETS_DIR = BASE_DIR / "assets"

APP_HOST = os.getenv("APP_HOST", "0.0.0.0")
APP_PORT = int(os.getenv("APP_PORT", "8123"))
IS_SERVER = os.getenv("CVJ_SERVER", "0").strip() == "1"

LOGO_SRC = "logopb.jpg"

HIDE_STATUSES = {"F", "X"}
