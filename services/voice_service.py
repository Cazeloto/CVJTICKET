from __future__ import annotations

import os
import subprocess
import threading
from datetime import datetime, timedelta
from typing import Any


def _ps_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _spoken_ticket_number(senha: str) -> str:
    senha = (senha or "").strip().upper()
    if "-" not in senha:
        return " ".join(senha)

    prefix, number = senha.split("-", 1)
    digits = " ".join(ch for ch in number if ch.isdigit())
    return f"{prefix} {digits}".strip()


class VoiceService:
    _lock = threading.Lock()
    _last_spoken: dict[str, datetime] = {}
    _repeat_window = timedelta(seconds=30)

    def __init__(self) -> None:
        self.enabled = os.getenv("CVJ_VOICE", "1").strip() != "0"

    def _should_speak(self, ticket: dict[str, Any]) -> bool:
        ticket_key = str(ticket.get("id") or ticket.get("senha") or "").strip()
        if not ticket_key:
            return True

        now = datetime.now()
        with self._lock:
            last = self._last_spoken.get(ticket_key)
            if last and now - last < self._repeat_window:
                return False

            self._last_spoken[ticket_key] = now
            old_limit = now - self._repeat_window
            self._last_spoken = {
                key: value
                for key, value in self._last_spoken.items()
                if value >= old_limit
            }
            return True

    def speak_ticket(self, ticket: dict[str, Any]) -> None:
        if not self.enabled or os.name != "nt":
            return
        if not self._should_speak(ticket):
            return

        senha = _spoken_ticket_number(str(ticket.get("senha") or ""))
        nome = str(
            ticket.get("nome_livre")
            or ticket.get("nome")
            or ticket.get("consulente")
            or ""
        ).strip()
        if not senha:
            return

        text = f"Senha {senha}"
        if nome:
            text = f"{text}. {nome}"

        command = (
            "Add-Type -AssemblyName System.Speech; "
            "$voice = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
            "$voice.Rate = -1; "
            "$voice.Volume = 100; "
            f"$voice.Speak({_ps_quote(text)});"
        )

        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        try:
            subprocess.Popen(
                [
                    "powershell",
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-Command",
                    command,
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=creationflags,
            )
        except Exception:
            return
