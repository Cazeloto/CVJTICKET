from __future__ import annotations

import asyncio
import os
from datetime import date, datetime, timedelta
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
    APP_BG = "#C8A4CB"
    HEADER_BG = "#B98ABD"

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

    def safe_page_update() -> bool:
        try:
            page.update()
            return True
        except Exception:
            return False

    def show_snack(msg: str, ok: bool = True):
        page.snack_bar = ft.SnackBar(
            ft.Text(msg), bgcolor=(Colors.GREEN if ok else Colors.RED)
        )
        page.snack_bar.open = True
        safe_page_update()

    def format_work_date() -> str:
        return state["work_date"].strftime("%d/%m/%Y")

    def open_file(path: str):
        try:
            os.startfile(path)
        except Exception as ex:
            show_snack(f"Não consegui abrir o arquivo: {ex}", ok=False)

    # -------- Entrada única de nome --------
    nome_input = ft.TextField(
        label="Nome do consulente",
        hint_text="Digite qualquer parte do nome",
        expand=True,
        autofocus=True,
    )

    sugestoes_nomes = ft.Container(
        visible=False,
        bgcolor=Colors.WHITE,
        border=ft.border.all(1, Colors.OUTLINE_VARIANT),
        border_radius=8,
        padding=4,
        content=ft.Column(tight=True, spacing=0, controls=[]),
    )

    nome_box = ft.Container(
        expand=True,
        content=ft.Column(
            tight=True,
            spacing=4,
            controls=[nome_input, sugestoes_nomes],
        ),
    )

    def esconder_sugestoes():
        sugestoes_nomes.visible = False
        sugestoes_nomes.content.controls = []

    def selecionar_sugestao(nome: str):
        nome_input.value = (nome or "").strip()
        esconder_sugestoes()
        safe_page_update()

    def atualizar_sugestoes(e=None):
        termo = (nome_input.value or "").strip()
        if len(termo) < 2:
            esconder_sugestoes()
            safe_page_update()
            return

        try:
            sugestoes = db.search_consulentes(termo, limit=6)
        except Exception:
            sugestoes = []

        if not sugestoes:
            esconder_sugestoes()
            safe_page_update()
            return

        sugestoes_nomes.content.controls = [
            ft.Container(
                padding=ft.padding.symmetric(horizontal=10, vertical=7),
                border_radius=6,
                ink=True,
                on_click=lambda e, nome=item["nome"]: selecionar_sugestao(nome),
                content=ft.Row(
                    spacing=8,
                    controls=[
                        ft.Icon(Icons.PERSON_SEARCH, size=16, color=Colors.BLUE_700),
                        ft.Text(str(item["nome"]), size=13, weight=FontWeight.W_600),
                    ],
                ),
            )
            for item in sugestoes
        ]
        sugestoes_nomes.visible = True
        safe_page_update()

    nome_input.on_change = atualizar_sugestoes

    acompanhantes_dd = ft.Dropdown(
        label="Acomp.",
        width=112,
        value="0",
        options=[
            ft.dropdown.Option("0"),
            ft.dropdown.Option("1"),
            ft.dropdown.Option("2"),
        ],
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

    def fechamento_card(title: str, value: int, bg, fg, icon) -> ft.Control:
        return ft.Container(
            expand=True,
            padding=14,
            border_radius=8,
            bgcolor=bg,
            content=ft.Column(
                spacing=8,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Icon(icon, color=fg, size=24),
                    ft.Text(str(value), size=28, weight=FontWeight.W_900, color=fg),
                    ft.Text(
                        title,
                        size=12,
                        weight=FontWeight.W_800,
                        color=fg,
                        text_align=ft.TextAlign.CENTER,
                    ),
                ],
            ),
        )

    def relatorio_fechamento_gira(e=None):
        try:
            tickets = db.list_tickets(state["work_date"])
            concluidos = [t for t in tickets if t.get("status") in ("F", "D")]
            counts = {"N": 0, "P": 0, "E": 0, "A": 0}
            for t in concluidos:
                fila = (t.get("fila") or "N").upper()
                if fila not in counts:
                    fila = "N"
                counts[fila] += 1

            total_consulentes = counts["N"] + counts["P"] + counts["E"]
            total_acompanhantes = 0
            for t in concluidos:
                if (t.get("fila") or "").upper() == "A":
                    continue
                try:
                    total_acompanhantes += int(t.get("acompanhantes") or 0)
                except Exception:
                    pass
            total_pessoas = total_consulentes + total_acompanhantes

            def gerar_pdf_fechamento(ev=None):
                try:
                    pdf_path = printer.gerar_fechamento_gira_pdf(
                        work_date=state["work_date"], tickets=tickets
                    )
                    page.pop_dialog()
                    open_file(pdf_path)
                    show_snack("Fechamento da gira gerado.")
                except Exception as ex:
                    show_snack(f"Erro ao gerar PDF: {ex}", ok=False)

            dialog = ft.AlertDialog(
                modal=True,
                title=ft.Text("Fechamento da Gira", weight=FontWeight.W_900),
                content=ft.Container(
                    width=760,
                    padding=4,
                    content=ft.Column(
                        tight=True,
                        spacing=16,
                        controls=[
                            ft.Text(
                                f"Dia {format_work_date()} - Concluídos",
                                size=14,
                                weight=FontWeight.W_700,
                                color=Colors.GREY_700,
                            ),
                            ft.Container(
                                padding=18,
                                border_radius=8,
                                bgcolor=Colors.GREY_100,
                                content=ft.Column(
                                    spacing=16,
                                    controls=[
                                        ft.Text(
                                            "Resumo de Atendimentos",
                                            size=18,
                                            weight=FontWeight.W_900,
                                        ),
                                        ft.Row(
                                            spacing=12,
                                            controls=[
                                                fechamento_card(
                                                    "Normal",
                                                    counts["N"],
                                                    Colors.BLUE_100,
                                                    Colors.BLUE_900,
                                                    Icons.PEOPLE_ALT,
                                                ),
                                                fechamento_card(
                                                    "Preferencial",
                                                    counts["P"],
                                                    Colors.AMBER_100,
                                                    Colors.AMBER_900,
                                                    Icons.STAR,
                                                ),
                                                fechamento_card(
                                                    "Espera",
                                                    counts["E"],
                                                    Colors.PURPLE_100,
                                                    Colors.PURPLE_900,
                                                    Icons.HOURGLASS_BOTTOM,
                                                ),
                                                fechamento_card(
                                                    "Não apareceu",
                                                    counts["A"],
                                                    Colors.RED_100,
                                                    Colors.RED_900,
                                                    Icons.PERSON_OFF,
                                                ),
                                            ],
                                        ),
                                        ft.Divider(height=1),
                                        ft.Row(
                                            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                                            controls=[
                                                ft.Text(
                                                    f"TOTAL: {total_pessoas}",
                                                    size=22,
                                                    weight=FontWeight.W_900,
                                                ),
                                                ft.Text(
                                                    f"Consulentes: {total_consulentes}",
                                                    size=15,
                                                    weight=FontWeight.W_700,
                                                ),
                                                ft.Text(
                                                    f"Acompanhantes: {total_acompanhantes}",
                                                    size=15,
                                                    weight=FontWeight.W_700,
                                                ),
                                            ],
                                        ),
                                    ],
                                ),
                            ),
                        ],
                    ),
                ),
                actions=[
                    ft.OutlinedButton(
                        "Gerar PDF",
                        icon=Icons.PICTURE_AS_PDF,
                        on_click=gerar_pdf_fechamento,
                    ),
                    ft.TextButton("Fechar", on_click=lambda e: page.pop_dialog()),
                ],
                actions_alignment=ft.MainAxisAlignment.END,
            )
            page.show_dialog(dialog)
        except Exception as ex:
            show_snack(f"Erro no fechamento: {ex}", ok=False)

    def top_action_button(
        label: str, icon, on_click, icon_color=None, tooltip: str | None = None
    ) -> ft.Control:
        return ft.Container(
            height=38,
            tooltip=tooltip or label,
            padding=ft.padding.symmetric(horizontal=10, vertical=0),
            bgcolor=Colors.WHITE,
            border_radius=8,
            border=ft.border.all(1, Colors.OUTLINE_VARIANT),
            ink=True,
            on_click=on_click,
            content=ft.Row(
                spacing=8,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Icon(icon, size=18, color=icon_color or Colors.BLUE_900),
                    ft.Text(
                        label,
                        size=12,
                        weight=FontWeight.W_700,
                        color=Colors.BLUE_900,
                    ),
                ],
            ),
        )

    relatorios_menu = ft.Row(
        spacing=8,
        controls=[
            top_action_button(
                "Lista",
                Icons.DESCRIPTION,
                relatorio_lista_chamada_backup,
                tooltip="Gerar lista de chamada",
            ),
            top_action_button(
                "Fech.",
                Icons.SUMMARIZE,
                relatorio_fechamento_gira,
                tooltip="Gerar fechamento da gira",
            ),
        ],
    )

    # -------- Zerar dia --------
    confirm_dialog = ft.AlertDialog(modal=True)

    def close_dialog(e=None):
        try:
            page.pop_dialog()
        except Exception:
            confirm_dialog.open = False
        safe_page_update()

    def do_reset_day(e=None):
        try:
            db.reset_workday(
                state["work_date"], hard_delete=True, origin_device=device
            )
            close_dialog()
            refresh()
            show_snack("Dia Zerado")
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
        page.show_dialog(confirm_dialog)

    zerar_btn = top_action_button(
        "Zerar",
        Icons.DELETE_SWEEP,
        ask_reset_day,
        Colors.RED_700,
        tooltip="Zerar senhas do dia",
    )

    # -------- TV --------
    def abrir_tv(e=None):
        try:
            page.go("/tv")
        except Exception as ex:
            show_snack(f"Não consegui abrir a TV: {ex}", ok=False)

    tv_btn = top_action_button(
        "TV",
        Icons.LIVE_TV,
        abrir_tv,
        tooltip="Abrir painel da TV",
    )
    tv_btn.visible = IS_SERVER

    # -------- Data de trabalho --------
    work_date_txt = ft.Text(
        format_work_date(),
        size=14,
        weight=FontWeight.W_800,
    )

    def refresh_work_date_label():
        work_date_txt.value = format_work_date()

    def set_work_date(new_date: date):
        state["work_date"] = new_date
        refresh_work_date_label()
        refresh()

    def on_date_picked(e=None):
        value = date_picker.value
        if isinstance(value, datetime):
            value = value.date()
        if isinstance(value, date):
            set_work_date(value)

    date_picker = ft.DatePicker(
        value=state["work_date"],
        first_date=date(2020, 1, 1),
        last_date=date(2100, 12, 31),
        help_text="Escolha a data",
        cancel_text="Cancelar",
        confirm_text="OK",
        field_label_text="Data",
        on_change=on_date_picked,
    )

    def open_date_picker(e=None):
        date_picker.value = state["work_date"]
        page.show_dialog(date_picker)

    def previous_day(e=None):
        set_work_date(state["work_date"] - timedelta(days=1))

    def next_day(e=None):
        set_work_date(state["work_date"] + timedelta(days=1))

    def today(e=None):
        set_work_date(date.today())

    date_selector = ft.Container(
        height=38,
        tooltip="Data de trabalho",
        padding=ft.padding.symmetric(horizontal=8, vertical=2),
        border_radius=8,
        bgcolor=Colors.WHITE,
        border=ft.border.all(1, Colors.OUTLINE_VARIANT),
        content=ft.Row(
            spacing=4,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                ft.IconButton(
                    Icons.CHEVRON_LEFT,
                    tooltip="Dia anterior",
                    on_click=previous_day,
                ),
                ft.TextButton(
                    content=ft.Row(
                        spacing=6,
                        controls=[
                            ft.Icon(Icons.CALENDAR_MONTH, size=16),
                            work_date_txt,
                        ],
                    ),
                    tooltip="Escolher data",
                    on_click=open_date_picker,
                ),
                ft.IconButton(
                    Icons.CHEVRON_RIGHT,
                    tooltip="Próximo dia",
                    on_click=next_day,
                ),
                ft.IconButton(Icons.TODAY, tooltip="Hoje", on_click=today),
            ],
        ),
    )
    # -------- Dashboard (servidor) --------
    dash_total_aberto = ft.Text("0", size=20, weight=FontWeight.W_900)
    dash_n_aberto = ft.Text("0", size=18, weight=FontWeight.W_800)
    dash_p_aberto = ft.Text("0", size=18, weight=FontWeight.W_800)
    dash_e_aberto = ft.Text("0", size=18, weight=FontWeight.W_800)
    dash_a_aberto = ft.Text("0", size=18, weight=FontWeight.W_800)

    def dash_card(title: str, value_text: ft.Text, icon) -> ft.Control:
        return ft.Container(
            padding=12,
            border_radius=8,
            bgcolor=Colors.WHITE,
            border=ft.border.all(1, Colors.OUTLINE_VARIANT),
            content=ft.Row(
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                controls=[
                    ft.Row(
                        spacing=8,
                        controls=[
                            ft.Icon(icon),
                            ft.Text(title, weight=FontWeight.W_700),
                        ],
                    ),
                    value_text,
                ],
            ),
        )

    dashboard = ft.Row(
        spacing=12,
        visible=IS_SERVER,
        controls=[
            ft.Container(
                expand=True,
                content=dash_card(
                    "Em triagem (Total)", dash_total_aberto, Icons.MONITOR_HEART
                ),
            ),
            ft.Container(
                expand=True,
                content=dash_card("Normal (abertos)", dash_n_aberto, Icons.PEOPLE_ALT),
            ),
            ft.Container(
                expand=True,
                content=dash_card("Preferencial (abertos)", dash_p_aberto, Icons.STAR),
            ),
            ft.Container(
                expand=True,
                content=dash_card(
                    "Espera (abertos)", dash_e_aberto, Icons.HOURGLASS_BOTTOM
                ),
            ),
            ft.Container(
                expand=True,
                content=dash_card(
                    "Não apareceu (abertos)", dash_a_aberto, Icons.PERSON_OFF
                ),
            ),
        ],
    )

    triagem_summary = ft.Container(
        height=38,
        tooltip="Total em triagem",
        padding=ft.padding.symmetric(horizontal=10, vertical=2),
        border_radius=8,
        bgcolor=Colors.WHITE,
        border=ft.border.all(1, Colors.OUTLINE_VARIANT),
        visible=IS_SERVER,
        content=ft.Row(
            spacing=8,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                ft.Icon(Icons.MONITOR_HEART, size=18, color=Colors.BLUE_GREY_900),
                ft.Text(
                    "Em triagem",
                    size=12,
                    weight=FontWeight.W_700,
                    color=Colors.BLUE_GREY_900,
                ),
                dash_total_aberto,
            ],
        ),
    )

    # -------- Contadores + Listas --------
    count_n = ft.Text("0", size=14, weight=FontWeight.W_900)
    count_p = ft.Text("0", size=14, weight=FontWeight.W_900)
    count_e = ft.Text("0", size=14, weight=FontWeight.W_900)
    count_a = ft.Text("0", size=14, weight=FontWeight.W_900)
    done_n = ft.Text("0", size=14, weight=FontWeight.W_900)
    done_p = ft.Text("0", size=14, weight=FontWeight.W_900)
    done_e = ft.Text("0", size=14, weight=FontWeight.W_900)
    done_a = ft.Text("0", size=14, weight=FontWeight.W_900)

    normal_list = ft.ListView(spacing=8, expand=True)
    pref_list = ft.ListView(spacing=8, expand=True)
    esp_list = ft.ListView(spacing=8, expand=True)
    aus_list = ft.ListView(spacing=8, expand=True)

    imprimir_ao_gerar = ft.Switch(
        label="Imp.", tooltip="Imprimir ao gerar", value=True, visible=IS_SERVER
    )

    def criar_na_fila(fila_code: str):
        n = (nome_input.value or "").strip().upper()
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
                acompanhantes=int(acompanhantes_dd.value or "0"),
            )
            nome_input.value = ""
            esconder_sugestoes()
            acompanhantes_dd.value = "0"
            if IS_SERVER and imprimir_ao_gerar.value:
                pdf_path = printer.gerar_senha_a6_pdf(
                    ticket=t, work_date=state["work_date"], incluir_qr=True
                )
                open_file(pdf_path)
            refresh()
            show_snack(f"Senha gerada: {t.get('senha')} ({fila_label_ui(fila_code)})")
        except Exception as ex:
            show_snack(f"Erro ao gerar: {ex}", ok=False)

    def criar_btn(
        label: str, icon, fila_code: str, bgcolor, color, tooltip: str
    ) -> ft.Control:
        return ft.ElevatedButton(
            label,
            icon=icon,
            bgcolor=bgcolor,
            color=color,
            tooltip=tooltip,
            height=40,
            width=88,
            on_click=lambda e: criar_na_fila(fila_code),
        )

    create_panel = ft.Container(
        padding=ft.padding.symmetric(horizontal=14, vertical=8),
        border_radius=8,
        bgcolor=Colors.WHITE,
        border=ft.border.all(1, Colors.OUTLINE_VARIANT),
        content=ft.Row(
            spacing=8,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                ft.Icon(Icons.ADD_CIRCLE_OUTLINE, color=Colors.BLUE_900),
                ft.Text("Nova senha", size=14, weight=FontWeight.W_800, width=92),
                nome_box,
                acompanhantes_dd,
                imprimir_ao_gerar,
                criar_btn(
                    "N",
                    Icons.PEOPLE_ALT,
                    "N",
                    Colors.BLUE_100,
                    Colors.BLUE_900,
                    "Gerar senha normal",
                ),
                criar_btn(
                    "P",
                    Icons.STAR,
                    "P",
                    Colors.AMBER_100,
                    Colors.AMBER_900,
                    "Gerar senha preferencial",
                ),
                criar_btn(
                    "E",
                    Icons.HOURGLASS_BOTTOM,
                    "E",
                    Colors.PURPLE_100,
                    Colors.PURPLE_900,
                    "Gerar senha de espera",
                ),
            ],
        ),
    )

    def ticket_card(t: dict) -> ft.Control:
        st = t.get("status", "W")
        status_dot_color = {
            "W": Colors.AMBER,
            "C": Colors.GREEN,
            "F": Colors.BLUE,
            "D": Colors.BLUE,
            "X": Colors.RED,
        }.get(st, Colors.GREY)
        border = ft.border.all(2 if st == "C" else 1.5, status_dot_color)
        status_dot = ft.Container(
            width=14,
            height=14,
            tooltip=status_label(st),
            border_radius=7,
            bgcolor=status_dot_color,
            border=ft.border.all(1, Colors.WHITE),
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
            if (t.get("fila") or "").upper() == "A":
                db.delete_ticket(int(t["id"]), origin_device=device)
            else:
                db.cancel_ticket(int(t["id"]), origin_device=device)
            refresh()

        def on_nao_apareceu(e=None):
            if st in ("X", "D", "F"):
                return
            if (t.get("fila") or "").upper() == "A":
                return
            db.move_ticket(int(t["id"]), "A", origin_device=device)
            refresh()

        acomp = (
            int(t.get("acompanhantes") or 0)
            if str(t.get("acompanhantes") or "0").isdigit()
            else 0
        )
        nome_exibicao = (t.get("nome_livre") or "- sem nome -").strip()
        if acomp > 0:
            nome_exibicao = f"{nome_exibicao} +{acomp}"

        is_nao_apareceu = (t.get("fila") or "").upper() == "A"

        def card_action_button(icon, tooltip: str, on_click, disabled: bool = False):
            return ft.IconButton(
                icon,
                tooltip=tooltip,
                on_click=on_click,
                disabled=disabled,
                icon_size=19,
                width=34,
                height=32,
            )

        action_controls = [
            card_action_button(
                Icons.CAMPAIGN,
                "Chamar",
                on_call,
                st in ("X", "D", "F"),
            ),
            card_action_button(
                Icons.CHECK_CIRCLE,
                "Concluir",
                on_confirm,
                st in ("X", "D", "F"),
            ),
        ]
        if not is_nao_apareceu:
            action_controls.append(
                ft.IconButton(
                    Icons.PERSON_OFF,
                    tooltip="Não apareceu",
                    on_click=on_nao_apareceu,
                    disabled=st in ("X", "D", "F"),
                )
            )
        action_controls.append(
            ft.IconButton(
                Icons.DELETE_OUTLINE,
                tooltip="Apagar registro" if is_nao_apareceu else "Cancelar",
                on_click=on_cancel,
                disabled=st == "X",
            )
        )

        for action_btn in action_controls:
            action_btn.icon_size = 19
            action_btn.width = 34
            action_btn.height = 32

        actions = ft.Row(
            spacing=2,
            alignment=ft.MainAxisAlignment.END,
            controls=action_controls,
        )

        return ft.Container(
            padding=10,
            border_radius=8,
            border=border,
            bgcolor=Colors.WHITE,
            content=ft.Column(
                spacing=6,
                controls=[
                    ft.Row(
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        controls=[
                            ft.Row(
                                spacing=8,
                                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                                controls=[
                                    ft.Container(
                                        width=70,
                                        padding=ft.padding.symmetric(
                                            horizontal=6, vertical=8
                                        ),
                                        border_radius=8,
                                        bgcolor=Colors.BLUE_GREY_50,
                                        content=ft.Text(
                                            str(t.get("senha", "-")),
                                            size=16,
                                            weight=FontWeight.W_900,
                                            text_align=ft.TextAlign.CENTER,
                                        ),
                                    ),
                                    status_dot,
                                ],
                            ),
                            actions,
                        ],
                    ),
                    ft.Text(
                        nome_exibicao,
                        size=16,
                        weight=FontWeight.W_900,
                        max_lines=1,
                        overflow=ft.TextOverflow.ELLIPSIS,
                    ),
                ],
            ),
        )

    def header_count_chip(counter: ft.Text) -> ft.Control:
        return ft.Container(
            padding=ft.padding.symmetric(horizontal=8, vertical=4),
            border_radius=8,
            bgcolor=Colors.WHITE,
            content=ft.Row(
                spacing=6,
                controls=[
                    ft.Icon(Icons.CONFIRMATION_NUMBER, size=16, color=Colors.BLACK),
                    counter,
                ],
            ),
        )

    def header_done_chip(counter: ft.Text) -> ft.Control:
        return ft.Container(
            padding=ft.padding.symmetric(horizontal=8, vertical=4),
            border_radius=8,
            bgcolor=Colors.WHITE,
            content=ft.Row(
                spacing=6,
                controls=[
                    ft.Icon(Icons.CHECK_CIRCLE, size=16, color=Colors.GREEN_700),
                    counter,
                ],
            ),
        )

    def fila_header_style(fila_code: str):
        if fila_code == "P":
            return (Colors.AMBER_100, Colors.AMBER_900, Colors.BLACK)
        if fila_code == "N":
            return (Colors.BLUE_100, Colors.BLUE_900, Colors.BLACK)
        if fila_code == "A":
            return (Colors.RED_100, Colors.RED_900, Colors.BLACK)
        return (Colors.PURPLE_100, Colors.PURPLE_900, Colors.BLACK)

    def desktop_col(
        title: str,
        icon,
        lv: ft.ListView,
        fila_code: str,
        counter: ft.Text,
        done_counter: ft.Text,
        allow_create: bool = True,
    ) -> ft.Control:
        bg, icc, tx = fila_header_style(fila_code)

        header = ft.Container(
            padding=ft.padding.symmetric(vertical=10, horizontal=10),
            border_radius=8,
            bgcolor=bg,
            ink=allow_create,
            on_click=(lambda e: criar_na_fila(fila_code)) if allow_create else None,
            content=ft.Row(
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=8,
                controls=[
                    ft.Row(
                        spacing=8,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        controls=[
                            ft.Icon(icon, color=icc),
                            ft.Text(
                                title,
                                size=15,
                                weight=FontWeight.W_900,
                                color=tx,
                            ),
                        ],
                    ),
                    ft.Row(
                        spacing=6,
                        controls=[
                            header_count_chip(counter),
                            header_done_chip(done_counter),
                        ],
                    ),
                ],
            ),
        )
        return ft.Container(
            padding=10,
            border_radius=8,
            bgcolor=Colors.GREY_50,
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
                    "Normal", Icons.PEOPLE_ALT, normal_list, "N", count_n, done_n
                ),
            ),
            ft.Container(
                col={"xs": 12, "md": 3},
                content=desktop_col(
                    "Preferencial", Icons.STAR, pref_list, "P", count_p, done_p
                ),
            ),
            ft.Container(
                col={"xs": 12, "md": 3},
                content=desktop_col(
                    "Espera", Icons.HOURGLASS_BOTTOM, esp_list, "E", count_e, done_e
                ),
            ),
            ft.Container(
                col={"xs": 12, "md": 3},
                content=desktop_col(
                    "Não apareceu",
                    Icons.PERSON_OFF,
                    aus_list,
                    "A",
                    count_a,
                    done_a,
                    False,
                ),
            ),
        ],
    )

    # -------- Topbar + Layout --------
    topbar = ft.Container(
        padding=ft.padding.symmetric(horizontal=14, vertical=8),
        border_radius=8,
        bgcolor=HEADER_BG,
        border=ft.border.all(1, Colors.OUTLINE_VARIANT),
        content=ft.Row(
            spacing=10,
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                ft.Row(
                    spacing=10,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[
                        ft.Row(
                            spacing=12,
                            vertical_alignment=ft.CrossAxisAlignment.CENTER,
                            controls=[
                                ft.Image(
                                    src=LOGO_SRC,
                                    width=34,
                                    height=34,
                                    fit="contain",
                                ),
                                ft.Text(
                                    "Casa da Vovó Joaquina",
                                    size=18,
                                    weight=FontWeight.W_900,
                                    color=Colors.WHITE,
                                ),
                            ],
                        ),
                        ft.Container(
                            height=28,
                            tooltip="Modo servidor" if IS_SERVER else "Terminal cliente",
                            padding=ft.padding.symmetric(horizontal=9, vertical=2),
                            border_radius=8,
                            bgcolor=Colors.BLUE_50 if IS_SERVER else Colors.GREY_100,
                            border=ft.border.all(
                                1, Colors.BLUE_200 if IS_SERVER else Colors.GREY_300
                            ),
                            content=ft.Row(
                                spacing=6,
                                controls=[
                                    ft.Icon(
                                        Icons.COMPUTER,
                                        size=13,
                                        color=Colors.BLUE_900
                                        if IS_SERVER
                                        else Colors.GREY_700,
                                    ),
                                    ft.Text(
                                        "Servidor" if IS_SERVER else "Cliente",
                                        size=11,
                                        weight=FontWeight.W_700,
                                        color=Colors.BLUE_900
                                        if IS_SERVER
                                        else Colors.GREY_700,
                                    ),
                                ],
                            ),
                        ),
                    ],
                ),
                ft.Row(
                    spacing=10,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[
                        date_selector,
                        triagem_summary,
                        relatorios_menu,
                        tv_btn,
                        zerar_btn,
                    ],
                ),
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
                create_panel,
                desktop_board,
            ],
        )

    # -------- Refresh --------
    def refresh():
        try:
            all_items = db.list_tickets(state["work_date"])
        except Exception as ex:
            show_snack(f"Erro lendo do banco: {ex}", ok=False)
            return False

        abertos = [t for t in all_items if t.get("status") in ("W", "C")]
        concluidos = [t for t in all_items if t.get("status") in ("F", "D")]
        n_open = sum(1 for t in abertos if t.get("fila") == "N")
        p_open = sum(1 for t in abertos if t.get("fila") == "P")
        e_open = sum(1 for t in abertos if t.get("fila") == "E")
        a_open = sum(1 for t in abertos if t.get("fila") == "A")
        total_open = len(abertos)

        count_n.value = str(n_open)
        count_p.value = str(p_open)
        count_e.value = str(e_open)
        count_a.value = str(a_open)
        done_n.value = str(sum(1 for t in concluidos if t.get("fila") == "N"))
        done_p.value = str(sum(1 for t in concluidos if t.get("fila") == "P"))
        done_e.value = str(sum(1 for t in concluidos if t.get("fila") == "E"))
        done_a.value = str(sum(1 for t in concluidos if t.get("fila") == "A"))

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

        return safe_page_update()

    async def auto_refresh():
        while True:
            if (page.route or "/").rstrip("/") == "/tv":
                await asyncio.sleep(0.8)
                continue
            try:
                if refresh() is False:
                    break
            except Exception:
                break
            await asyncio.sleep(1.5)

    def on_resize(e):
        apply_layout()
        safe_page_update()

    page.on_resize = on_resize

    apply_layout()
    refresh()
    page.run_task(auto_refresh)

    return ft.View(
        route="/",
        controls=[content_host],
        padding=0,
        bgcolor=APP_BG,
        scroll=ft.ScrollMode.AUTO,
    )
