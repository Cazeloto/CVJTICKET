from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime
import flet as ft

from services.database_service import DatabaseService
from services.voice_service import VoiceService

LOG = logging.getLogger("CVJFILAS")
TV_DESTAQUE_SEGUNDOS = 15


def build_tv_view(page: ft.Page, db: DatabaseService) -> ft.View:
    Colors = getattr(ft, "Colors", ft.Colors)
    Icons = getattr(ft, "Icons", ft.icons)
    FontWeight = getattr(ft, "FontWeight", ft.FontWeight)
    voice = VoiceService()

    page.title = "CVJFILAS - TV"
    page.theme_mode = ft.ThemeMode.DARK

    header_status_txt = ft.Text(
        "CHAMANDO AGORA",
        size=30,
        weight=FontWeight.W_900,
        color=getattr(Colors, "WHITE70", Colors.WHITE),
        text_align=ft.TextAlign.CENTER,
    )

    atual_fila_txt = ft.Text(
        "AGUARDANDO",
        size=44,
        weight=FontWeight.W_900,
        color=Colors.WHITE,
        text_align=ft.TextAlign.CENTER,
    )

    atual_senha_txt = ft.Text(
        "-",
        size=260,
        weight=FontWeight.W_900,
        color=Colors.WHITE,
        text_align=ft.TextAlign.CENTER,
    )

    atual_nome_txt = ft.Text(
        "",
        size=58,
        weight=FontWeight.W_800,
        color=Colors.WHITE,
        text_align=ft.TextAlign.CENTER,
        max_lines=2,
        overflow=ft.TextOverflow.ELLIPSIS,
    )

    data_txt = ft.Text(
        "",
        size=20,
        weight=FontWeight.W_700,
        color=getattr(Colors, "WHITE70", Colors.WHITE),
    )
    hora_txt = ft.Text(
        "",
        size=34,
        weight=FontWeight.W_900,
        color=Colors.WHITE,
    )
    rodape_status_txt = ft.Text(
        "Aguardando chamada",
        size=18,
        weight=FontWeight.W_700,
        color=getattr(Colors, "WHITE70", Colors.WHITE),
    )

    history_list = ft.Column(spacing=10, expand=True, scroll=ft.ScrollMode.AUTO)

    def history_empty_card() -> ft.Control:
        return ft.Container(
            padding=16,
            border_radius=8,
            bgcolor=getattr(Colors, "WHITE10", Colors.BLACK),
            content=ft.Text(
                "Nenhuma chamada registrada",
                size=18,
                weight=FontWeight.W_700,
                color=getattr(Colors, "WHITE70", Colors.WHITE),
                text_align=ft.TextAlign.CENTER,
            ),
        )

    def history_card(ticket: dict, index: int) -> ft.Control:
        fila = ticket.get("_fila_norm", "")
        senha = str(ticket.get("senha", "-"))
        nome = str(
            ticket.get("nome_livre")
            or ticket.get("nome")
            or ticket.get("consulente")
            or ""
        ).strip()
        called_at = ticket.get("_called_at_dt")
        horario = called_at.strftime("%H:%M") if called_at else ""

        return ft.Container(
            padding=14,
            border_radius=8,
            bgcolor=Colors.WHITE if index == 0 else getattr(Colors, "WHITE10", Colors.BLACK),
            border=ft.border.all(
                1,
                getattr(Colors, "WHITE24", Colors.WHITE)
                if index > 0
                else Colors.TRANSPARENT,
            ),
            content=ft.Column(
                spacing=8,
                controls=[
                    ft.Row(
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        controls=[
                            ft.Text(
                                senha,
                                size=34 if index == 0 else 26,
                                weight=FontWeight.W_900,
                                color=Colors.BLACK if index == 0 else Colors.WHITE,
                            ),
                            ft.Container(
                                padding=ft.padding.symmetric(horizontal=8, vertical=4),
                                border_radius=8,
                                bgcolor=cor_fila(fila),
                                content=ft.Text(
                                    nome_fila(fila),
                                    size=12,
                                    weight=FontWeight.W_900,
                                    color=Colors.WHITE,
                                ),
                            ),
                        ],
                    ),
                    ft.Text(
                        nome,
                        size=16 if index == 0 else 14,
                        weight=FontWeight.W_800,
                        color=Colors.BLACK if index == 0 else getattr(Colors, "WHITE70", Colors.WHITE),
                        max_lines=1,
                        overflow=ft.TextOverflow.ELLIPSIS,
                    ),
                    ft.Text(
                        horario,
                        size=13,
                        weight=FontWeight.W_700,
                        color=Colors.BLACK54 if index == 0 else getattr(Colors, "WHITE54", Colors.WHITE),
                    ),
                ],
            ),
        )

    atual_panel = ft.Container(
        expand=7,
        padding=36,
        border_radius=8,
        bgcolor=getattr(Colors, "BLUE_700", Colors.BLUE),
        content=ft.Column(
            alignment=ft.MainAxisAlignment.CENTER,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=20,
            controls=[
                header_status_txt,
                atual_fila_txt,
                atual_senha_txt,
                atual_nome_txt,
            ],
        ),
    )

    historico_panel = ft.Container(
        expand=3,
        padding=22,
        border_radius=8,
        bgcolor=getattr(Colors, "BLUE_GREY_900", Colors.BLACK),
        border=ft.border.all(1, getattr(Colors, "WHITE10", Colors.WHITE)),
        content=ft.Column(
            spacing=18,
            controls=[
                ft.Row(
                    spacing=10,
                    controls=[
                        ft.Icon(Icons.HISTORY, color=Colors.WHITE, size=26),
                        ft.Text(
                            "Últimas chamadas",
                            size=26,
                            weight=FontWeight.W_900,
                            color=Colors.WHITE,
                        ),
                    ],
                ),
                ft.Divider(height=1, color=getattr(Colors, "WHITE24", Colors.WHITE)),
                history_list,
            ],
        ),
    )

    footer = ft.Container(
        padding=ft.padding.symmetric(horizontal=24, vertical=12),
        border_radius=8,
        bgcolor=getattr(Colors, "BLUE_GREY_900", Colors.BLACK),
        border=ft.border.all(1, getattr(Colors, "WHITE10", Colors.WHITE)),
        content=ft.Row(
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                ft.Text(
                    "Casa da Vovó Joaquina",
                    size=22,
                    weight=FontWeight.W_900,
                    color=Colors.WHITE,
                ),
                rodape_status_txt,
                ft.Row(spacing=18, controls=[data_txt, hora_txt]),
            ],
        ),
    )

    root = ft.Container(
        expand=True,
        padding=18,
        bgcolor=getattr(Colors, "BLACK", Colors.BLUE_GREY_900),
        content=ft.Column(
            expand=True,
            spacing=18,
            controls=[
                ft.Row(
                    expand=True,
                    spacing=18,
                    controls=[atual_panel, historico_panel],
                ),
                footer,
            ],
        ),
    )

    def get_fila(ticket: dict) -> str:
        fila = str(ticket.get("fila") or ticket.get("tipo") or "").upper().strip()
        if fila in ("N", "NORMAL"):
            return "N"
        if fila in ("P", "PREFERENCIAL", "PRIORITARIO", "PRIORITÁRIO"):
            return "P"
        if fila in ("E", "ESPERA"):
            return "E"
        if fila in ("A", "NAO APARECEU", "NÃO APARECEU"):
            return "A"
        return fila

    def nome_fila(fila: str) -> str:
        return {
            "N": "NORMAL",
            "P": "PREFERENCIAL",
            "E": "ESPERA",
            "A": "NÃO APARECEU",
        }.get(fila, fila)

    def cor_fila(fila: str):
        if fila == "P":
            return getattr(Colors, "AMBER_700", Colors.ORANGE)
        if fila == "N":
            return getattr(Colors, "BLUE_700", Colors.BLUE)
        if fila == "E":
            return getattr(Colors, "PURPLE_700", Colors.PURPLE)
        if fila == "A":
            return getattr(Colors, "RED_700", Colors.RED)
        return getattr(Colors, "BLUE_GREY_700", Colors.GREY)

    def parse_dt(value):
        if not value:
            return None
        if isinstance(value, datetime):
            dt = value
        else:
            s = str(value).strip()
            dt = None
            try:
                dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
            except Exception:
                pass
            if dt is None:
                for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S"):
                    try:
                        dt = datetime.strptime(s, fmt)
                        break
                    except Exception:
                        continue
        if dt is None:
            return None
        if getattr(dt, "tzinfo", None) is not None:
            dt = dt.astimezone().replace(tzinfo=None)
        return dt

    def set_history(chamados: list[dict]):
        recentes = sorted(chamados, key=lambda x: x["_called_at_dt"], reverse=True)[:6]
        history_list.controls = (
            [history_card(t, idx) for idx, t in enumerate(recentes)]
            if recentes
            else [history_empty_card()]
        )

    async def blink():
        for _ in range(2):
            atual_senha_txt.visible = False
            page.update()
            await asyncio.sleep(0.25)

            atual_senha_txt.visible = True
            page.update()
            await asyncio.sleep(0.25)

    ultimo_ticket_id = None

    async def refresh_loop():
        nonlocal ultimo_ticket_id

        while True:
            try:
                today = date.today()
                now = datetime.now()
                items = db.list_tickets(today)

                chamados = []
                for t in items:
                    called_at = parse_dt(t.get("called_at"))
                    if called_at:
                        tt = dict(t)
                        tt["_called_at_dt"] = called_at
                        tt["_fila_norm"] = get_fila(tt)
                        chamados.append(tt)

                chamados.sort(key=lambda x: x["_called_at_dt"])
                set_history(chamados)

                atual = chamados[-1] if chamados else None
                mostrar_atual = None

                if atual:
                    delta = (now - atual["_called_at_dt"]).total_seconds()
                    if 0 <= delta <= TV_DESTAQUE_SEGUNDOS:
                        mostrar_atual = atual

                if mostrar_atual:
                    fila = mostrar_atual["_fila_norm"]
                    senha = str(mostrar_atual.get("senha", "-"))
                    nome = str(
                        mostrar_atual.get("nome_livre")
                        or mostrar_atual.get("nome")
                        or mostrar_atual.get("consulente")
                        or ""
                    ).strip()

                    header_status_txt.value = "CHAMANDO AGORA"
                    atual_panel.bgcolor = cor_fila(fila)
                    atual_fila_txt.value = nome_fila(fila)
                    atual_senha_txt.value = senha
                    atual_nome_txt.value = nome
                    rodape_status_txt.value = "Senha em chamada"

                    if mostrar_atual.get("id") != ultimo_ticket_id:
                        ultimo_ticket_id = mostrar_atual.get("id")
                        voice.speak_ticket(mostrar_atual)
                        await blink()
                else:
                    header_status_txt.value = "PAINEL DE CHAMADA"
                    atual_panel.bgcolor = getattr(Colors, "BLUE_GREY_800", Colors.BLUE)
                    atual_fila_txt.value = "AGUARDANDO"
                    atual_senha_txt.value = "-"
                    atual_nome_txt.value = ""
                    rodape_status_txt.value = "Aguardando chamada"

                data_txt.value = today.strftime("%d/%m/%Y")
                hora_txt.value = now.strftime("%H:%M")
                page.update()

            except Exception:
                LOG.exception("Erro no refresh_loop da TV")

            await asyncio.sleep(2)

    async def bootstrap():
        await asyncio.sleep(0.2)
        page.run_task(refresh_loop)

    v = ft.View(
        route="/tv",
        padding=0,
        controls=[root],
        bgcolor=getattr(Colors, "BLACK", Colors.BLUE_GREY_900),
    )
    v.data = {"bootstrap": bootstrap}
    return v
