"""Roteador principal do CVJTICKET.

Mapeia rotas Flet para as views correspondentes e trata erros de renderização
exibindo uma tela de diagnóstico em vez de travar silenciosamente.

Rotas suportadas:
    /           → main_view  (desktop/operador)
    /tv         → tv_view    (painel de chamada)
    /celular    → mobile_call_view
    /celular/chamada → mobile_call_view (alias para compatibilidade)
    /celular/cadastro → mobile_registration_view
"""
from __future__ import annotations

import logging
import flet as ft

from services.database_service import DatabaseService
from services.print_service import PrintService

from .main_view import build_main_view
from .mobile_view import build_mobile_call, build_mobile_registration
from .tv_view import build_tv_view


def app(page: ft.Page) -> None:
    """Ponto de entrada da aplicação Flet.

    Configura os handlers de rota e renderiza a view inicial.
    """
    db = DatabaseService()
    printer = PrintService()
    log = logging.getLogger("CVJFILAS")
    log.info("APP iniciado. Route inicial=%s", page.route)

    def render_error(title: str, ex: Exception) -> None:
        """Exibe uma tela de erro com traceback quando uma view falha ao renderizar."""
        import traceback

        tb = traceback.format_exc()
        log.error("%s: %s\n%s", title, ex, tb)

        page.views.clear()
        page.views.append(
            ft.View(
                route="/error",
                controls=[
                    ft.Container(
                        padding=20,
                        bgcolor=ft.Colors.BLACK,
                        content=ft.Column(
                            controls=[
                                ft.Text(title, size=18, weight=ft.FontWeight.W_900, color=ft.Colors.RED),
                                ft.Text(str(ex), color=ft.Colors.WHITE),
                                ft.Text(tb[-2500:], size=12, color=ft.Colors.WHITE),
                            ],
                            scroll=ft.ScrollMode.AUTO,
                        ),
                    )
                ],
            )
        )
        page.update()

    def route_change(e=None) -> None:
        """Constrói e exibe a view correspondente à rota atual."""
        try:
            # Normaliza: remove query string, trailing slash e converte para minúsculo
            raw = page.route or "/"
            route_key = raw.split("?", 1)[0].rstrip("/").lower() or "/"

            page.views.clear()

            if route_key == "/tv":
                v = build_tv_view(page, db)
            elif route_key == "/celular/cadastro":
                v = build_mobile_registration(page, db, printer)
            elif route_key in ("/celular", "/celular/chamada"):
                v = build_mobile_call(page, db, printer)
            else:
                v = build_main_view(page, db, printer)

            page.views.append(v)
            page.update()

            # Executa a corrotina de bootstrap da view, se existir
            boot = (getattr(v, "data", None) or {}).get("bootstrap")
            if boot:
                page.run_task(boot)
        except Exception as ex:
            render_error("Falha ao renderizar", ex)

    def view_pop(e: ft.ViewPopEvent) -> None:
        """Volta para a view anterior na pilha de navegação."""
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
