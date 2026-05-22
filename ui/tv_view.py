from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime
import flet as ft

from services.database_service import DatabaseService

LOG = logging.getLogger("CVJFILAS")
TV_DESTAQUE_SEGUNDOS = 15


def build_tv_view(page: ft.Page, db: DatabaseService) -> ft.View:
    Colors = getattr(ft, "Colors", ft.Colors)
    FontWeight = getattr(ft, "FontWeight", ft.FontWeight)

    page.title = "CVJFILAS - TV"
    page.theme_mode = ft.ThemeMode.DARK

    title_txt = ft.Text(
        "CHAMANDO AGORA",
        size=48,
        weight=FontWeight.W_900,
        color=getattr(Colors, "WHITE70", Colors.WHITE),
        text_align=ft.TextAlign.CENTER,
    )

    info_txt = ft.Text(
        "",
        size=18,
        color=getattr(Colors, "WHITE70", Colors.WHITE),
        text_align=ft.TextAlign.CENTER,
    )

    atual_fila_txt = ft.Text(
        "",
        size=42,
        weight=FontWeight.W_800,
        color=Colors.WHITE,
        text_align=ft.TextAlign.CENTER,
    )

    atual_senha_txt = ft.Text(
        "—",
        size=260,
        weight=FontWeight.W_900,
        color=Colors.WHITE,
        text_align=ft.TextAlign.CENTER,
    )

    atual_nome_txt = ft.Text(
        "",
        size=60,
        weight=FontWeight.W_700,
        color=Colors.WHITE,
        text_align=ft.TextAlign.CENTER,
        max_lines=2,
    )

    def last_text(size: int, color):
        return ft.Text(
            "—",
            size=size,
            weight=FontWeight.W_900 if size >= 50 else FontWeight.W_700,
            color=color,
            text_align=ft.TextAlign.CENTER,
        )

    ult_n_1 = last_text(56, Colors.WHITE)
    ult_n_2 = last_text(40, getattr(Colors, "WHITE70", Colors.WHITE))
    ult_n_3 = last_text(30, getattr(Colors, "WHITE54", Colors.WHITE))

    ult_p_1 = last_text(56, Colors.WHITE)
    ult_p_2 = last_text(40, getattr(Colors, "WHITE70", Colors.WHITE))
    ult_p_3 = last_text(30, getattr(Colors, "WHITE54", Colors.WHITE))

    def resumo_card(titulo: str, ctrls: list[ft.Text]) -> ft.Control:
        return ft.Container(
            expand=True,
            padding=20,
            border_radius=22,
            bgcolor=getattr(Colors, "BLACK54", Colors.BLACK),
            border=ft.border.all(1, getattr(Colors, "WHITE10", Colors.WHITE)),
            content=ft.Column(
                alignment=ft.MainAxisAlignment.CENTER,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=8,
                controls=[
                    ft.Text(
                        titulo,
                        size=26,
                        weight=FontWeight.W_700,
                        color=Colors.WHITE,
                        text_align=ft.TextAlign.CENTER,
                    ),
                    *ctrls,
                ],
            ),
        )

    atual_panel = ft.Container(
        expand=7,
        padding=28,
        border_radius=28,
        bgcolor=getattr(Colors, "BLUE_700", Colors.BLUE),
        content=ft.Column(
            alignment=ft.MainAxisAlignment.CENTER,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=18,
            controls=[
                title_txt,
                atual_fila_txt,
                atual_senha_txt,
                atual_nome_txt,
                info_txt,
            ],
        ),
    )

    resumo_panel = ft.Container(
        expand=3,
        padding=12,
        content=ft.Column(
            spacing=14,
            controls=[
                resumo_card("ÚLTIMOS NORMAIS", [ult_n_1, ult_n_2, ult_n_3]),
                resumo_card("ÚLTIMOS PREFERENCIAIS", [ult_p_1, ult_p_2, ult_p_3]),
            ],
        ),
    )

    root = ft.Container(
        expand=True,
        padding=18,
        bgcolor=getattr(Colors, "BLACK", Colors.BLUE_GREY_900),
        content=ft.Row(
            expand=True,
            spacing=18,
            controls=[atual_panel, resumo_panel],
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
        return fila

    def nome_fila(fila: str) -> str:
        return {"N": "NORMAL", "P": "PREFERENCIAL", "E": "ESPERA"}.get(fila, fila)

    def cor_fila(fila: str):
        if fila == "P":
            return getattr(Colors, "AMBER_700", Colors.ORANGE)
        if fila == "N":
            return getattr(Colors, "BLUE_700", Colors.BLUE)
        return getattr(Colors, "GREY_700", Colors.GREY)

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

    def top3_por_fila(chamados: list[dict], fila: str) -> list[dict]:
        filtrados = [t for t in chamados if t["_fila_norm"] == fila]
        filtrados.sort(key=lambda x: x["_called_at_dt"], reverse=True)
        return filtrados[:3]

    def set_top3(c1: ft.Text, c2: ft.Text, c3: ft.Text, itens: list[dict]):
        vals = [str(i.get("senha", "—")) for i in itens]
        while len(vals) < 3:
            vals.append("—")
        c1.value, c2.value, c3.value = vals[0], vals[1], vals[2]

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

                ultimos_n = top3_por_fila(chamados, "N")
                ultimos_p = top3_por_fila(chamados, "P")
                set_top3(ult_n_1, ult_n_2, ult_n_3, ultimos_n)
                set_top3(ult_p_1, ult_p_2, ult_p_3, ultimos_p)

                agora = datetime.now()
                atual = chamados[-1] if chamados else None
                mostrar_atual = None

                if atual:
                    delta = (agora - atual["_called_at_dt"]).total_seconds()
                    if 0 <= delta <= TV_DESTAQUE_SEGUNDOS:
                        mostrar_atual = atual

                if mostrar_atual:
                    fila = mostrar_atual["_fila_norm"]
                    senha = str(mostrar_atual.get("senha", "—"))
                    nome = str(
                        mostrar_atual.get("nome_livre")
                        or mostrar_atual.get("nome")
                        or mostrar_atual.get("consulente")
                        or ""
                    ).strip()

                    atual_panel.bgcolor = cor_fila(fila)
                    atual_fila_txt.value = nome_fila(fila)
                    atual_senha_txt.value = senha
                    atual_nome_txt.value = nome

                    if mostrar_atual.get("id") != ultimo_ticket_id:
                        ultimo_ticket_id = mostrar_atual.get("id")
                        await blink()
                else:
                    atual_panel.bgcolor = getattr(Colors, "BLUE_700", Colors.BLUE)
                    atual_fila_txt.value = "AGUARDANDO"
                    atual_senha_txt.value = "—"
                    atual_nome_txt.value = ""

                info_txt.value = f"Data: {today.strftime('%d/%m/%Y')}"
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
