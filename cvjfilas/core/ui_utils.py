"""Utilitários de UI compartilhados entre as views do CVJTICKET.

Funções puras de mapeamento de códigos internos para texto/cor exibíveis.
Nenhuma dessas funções produz efeitos colaterais.
"""
from __future__ import annotations

import flet as ft

# Mapeamento de código de fila para nome legível.
_FILA_LABELS: dict[str, str] = {
    "N": "Normal",
    "P": "Preferencial",
    "E": "Espera",
    "A": "Não apareceu",
}

# Mapeamento de código de status para nome legível.
_STATUS_LABELS: dict[str, str] = {
    "W": "Aguardando",
    "C": "Chamado",
    "F": "Concluído",
    "X": "Cancelado",
    "D": "Finalizado",
}


def fila_label(f: str) -> str:
    """Retorna o nome legível da fila (ex.: 'N' → 'Normal').

    Retorna o próprio código se não reconhecido.
    """
    return _FILA_LABELS.get(f, f)


def status_label(s: str) -> str:
    """Retorna o nome legível do status (ex.: 'W' → 'Aguardando').

    Retorna o próprio código se não reconhecido.
    """
    return _STATUS_LABELS.get(s, s)


def status_color(s: str) -> object:
    """Retorna a cor Flet associada ao status do ticket.

    Usa ft.Colors diretamente (compatível com Flet ≥ 0.21).
    """
    return {
        "W": ft.Colors.GREEN_100,
        "C": ft.Colors.AMBER,
        "F": ft.Colors.GREEN,
        "X": ft.Colors.GREY,
        "D": ft.Colors.BLUE,
    }.get(s, ft.Colors.BLUE_GREY)
