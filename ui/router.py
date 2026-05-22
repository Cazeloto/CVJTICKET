from __future__ import annotations

import logging
import flet as ft

from services.database_service import DatabaseService
from services.print_service import PrintService

from .main_view import build_main_view
from .tv_view import build_tv_view


def app(page: ft.Page):
    db = DatabaseService()
    printer = PrintService()
    log = logging.getLogger("CVJFILAS")
    log.info("APP iniciado. Route inicial=%s", page.route)

    def render_error(title: str, ex: Exception):
        import traceback

        Colors = getattr(ft, "Colors", ft.Colors)
        FontWeight = getattr(ft, "FontWeight", ft.FontWeight)

        tb = traceback.format_exc()
        log.error("%s: %s\n%s", title, ex, tb)

        page.views.clear()
        page.views.append(
            ft.View(
                route="/error",
                controls=[
                    ft.Container(
                        padding=20,
                        bgcolor=Colors.BLACK,
                        content=ft.Column(
                            controls=[
                                ft.Text(
                                    title,
                                    size=18,
                                    weight=FontWeight.W_900,
                                    color=Colors.RED,
                                ),
                                ft.Text(str(ex), color=Colors.WHITE),
                                ft.Text(tb[-2500:], size=12, color=Colors.WHITE),
                            ],
                            scroll=ft.ScrollMode.AUTO,
                        ),
                    )
                ],
            )
        )
        page.update()

    def route_change(e=None):
        try:
            raw = page.route or "/"
            r = raw.rstrip("/") or "/"

            page.views.clear()
            if r == "/tv":
                v = build_tv_view(page, db)
            else:
                v = build_main_view(page, db, printer)

            page.views.append(v)
            page.update()

            boot = (getattr(v, "data", None) or {}).get("bootstrap")
            if boot:
                page.run_task(boot)
        except Exception as ex:
            render_error("Falha ao renderizar", ex)

    def view_pop(e: ft.ViewPopEvent):
        try:
            page.views.pop()
            top = page.views[-1]
            page.route = top.route
            route_change(None)
        except Exception as ex:
            render_error("Falha no view_pop", ex)

    page.on_route_change = route_change
    page.on_view_pop = view_pop

    if not page.route:
        page.route = "/"
    route_change(None)
