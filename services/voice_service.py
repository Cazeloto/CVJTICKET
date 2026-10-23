"""Serviço de síntese de voz para o painel de TV do CVJTICKET.

Usa o Windows Speech Synthesis (System.Speech) via PowerShell para
anunciar tickets chamados em voz alta. Silenciosamente desativado em
sistemas não-Windows ou quando CVJ_VOICE=0.
"""
from __future__ import annotations

import os
import subprocess
import threading
from datetime import datetime, timedelta
from typing import Any


def _ps_quote(value: str) -> str:
    """Escapa uma string para uso seguro dentro de aspas simples no PowerShell."""
    return "'" + value.replace("'", "''") + "'"


def _spoken_ticket_number(senha: str) -> str:
    """Converte o código da senha em texto falado.

    Exemplos:
        'N-007' → 'N 0 0 7'
        'P023'  → 'P 0 2 3'
    """
    senha = (senha or "").strip().upper()
    if "-" not in senha:
        return " ".join(senha)
    prefix, number = senha.split("-", 1)
    digits = " ".join(ch for ch in number if ch.isdigit())
    return f"{prefix} {digits}".strip()


class VoiceService:
    """Anuncia tickets chamados em voz alta via Windows Speech Synthesis.

    Thread-safe: usa um lock para controlar a janela de repetição e evitar
    que o mesmo ticket seja anunciado múltiplas vezes em menos de 30 s.
    """

    _lock = threading.Lock()
    _last_spoken: dict[str, datetime] = {}
    _repeat_window = timedelta(seconds=30)

    def __init__(self) -> None:
        """Inicializa o serviço. Lê CVJ_VOICE do ambiente (padrão: ativado)."""
        self.enabled = os.getenv("CVJ_VOICE", "1").strip() != "0"

    def _should_speak(self, ticket: dict[str, Any]) -> bool:
        """Retorna True se o ticket deve ser anunciado agora.

        Impede repetição do mesmo ticket dentro da janela de 30 segundos.
        """
        ticket_key = str(ticket.get("id") or ticket.get("senha") or "").strip()
        if not ticket_key:
            return True

        now = datetime.now()
        with self._lock:
            last = self._last_spoken.get(ticket_key)
            if last and now - last < self._repeat_window:
                return False
            self._last_spoken[ticket_key] = now
            # Limpa entradas antigas para evitar crescimento ilimitado
            cutoff = now - self._repeat_window
            self._last_spoken = {k: v for k, v in self._last_spoken.items() if v >= cutoff}
            return True

    def speak_ticket(self, ticket: dict[str, Any]) -> None:
        """Anuncia a senha e o nome do consulente em voz alta.

        Não bloqueia — dispara um processo PowerShell em background.
        Silenciosamente ignorado em sistemas não-Windows ou com voz desativada.
        """
        if not self.enabled or os.name != "nt":
            return
        if not self._should_speak(ticket):
            return

        senha = _spoken_ticket_number(str(ticket.get("senha") or ""))
        if not senha:
            return

        nome = str(
            ticket.get("nome_livre") or ticket.get("nome") or ticket.get("consulente") or ""
        ).strip()

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

        try:
            subprocess.Popen(
                ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except Exception:
            pass
