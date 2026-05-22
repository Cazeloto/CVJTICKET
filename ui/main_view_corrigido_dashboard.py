from __future__ import annotations

import asyncio
import os
from datetime import date
import flet as ft

from services.database_service import DatabaseService
from services.print_service import PrintService

from ..core.constants import IS_SERVER, LOGO_SRC, HIDE_STATUSES
from ..core.ui_utils import fila_label, status_label, status_color


def build_main_view(
    page: ft.Page, db: DatabaseService, printer: PrintService
) -> ft.View:
    Colors = getattr(ft, "Colors", ft.Colors)
    Icons = getattr(ft, "Icons", ft.icons)
    FontWeight = getattr(ft, "FontWeight", ft.FontWeight)

    page.title = "Sistema de Filas - CVJ"
    page.theme_mode = ft.ThemeMode.LIGHT

    def fila_label_ui(c: str) -> str:
        return {
            "N": "Normal",
            "P": "Preferencial",
            "E": "Espera",
            "A": "Não apareceu",
        }.get((c or "").upper(), fila_label(c))

    device = os.getenv("COMPUTERNAME", "TERMINAL")
    state = {"work_date": date.today()}

    def is_mobile() -> bool:
        w = page.width
        return True if w is None else w < 900

    def show_snack(msg: str, ok: bool = True):
        page.snack_bar = ft.SnackBar(
            ft.Text(msg), bgcolor=(Colors.GREEN if ok else Colors.RED)
        )
        page.snack_bar.open = True
        page.update()

    def open_file(path: str):
        try:
            os.startfile(path)
        except Exception as ex:
            show_snack(f"Não consegui abrir o arquivo: {ex}", ok=False)

    # -------- Entrada única de nome --------
    nome_input = ft.TextField(
        label="Nome do consulente",
        hint_text="Digite o nome e clique na fila",
        expand=True,
        autofocus=True,
    )

    # -------- Relatórios --------
    def relatorio_lista_chamada_backup(e=None):
        try:
            tickets = db.list_tickets(state["work_date"])
            pdf_path = printer.gerar_lista_chamada_por_fila_pdf(
                work_date=state["work_date"], tickets=tickets
            )
            open_file(pdf_path)
            show_snack("Lista de chamada (Backup) gerada.")
        except Exception as ex:
            show_snack(f"Erro no relatório (backup): {ex}", ok=False)

    def relatorio_fechamento_gira(e=None):
        try:
            tickets = db.list_tickets(state["work_date"])
            pdf_path = printer.gerar_fechamento_gira_pdf(
                work_date=state["work_date"], tickets=tickets
            )
            open_file(pdf_path)
            show_snack("Fechamento da gira gerado.")
        except Exception as ex:
            show_snack(f"Erro no fechamento: {ex}", ok=False)

    relatorios_menu = ft.PopupMenuButton(
        icon=Icons.DESCRIPTION,
        tooltip="Relatórios",
        items=[
            ft.PopupMenuItem(
                content=ft.Text("Lista de chamada (Backup)"),
                on_click=relatorio_lista_chamada_backup,
            ),
            ft.PopupMenuItem(
                content=ft.Text("Fechamento da gira"),
                on_click=relatorio_fechamento_gira,
            ),
        ],
    )

    # -------- Zerar dia --------
    confirm_dialog = ft.AlertDialog(modal=True)

    def close_dialog(e=None):
        confirm_dialog.open = False
        page.update()

    def do_reset_day(e=None):
        try:
            affected = db.reset_workday(
                state["work_date"], hard_delete=True, origin_device=device
            )
            close_dialog()
            refresh()
            show_snack(f"Dia zerado. Registros removidos: {affected}")
        except Exception as ex:
            close_dialog()
            show_snack(f"Erro ao zerar o dia: {ex}", ok=False)

    def ask_reset_day(e=None):
        d = state["work_date"].strftime("%d/%m/%Y")
        confirm_dialog.title = ft.Text("Confirmar zerar o dia")
        confirm_dialog.content = ft.Text(
            f"Você tem certeza que deseja zerar TODAS as senhas do dia {d}?\n\n"
            "Isso apaga os registros do dia e reinicia a numeração."
        )
        confirm_dialog.actions = [
            ft.TextButton("Cancelar", on_click=close_dialog),
            ft.ElevatedButton("Zerar agora", on_click=do_reset_day),
        ]
        confirm_dialog.actions_alignment = ft.MainAxisAlignment.END
        page.dialog = confirm_dialog
        confirm_dialog.open = True
        page.update()

    zerar_btn = ft.OutlinedButton(
        "Zerar dia", icon=Icons.DELETE_SWEEP, on_click=ask_reset_day
    )

    # -------- TV --------
    def abrir_tv(e=None):
        try:
            page.launch_url("#/tv")
        except Exception:
            try:
                page.launch_url("/#/tv")
            except Exception:
                pass

    tv_btn = ft.OutlinedButton(
        "Abrir TV", icon=Icons.LIVE_TV, on_click=abrir_tv, visible=IS_SERVER
    )

    # -------- Dashboard (servidor) --------
    dash_total_aberto = ft.Text("0", size=20, weight=FontWeight.W_900)
    dash_n_aberto = ft.Text("0", size=18, weight=FontWeight.W_800)
    dash_p_aberto = ft.Text("0", size=18, weight=FontWeight.W_800)
    dash_e_aberto = ft.Text("0", size=18, weight=FontWeight.W_800)
    dash_a_aberto = ft.Text("0", size=18, weight=FontWeight.W_800)

    def dash_card(title: str, value_text: ft.Text, icon) -> ft.Control:
        """
        Card compacto do dashboard.

        Importante:
        - usa o próprio value_text recebido, para o refresh continuar atualizando os valores;
        - reduz fonte/padding para caberem 5 cards em uma única linha;
        - o título é encurtado no dashboard para evitar quebra.
        """
        value_text.size = 16
        value_text.weight = FontWeight.W_900

        return ft.Container(
            padding=8,
            border_radius=14,
            bgcolor=Colors.SURFACE,
            border=ft.border.all(1, Colors.OUTLINE_VARIANT),
            content=ft.Row(
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Row(
                        spacing=5,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        controls=[
                            ft.Icon(icon, size=16),
                            ft.Text(
                                title,
                                weight=FontWeight.W_700,
                                size=12,
                                no_wrap=True,
                            ),
                        ],
                    ),
                    value_text,
                ],
            ),
        )

    dashboard = ft.Row(
        spacing=6,
        visible=IS_SERVER,
        controls=[
            ft.Container(
                expand=1,
                content=dash_card(
                    "Em triagem",
                    dash_total_aberto,
                    Icons.MONITOR_HEART,
                ),
            ),
            ft.Container(
                expand=1,
                content=dash_card(
                    "Normal",
                    dash_n_aberto,
                    Icons.PEOPLE_ALT,
                ),
            ),
            ft.Container(
                expand=1,
                content=dash_card(
                    "Preferencial",
                    dash_p_aberto,
                    Icons.STAR,
                ),
            ),
            ft.Container(
                expand=1,
                content=dash_card(
                    "Espera",
                    dash_e_aberto,
                    Icons.HOURGLASS_BOTTOM,
                ),
            ),
            ft.Container(
                expand=1,
                content=dash_card(
                    "Não apareceu",
                    dash_a_aberto,
                    Icons.PERSON_OFF,
                ),
            ),
        ],
    )

    # -------- Contadores + Listas --------
    count_n = ft.Text("0", size=14, weight=FontWeight.W_900)
    count_p = ft.Text("0", size=14, weight=FontWeight.W_900)
    count_e = ft.Text("0", size=14, weight=FontWeight.W_900)
    count_a = ft.Text("0", size=14, weight=FontWeight.W_900)

    normal_list = ft.ListView(spacing=8, expand=True)
    pref_list = ft.ListView(spacing=8, expand=True)
    esp_list = ft.ListView(spacing=8, expand=True)
    aus_list = ft.ListView(spacing=8, expand=True)

    imprimir_ao_gerar = ft.Switch(
        label="Imprimir ao gerar", value=True, visible=IS_SERVER
    )

    def criar_na_fila(fila_code: str):
        n = (nome_input.value or "").strip()
        if not n:
            show_snack("Digite o nome do consulente.", ok=False)
            return
        try:
            t = db.create_ticket(
                work_date=state["work_date"],
                nome=n,
                fila=fila_code,
                categoria="N",
                origin_device=device,
            )
            nome_input.value = ""
            if IS_SERVER and imprimir_ao_gerar.value:
                pdf_path = printer.gerar_senha_a6_pdf(
                    ticket=t, work_date=state["work_date"], incluir_qr=True
                )
                open_file(pdf_path)
            refresh()
            show_snack(f"Senha gerada: {t.get('senha')} ({fila_label_ui(fila_code)})")
        except Exception as ex:
            show_snack(f"Erro ao gerar: {ex}", ok=False)

    def ticket_card(t: dict) -> ft.Control:
        st = t.get("status", "W")
        border = (
            ft.border.all(2, Colors.AMBER)
            if st == "C"
            else ft.border.all(1, Colors.OUTLINE_VARIANT)
        )

        badge = ft.Container(
            padding=ft.padding.symmetric(horizontal=8, vertical=2),
            bgcolor=status_color(st),
            border_radius=999,
            content=ft.Text(status_label(st), size=11, weight=FontWeight.W_700),
        )

        def on_call(e):
            if st in ("X", "D", "F"):
                return
            db.call_ticket(int(t["id"]), origin_device=device)
            refresh()

        def on_confirm(e):
            if st in ("X", "D", "F"):
                return
            db.confirm_ticket(int(t["id"]), origin_device=device)
            refresh()

        def on_cancel(e):
            if st == "X":
                return
            db.cancel_ticket(int(t["id"]), origin_device=device)
            refresh()

        def on_nao_apareceu(e=None):
            if st in ("X", "D", "F"):
                return
            if (t.get("fila") or "").upper() == "A":
                return
            db.move_ticket(int(t["id"]), "A", origin_device=device)
            refresh()

        actions = ft.Row(
            spacing=6,
            controls=[
                ft.IconButton(
                    Icons.CAMPAIGN,
                    tooltip="Chamar",
                    on_click=on_call,
                    disabled=st in ("X", "D", "F"),
                ),
                ft.IconButton(
                    Icons.CHECK_CIRCLE,
                    tooltip="Concluir",
                    on_click=on_confirm,
                    disabled=st in ("X", "D", "F"),
                ),
                ft.IconButton(
                    Icons.PERSON_OFF,
                    tooltip="Não apareceu",
                    on_click=on_nao_apareceu,
                    disabled=st in ("X", "D", "F")
                    or (t.get("fila") or "").upper() == "A",
                ),
                ft.IconButton(
                    Icons.DELETE_OUTLINE,
                    tooltip="Cancelar",
                    on_click=on_cancel,
                    disabled=st == "X",
                ),
            ],
        )

        return ft.Container(
            padding=12,
            border_radius=16,
            border=border,
            bgcolor=Colors.SURFACE,
            content=ft.Column(
                spacing=8,
                controls=[
                    ft.Row(
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        controls=[
                            ft.Text(
                                str(t.get("senha", "—")),
                                size=22,
                                weight=FontWeight.W_800,
                            ),
                            actions,
                        ],
                    ),
                    ft.Text(
                        (t.get("nome_livre") or "— sem nome —").strip(),
                        size=16,
                        weight=FontWeight.W_700,
                    ),
                    ft.Row(spacing=6, controls=[badge]),
                ],
            ),
        )

    def header_count_chip(counter: ft.Text) -> ft.Control:
        return ft.Container(
            padding=ft.padding.symmetric(horizontal=10, vertical=6),
            border_radius=999,
            bgcolor=Colors.WHITE,
            content=ft.Row(
                spacing=6,
                controls=[
                    ft.Icon(Icons.CONFIRMATION_NUMBER, size=16, color=Colors.BLACK),
                    counter,
                ],
            ),
        )

    def fila_header_style(fila_code: str):
        if fila_code == "P":
            return (Colors.AMBER_200, Colors.AMBER_900, Colors.BLACK)
        if fila_code == "N":
            return (Colors.BLUE_200, Colors.BLUE_900, Colors.BLACK)
        if fila_code == "A":
            return (Colors.RED_200, Colors.RED_900, Colors.BLACK)
        return (Colors.PURPLE_200, Colors.PURPLE_900, Colors.BLACK)

    def desktop_col(
        title: str,
        icon,
        lv: ft.ListView,
        fila_code: str,
        counter: ft.Text,
        allow_create: bool = True,
    ) -> ft.Control:
        bg, icc, tx = fila_header_style(fila_code)

        header = ft.Container(
            padding=ft.padding.symmetric(vertical=10, horizontal=12),
            border_radius=14,
            bgcolor=bg,
            ink=allow_create,
            on_click=(lambda e: criar_na_fila(fila_code)) if allow_create else None,
            content=ft.Row(
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                controls=[
                    ft.Row(
                        spacing=8,
                        controls=[
                            ft.Icon(icon, color=icc),
                            ft.Text(title, size=16, weight=FontWeight.W_900, color=tx),
                            header_count_chip(counter),
                        ],
                    ),
                    ft.Text(
                        (
                            "Clique para adicionar"
                            if allow_create
                            else "Somente via botão"
                        ),
                        size=12,
                    ),
                ],
            ),
        )
        return ft.Container(
            padding=12,
            border_radius=18,
            bgcolor=Colors.SURFACE,
            border=ft.border.all(1, Colors.OUTLINE_VARIANT),
            content=ft.Column(spacing=10, controls=[header, ft.Divider(height=1), lv]),
        )

    desktop_board = ft.ResponsiveRow(
        columns=12,
        spacing=12,
        run_spacing=12,
        controls=[
            ft.Container(
                col={"xs": 12, "md": 3},
                content=desktop_col(
                    "Normal", Icons.PEOPLE_ALT, normal_list, "N", count_n
                ),
            ),
            ft.Container(
                col={"xs": 12, "md": 3},
                content=desktop_col(
                    "Preferencial", Icons.STAR, pref_list, "P", count_p
                ),
            ),
            ft.Container(
                col={"xs": 12, "md": 3},
                content=desktop_col(
                    "Espera", Icons.HOURGLASS_BOTTOM, esp_list, "E", count_e
                ),
            ),
            ft.Container(
                col={"xs": 12, "md": 3},
                content=desktop_col(
                    "Não apareceu", Icons.PERSON_OFF, aus_list, "A", count_a, False
                ),
            ),
        ],
    )

    # -------- Topbar + Layout --------
    topbar = ft.Container(
        padding=12,
        border_radius=18,
        bgcolor=Colors.SURFACE,
        border=ft.border.all(1, Colors.OUTLINE_VARIANT),
        content=ft.Row(
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            controls=[
                ft.Row(
                    spacing=12,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[
                        ft.Image(
                            src=LOGO_SRC,
                            width=44 if is_mobile() else 56,
                            height=44 if is_mobile() else 56,
                            fit="contain",
                        ),
                        ft.Text(
                            "Casa da Vovó Joaquina",
                            size=16 if is_mobile() else 20,
                            weight=FontWeight.W_800,
                        ),
                        ft.Container(
                            padding=ft.padding.symmetric(horizontal=10, vertical=4),
                            border_radius=999,
                            bgcolor=Colors.ON_SURFACE_VARIANT,
                            content=ft.Text(
                                "SERVIDOR" if IS_SERVER else "CLIENTE",
                                size=11,
                                weight=FontWeight.W_700,
                            ),
                        ),
                    ],
                ),
                ft.Row(spacing=10, controls=[relatorios_menu, zerar_btn, tv_btn]),
            ],
        ),
    )

    content_host = ft.Container(expand=True)

    def apply_layout():
        # no web você está usando desktop; mantive só o board desktop (sem tabs),
        # mas se quiser mobile depois a gente reintroduz.
        content_host.content = ft.Column(
            expand=True,
            spacing=12,
            controls=[
                topbar,
                dashboard,
                ft.Container(
                    padding=12,
                    border_radius=18,
                    bgcolor=Colors.SURFACE,
                    border=ft.border.all(1, Colors.OUTLINE_VARIANT),
                    content=ft.Row(controls=[nome_input, imprimir_ao_gerar]),
                ),
                desktop_board,
            ],
        )

    # -------- Refresh --------
    def refresh():
        try:
            all_items = db.list_tickets(state["work_date"])
        except Exception as ex:
            show_snack(f"Erro lendo do banco: {ex}", ok=False)
            return

        abertos = [t for t in all_items if t.get("status") in ("W", "C")]
        n_open = sum(1 for t in abertos if t.get("fila") == "N")
        p_open = sum(1 for t in abertos if t.get("fila") == "P")
        e_open = sum(1 for t in abertos if t.get("fila") == "E")
        a_open = sum(1 for t in abertos if t.get("fila") == "A")
        total_open = len(abertos)

        count_n.value = str(n_open)
        count_p.value = str(p_open)
        count_e.value = str(e_open)
        count_a.value = str(a_open)

        if IS_SERVER:
            dash_total_aberto.value = str(total_open)
            dash_n_aberto.value = str(n_open)
            dash_p_aberto.value = str(p_open)
            dash_e_aberto.value = str(e_open)
            dash_a_aberto.value = str(a_open)

        items = [t for t in all_items if (t.get("status") not in HIDE_STATUSES)]
        by = {"N": [], "P": [], "E": [], "A": []}
        for t in items:
            by.get(t.get("fila", "N"), by["N"]).append(t)

        def prio_status(s: str) -> int:
            return {"C": 0, "W": 1, "F": 2, "D": 3, "X": 4}.get(s, 9)

        for f in ("N", "P", "E", "A"):
            by[f].sort(
                key=lambda x: (prio_status(x.get("status", "W")), int(x.get("seq", 0)))
            )

        normal_list.controls = [ticket_card(t) for t in by["N"]]
        pref_list.controls = [ticket_card(t) for t in by["P"]]
        esp_list.controls = [ticket_card(t) for t in by["E"]]
        aus_list.controls = [ticket_card(t) for t in by["A"]]

        page.update()

    async def auto_refresh():
        while True:
            if (page.route or "/").rstrip("/") == "/tv":
                await asyncio.sleep(0.8)
                continue
            try:
                refresh()
            except Exception:
                pass
            await asyncio.sleep(1.5)

    def on_resize(e):
        apply_layout()
        page.update()

    page.on_resize = on_resize

    apply_layout()
    refresh()
    page.run_task(auto_refresh)

    return ft.View(
        route="/",
        controls=[content_host],
        padding=0,
        bgcolor=Colors.WHITE,
        scroll=ft.ScrollMode.AUTO,
    )
