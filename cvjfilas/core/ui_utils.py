from __future__ import annotations
import flet as ft


def fila_label(f: str) -> str:
    return {"N": "Normal", "P": "Preferencial", "E": "Espera"}.get(f, f)


def status_label(s: str) -> str:
    return {
        "W": "Aguardando",
        "C": "Chamado",
        "F": "Concluído",
        "X": "Cancelado",
        "D": "Finalizado",
    }.get(s, s)


def status_color(s: str):
    # Compatível com ft.Colors e ft.Colors (depende da versão)
    Colors = getattr(ft, "Colors", ft.Colors)
    return {
        "W": Colors.GREEN_100,
        "C": Colors.AMBER,
        "F": Colors.GREEN,
        "X": Colors.GREY,
        "D": Colors.BLUE,
    }.get(s, Colors.BLUE_GREY)
