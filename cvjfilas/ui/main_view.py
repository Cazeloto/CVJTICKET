from __future__ import annotations

import asyncio
import logging
import os
import socket
import threading
from datetime import date, datetime, timedelta
from pathlib import Path

import flet as ft

from services.database_service import DatabaseService
from services.print_service import PrintService

from ..core.constants import APP_PORT, IS_SERVER, LOGO_SRC, HIDE_STATUSES
from ..core.ui_utils import fila_label, status_label, status_color


LOG = logging.getLogger("CVJFILAS")


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
    compartilhamento = ft.Share()
    state = {
        "active": True,
        "work_date": date.today(),
        "refreshing": False,
        "operation_busy": False,
        "compartilhando": False,
        "last_signature": None,
        "call_started": False,
        "tickets_by_id": {},
        "render_version": 0,
    }

    def server_address_label() -> str:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.connect(("8.8.8.8", 80))
                ip = s.getsockname()[0]
        except Exception:
            try:
                ip = socket.gethostbyname(socket.gethostname())
            except Exception:
                ip = "127.0.0.1"
        port = os.getenv("APP_PORT", str(APP_PORT)).strip() or str(APP_PORT)
        return f"http://{ip}:{port}"

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

    def print_file(path: str) -> bool:
        try:
            os.startfile(path, "print")
            return True
        except Exception as ex:
            show_snack(f"Nao consegui imprimir automaticamente: {ex}", ok=False)
            return False

    def on_disconnect(e=None):
        state["active"] = False

    _prev_disconnect = page.on_disconnect

    def _on_disconnect_chained(e=None):
        on_disconnect(e)
        if callable(_prev_disconnect):
            _prev_disconnect(e)

    page.on_disconnect = _on_disconnect_chained

    def print_ticket_async(ticket: dict):
        def worker():
            try:
                pdf_path = printer.gerar_senha_a6_pdf(
                    ticket=ticket, work_date=state["work_date"], incluir_qr=True
                )
                os.startfile(pdf_path, "print")
            except Exception:
                LOG.exception("Erro ao imprimir senha em segundo plano")
            finally:
                focus_nome_input()

        threading.Thread(target=worker, daemon=True).start()

    # -------- Entrada única de nome --------
    nome_input = ft.TextField(
        label="Nome do consulente",
        hint_text="Digite o nome e clique na fila",
        expand=True,
        autofocus=True,
    )

    async def focus_nome_input_after_update():
        for delay in (0.08, 0.25, 0.6, 1.2, 2.0):
            await asyncio.sleep(delay)
            try:
                await nome_input.focus()
            except Exception:
                pass

    def focus_nome_input():
        try:
            page.run_task(focus_nome_input_after_update)
        except Exception:
            pass

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

    def fechamento_card(
        title: str, value: int, bg, fg, icon, subtitle: str | None = None
    ) -> ft.Control:
        controls = [
            ft.Icon(icon, color=fg, size=24),
            ft.Text(str(value), size=28, weight=FontWeight.W_900, color=fg),
            ft.Text(
                title,
                size=12,
                weight=FontWeight.W_800,
                color=fg,
                text_align=ft.TextAlign.CENTER,
            ),
        ]
        if subtitle:
            controls.append(
                ft.Text(
                    subtitle,
                    size=10,
                    weight=FontWeight.W_600,
                    color=fg,
                    text_align=ft.TextAlign.CENTER,
                )
            )

        return ft.Container(
            expand=True,
            padding=14,
            border_radius=8,
            bgcolor=bg,
            content=ft.Column(
                spacing=8,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                controls=controls,
            ),
        )

    def relatorio_fechamento_gira(e=None):
        try:
            tickets = db.list_tickets(state["work_date"])
            concluidos = [t for t in tickets if t.get("status") in ("F", "D")]
            counts = {"N": 0, "P": 0, "E": 0}
            for t in concluidos:
                fila = (t.get("fila") or "N").upper()
                if fila in counts:
                    counts[fila] += 1

            total_desistencias = sum(
                1 for t in tickets if (t.get("fila") or "").upper() == "A"
            )

            acompanhantes_por_fila = {"N": 0, "P": 0, "E": 0}
            for t in concluidos:
                fila = (t.get("fila") or "").upper()
                if fila not in acompanhantes_por_fila:
                    continue
                try:
                    acompanhantes_por_fila[fila] += int(t.get("acompanhantes") or 0)
                except Exception:
                    pass
            total_normal = counts["N"] + acompanhantes_por_fila["N"]
            total_prioritario = counts["P"] + acompanhantes_por_fila["P"]
            total_espera = counts["E"] + acompanhantes_por_fila["E"]
            total_pessoas = total_normal + total_prioritario + total_espera

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

            async def gerar_e_compartilhar_fechamento():
                if state["compartilhando"]:
                    return

                state["compartilhando"] = True
                try:
                    page.pop_dialog()
                    pdf_path = printer.gerar_fechamento_gira_pdf(
                        work_date=state["work_date"], tickets=tickets
                    )
                    arquivo = Path(pdf_path)
                    await compartilhamento.share_files(
                        [
                            ft.ShareFile.from_bytes(
                                arquivo.read_bytes(),
                                mime_type="application/pdf",
                                name=arquivo.name,
                            )
                        ],
                        title="Fechamento da Gira",
                        subject=(
                            "Fechamento da gira - "
                            f"{state['work_date'].strftime('%d/%m/%Y')}"
                        ),
                        text=(
                            "Fechamento da gira da Casa da Vovó Joaquina - "
                            f"{state['work_date'].strftime('%d/%m/%Y')}"
                        ),
                        download_fallback_enabled=True,
                        mail_to_fallback_enabled=False,
                    )
                    show_snack(
                        "PDF pronto. Escolha o WhatsApp; se o menu não abrir, "
                        "use o arquivo baixado."
                    )
                except Exception as ex:
                    show_snack(
                        f"Erro ao compartilhar o fechamento: {ex}", ok=False
                    )
                finally:
                    state["compartilhando"] = False

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
                                                    total_normal,
                                                    Colors.BLUE_100,
                                                    Colors.BLUE_900,
                                                    Icons.PEOPLE_ALT,
                                                    f"sendo {acompanhantes_por_fila['N']} acompanhantes",
                                                ),
                                                fechamento_card(
                                                    "Prioridade",
                                                    total_prioritario,
                                                    Colors.AMBER_100,
                                                    Colors.AMBER_900,
                                                    Icons.STAR,
                                                    f"sendo {acompanhantes_por_fila['P']} acompanhantes",
                                                ),
                                                fechamento_card(
                                                    "Espera",
                                                    total_espera,
                                                    Colors.PURPLE_100,
                                                    Colors.PURPLE_900,
                                                    Icons.HOURGLASS_BOTTOM,
                                                    f"sendo {acompanhantes_por_fila['E']} acompanhantes",
                                                ),
                                                fechamento_card(
                                                    "Desistências",
                                                    total_desistencias,
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
                                                    f"Normal: {total_normal}",
                                                    size=15,
                                                    weight=FontWeight.W_700,
                                                ),
                                                ft.Text(
                                                    f"Prioridade: {total_prioritario}",
                                                    size=15,
                                                    weight=FontWeight.W_700,
                                                ),
                                                ft.Text(
                                                    f"Espera: {total_espera}",
                                                    size=15,
                                                    weight=FontWeight.W_700,
                                                ),
                                            ],
                                        ),
                                    ],
                                ),
                            ),
                            ft.Text(
                                "Para enviar, clique em Compartilhar e escolha o "
                                "WhatsApp e os contatos. Se o navegador não abrir "
                                "o menu, o PDF será baixado automaticamente.",
                                size=11,
                                color=Colors.GREY_700,
                            ),
                        ],
                    ),
                ),
                actions=[
                    ft.TextButton("Fechar", on_click=lambda e: page.pop_dialog()),
                    ft.OutlinedButton(
                        "Gerar PDF",
                        icon=Icons.PICTURE_AS_PDF,
                        on_click=gerar_pdf_fechamento,
                    ),
                    ft.ElevatedButton(
                        "Compartilhar",
                        icon=Icons.SHARE,
                        style=ft.ButtonStyle(
                            bgcolor=Colors.GREEN_700,
                            color=Colors.WHITE,
                        ),
                        on_click=lambda e: page.run_task(
                            gerar_e_compartilhar_fechamento
                        ),
                    ),
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
        page.open(date_picker)

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
    cadastro_count = ft.Text("0", size=18, weight=FontWeight.W_900)

    cadastro_normal_list = ft.ListView(spacing=6, expand=True)
    cadastro_pref_list = ft.ListView(spacing=6, expand=True)
    cadastro_esp_list = ft.ListView(spacing=6, expand=True)
    cadastro_aus_list = ft.ListView(spacing=6, expand=True)
    normal_list = ft.ListView(spacing=8, expand=True)
    pref_list = ft.ListView(spacing=8, expand=True)
    esp_list = ft.ListView(spacing=8, expand=True)
    aus_list = ft.ListView(spacing=8, expand=True)
    LIST_RENDER_LIMIT = 25

    def ticket_id(t: dict) -> int:
        return int(t.get("id") or 0)

    def control_ticket_id(control: ft.Control) -> int:
        data = getattr(control, "data", None)
        if isinstance(data, dict):
            return int(data.get("id") or 0)
        return int(data or 0)

    def ticket_control_data(t: dict) -> dict:
        return {
            "id": ticket_id(t),
            "fila": (t.get("fila") or "N").upper(),
            "status": t.get("status") or "W",
            "seq": int(t.get("seq") or 0),
        }

    def ticket_control_key(t: dict, prefix: str) -> str:
        return (
            f"{prefix}-{state['render_version']}-{ticket_id(t)}-"
            f"{(t.get('fila') or 'N').upper()}-"
            f"{t.get('senha') or ''}-"
            f"{t.get('status') or 'W'}"
        )

    def list_for_fila(fila: str, cadastro: bool | None = None) -> ft.ListView:
        use_cadastro = (not state["call_started"]) if cadastro is None else cadastro
        lists = (
            {
                "N": cadastro_normal_list,
                "P": cadastro_pref_list,
                "E": cadastro_esp_list,
                "A": cadastro_aus_list,
            }
            if use_cadastro
            else {"N": normal_list, "P": pref_list, "E": esp_list, "A": aus_list}
        )
        return lists.get((fila or "N").upper(), lists["N"])

    def open_counter_for(fila: str) -> ft.Text:
        return {"N": count_n, "P": count_p, "E": count_e, "A": count_a}.get(
            (fila or "N").upper(), count_n
        )

    def done_counter_for(fila: str) -> ft.Text:
        return {"N": done_n, "P": done_p, "E": done_e, "A": done_a}.get(
            (fila or "N").upper(), done_n
        )

    def dash_counter_for(fila: str) -> ft.Text | None:
        return {
            "N": dash_n_aberto,
            "P": dash_p_aberto,
            "E": dash_e_aberto,
            "A": dash_a_aberto,
        }.get((fila or "N").upper())

    def change_counter(text_control: ft.Text | None, delta: int):
        if text_control is None or delta == 0:
            return
        try:
            value = int(text_control.value or "0") + delta
        except Exception:
            value = delta
        text_control.value = str(max(0, value))

    def is_open_status(status: str) -> bool:
        return status in ("W", "C")

    def is_done_status(status: str) -> bool:
        return status in ("F", "D")

    def is_visible_ticket(t: dict) -> bool:
        return (t.get("status") or "W") not in HIDE_STATUSES

    def update_counters_for_change(old_t: dict | None, new_t: dict | None):
        old_fila = (old_t or {}).get("fila")
        old_status = (old_t or {}).get("status")
        new_fila = (new_t or {}).get("fila")
        new_status = (new_t or {}).get("status")

        if old_t and is_open_status(old_status):
            change_counter(open_counter_for(old_fila), -1)
            if IS_SERVER:
                change_counter(dash_total_aberto, -1)
                change_counter(dash_counter_for(old_fila), -1)
        if old_t and is_done_status(old_status):
            change_counter(done_counter_for(old_fila), -1)

        if new_t and is_open_status(new_status):
            change_counter(open_counter_for(new_fila), 1)
            if IS_SERVER:
                change_counter(dash_total_aberto, 1)
                change_counter(dash_counter_for(new_fila), 1)
        if new_t and is_done_status(new_status):
            change_counter(done_counter_for(new_fila), 1)

    def prio_status(s: str) -> int:
        return {"C": 0, "W": 1, "F": 2, "D": 3, "X": 4}.get(s, 9)

    def control_sort_key(control: ft.Control) -> tuple:
        data = getattr(control, "data", None) or {}
        return (prio_status(data.get("status", "W")), int(data.get("seq") or 0))

    def ticket_sort_key(t: dict) -> tuple:
        return (prio_status(t.get("status", "W")), int(t.get("seq", 0)))

    def cadastro_sort_key(t: dict) -> tuple:
        return (-int(t.get("seq", 0)), -ticket_id(t))

    def visible_tickets_for_fila(
        fila: str, cadastro: bool | None = None
    ) -> list[dict]:
        use_cadastro = (not state["call_started"]) if cadastro is None else cadastro
        fila = (fila or "N").upper()
        seen_ids = set()
        items = []
        for t in state["tickets_by_id"].values():
            tid = ticket_id(t)
            if tid in seen_ids:
                continue
            if (t.get("fila") or "N").upper() != fila or not is_visible_ticket(t):
                continue
            seen_ids.add(tid)
            items.append(t)
        items.sort(key=cadastro_sort_key if use_cadastro else ticket_sort_key)
        return items

    def render_fila_from_cache(fila: str, cadastro: bool | None = None):
        use_cadastro = (not state["call_started"]) if cadastro is None else cadastro
        lv = list_for_fila(fila, cadastro=use_cadastro)
        card_factory = cadastro_row if use_cadastro else ticket_card
        state["render_version"] += 1
        lv.controls.clear()
        lv.controls = [
            card_factory(t)
            for t in visible_tickets_for_fila(fila, use_cadastro)[:LIST_RENDER_LIMIT]
        ]

    def remove_ticket_control(ticket_id_value: int, fila: str | None = None):
        lists = [list_for_fila(fila)] if fila else [
            normal_list,
            pref_list,
            esp_list,
            aus_list,
            cadastro_normal_list,
            cadastro_pref_list,
            cadastro_esp_list,
            cadastro_aus_list,
        ]
        for lv in lists:
            for idx, control in enumerate(list(lv.controls)):
                if control_ticket_id(control) == ticket_id_value:
                    return lv, idx, lv.controls.pop(idx)
        return None, None, None

    def insert_ticket_control(t: dict):
        if state["call_started"]:
            render_fila_from_cache(t.get("fila"), cadastro=False)
            return None

        control = cadastro_row(t) if not state["call_started"] else ticket_card(t)
        lv = list_for_fila(t.get("fila"))
        key = control_sort_key(control)
        for idx, existing in enumerate(lv.controls):
            if key < control_sort_key(existing):
                lv.controls.insert(idx, control)
                break
        else:
            lv.controls.append(control)
        return control

    def apply_ticket_change(old_t: dict | None, new_t: dict | None):
        old_id = ticket_id(old_t) if old_t else ticket_id(new_t or {})
        old_fila = (old_t or {}).get("fila")
        if old_id:
            remove_ticket_control(old_id, old_fila)

        old_visible = bool(old_t and is_visible_ticket(old_t))
        visible_new = bool(new_t and is_visible_ticket(new_t))
        change_counter(cadastro_count, int(visible_new) - int(old_visible))
        update_counters_for_change(old_t, new_t)

        if new_t:
            state["tickets_by_id"][ticket_id(new_t)] = dict(new_t)
        elif old_id:
            state["tickets_by_id"].pop(old_id, None)

        if state["call_started"]:
            affected = {
                (old_fila or "").upper(),
                ((new_t or {}).get("fila") or "").upper(),
            }
            for fila in affected:
                if fila in ("N", "P", "E", "A"):
                    render_fila_from_cache(fila, cadastro=False)
        else:
            affected = {
                (old_fila or "").upper(),
                ((new_t or {}).get("fila") or "").upper(),
            }
            for fila in affected:
                if fila in ("N", "P", "E", "A"):
                    render_fila_from_cache(fila, cadastro=True)

        state["last_signature"] = None
        return safe_page_update()

    def render_call_board_from_cache() -> bool:
        items = [
            t
            for t in state["tickets_by_id"].values()
            if (t.get("status") not in HIDE_STATUSES)
        ]
        if not items:
            return False

        by = {"N": [], "P": [], "E": [], "A": []}
        for t in items:
            by.get(t.get("fila", "N"), by["N"]).append(t)
        for f in ("N", "P", "E", "A"):
            by[f].sort(
                key=lambda x: (prio_status(x.get("status", "W")), int(x.get("seq", 0)))
            )

        state["render_version"] += 1
        normal_list.controls = [ticket_card(t) for t in by["N"][:LIST_RENDER_LIMIT]]
        pref_list.controls = [ticket_card(t) for t in by["P"][:LIST_RENDER_LIMIT]]
        esp_list.controls = [ticket_card(t) for t in by["E"][:LIST_RENDER_LIMIT]]
        aus_list.controls = [ticket_card(t) for t in by["A"][:LIST_RENDER_LIMIT]]
        state["last_signature"] = None
        return safe_page_update()

    imprimir_ao_gerar = ft.Switch(
        label="Imp.", tooltip="Imprimir ao gerar", value=True, visible=IS_SERVER
    )

    def criar_na_fila(fila_code: str):
        n = (nome_input.value or "").strip().upper()
        if not n:
            show_snack("Digite o nome do consulente.", ok=False)
            focus_nome_input()
            return
        state["operation_busy"] = True
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
            acompanhantes_dd.value = "0"
            append_created_ticket(t)
            show_snack(f"Senha gerada: {t.get('senha')} ({fila_label_ui(fila_code)})")
            if IS_SERVER and imprimir_ao_gerar.value:
                print_ticket_async(t)
        except Exception as ex:
            show_snack(f"Erro ao gerar: {ex}", ok=False)
        finally:
            state["operation_busy"] = False
            focus_nome_input()

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
                nome_input,
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
            state["operation_busy"] = True
            try:
                updated = db.call_ticket(int(t["id"]), origin_device=device)
                apply_ticket_change(t, updated)
            finally:
                state["operation_busy"] = False

        def on_confirm(e):
            if st in ("X", "D", "F"):
                return
            state["operation_busy"] = True
            try:
                updated = db.confirm_ticket(int(t["id"]), origin_device=device)
                apply_ticket_change(t, updated)
            finally:
                state["operation_busy"] = False

        def on_cancel(e):
            if st == "X":
                return
            state["operation_busy"] = True
            try:
                if (t.get("fila") or "").upper() == "A":
                    db.delete_ticket(int(t["id"]), origin_device=device)
                    apply_ticket_change(t, None)
                else:
                    updated = db.cancel_ticket(int(t["id"]), origin_device=device)
                    apply_ticket_change(t, updated)
            finally:
                state["operation_busy"] = False

        def on_nao_apareceu(e=None):
            if st in ("X", "D", "F"):
                return
            if (t.get("fila") or "").upper() == "A":
                return
            state["operation_busy"] = True
            try:
                updated = db.move_ticket(int(t["id"]), "A", origin_device=device)
                apply_ticket_change(t, updated)
            finally:
                state["operation_busy"] = False

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
            key=ticket_control_key(t, "ticket"),
            data=ticket_control_data(t),
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

    def append_created_ticket(t: dict) -> bool:
        fila = (t.get("fila") or "N").upper()
        state["tickets_by_id"][ticket_id(t)] = dict(t)
        target = {"N": normal_list, "P": pref_list, "E": esp_list, "A": aus_list}.get(
            fila
        )
        counter = {"N": count_n, "P": count_p, "E": count_e, "A": count_a}.get(fila)
        dash_counter = {
            "N": dash_n_aberto,
            "P": dash_p_aberto,
            "E": dash_e_aberto,
            "A": dash_a_aberto,
        }.get(fila)

        if target is None or counter is None:
            return refresh(force=True)

        def inc(text_control: ft.Text):
            try:
                text_control.value = str(int(text_control.value or "0") + 1)
            except Exception:
                text_control.value = "1"

        cadastro_target = {
            "N": cadastro_normal_list,
            "P": cadastro_pref_list,
            "E": cadastro_esp_list,
            "A": cadastro_aus_list,
        }.get(fila)

        inc(counter)
        inc(cadastro_count)
        if IS_SERVER:
            inc(dash_total_aberto)
            if dash_counter is not None:
                inc(dash_counter)

        if not state["call_started"]:
            if cadastro_target is None:
                return refresh(force=True)
            render_fila_from_cache(fila, cadastro=True)
            state["last_signature"] = None
            return safe_page_update()

        render_fila_from_cache(fila, cadastro=False)
        state["last_signature"] = None
        return safe_page_update()

    def cadastro_row(t: dict) -> ft.Control:
        fila = (t.get("fila") or "N").upper()
        senha = str(t.get("senha") or "-")
        nome = (t.get("nome_livre") or "- sem nome -").strip()
        acomp = (
            int(t.get("acompanhantes") or 0)
            if str(t.get("acompanhantes") or "0").isdigit()
            else 0
        )
        if acomp > 0:
            nome = f"{nome} +{acomp}"

        bg, icc, tx = fila_header_style(fila)

        def apagar(e=None):
            state["operation_busy"] = True
            try:
                db.delete_ticket(int(t["id"]), origin_device=device)
                apply_ticket_change(t, None)
            except Exception as ex:
                show_snack(f"Erro ao apagar: {ex}", ok=False)
            finally:
                state["operation_busy"] = False

        return ft.Container(
            key=ticket_control_key(t, "cadastro"),
            data=ticket_control_data(t),
            height=44,
            padding=ft.padding.symmetric(horizontal=10, vertical=4),
            border_radius=8,
            bgcolor=Colors.WHITE,
            border=ft.border.all(1, Colors.OUTLINE_VARIANT),
            content=ft.Row(
                spacing=10,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Container(
                        width=76,
                        padding=ft.padding.symmetric(horizontal=8, vertical=6),
                        border_radius=8,
                        bgcolor=bg,
                        content=ft.Text(
                            senha,
                            size=14,
                            weight=FontWeight.W_900,
                            color=tx,
                            text_align=ft.TextAlign.CENTER,
                        ),
                    ),
                    ft.Icon(
                        Icons.STAR if fila == "P" else Icons.PEOPLE_ALT,
                        size=18,
                        color=icc,
                    ),
                    ft.Text(
                        nome,
                        expand=True,
                        size=14,
                        weight=FontWeight.W_700,
                        max_lines=1,
                        overflow=ft.TextOverflow.ELLIPSIS,
                    ),
                    ft.IconButton(
                        Icons.DELETE_OUTLINE,
                        tooltip="Apagar",
                        on_click=apagar,
                        icon_size=18,
                        width=34,
                        height=32,
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

    cadastro_board = ft.ResponsiveRow(
        columns=12,
        spacing=12,
        run_spacing=12,
        controls=[
            ft.Container(
                col={"xs": 12, "md": 3},
                content=desktop_col(
                    "Normal",
                    Icons.PEOPLE_ALT,
                    cadastro_normal_list,
                    "N",
                    count_n,
                    done_n,
                ),
            ),
            ft.Container(
                col={"xs": 12, "md": 3},
                content=desktop_col(
                    "Preferencial",
                    Icons.STAR,
                    cadastro_pref_list,
                    "P",
                    count_p,
                    done_p,
                ),
            ),
            ft.Container(
                col={"xs": 12, "md": 3},
                content=desktop_col(
                    "Espera",
                    Icons.HOURGLASS_BOTTOM,
                    cadastro_esp_list,
                    "E",
                    count_e,
                    done_e,
                ),
            ),
            ft.Container(
                col={"xs": 12, "md": 3},
                content=desktop_col(
                    "Não apareceu",
                    Icons.PERSON_OFF,
                    cadastro_aus_list,
                    "A",
                    count_a,
                    done_a,
                    False,
                ),
            ),
        ],
    )

    def iniciar_gira(e=None):
        state["call_started"] = True
        iniciar_gira_btn.visible = False
        apply_layout()
        if not render_call_board_from_cache():
            refresh(force=True)
        show_snack("Gira iniciada.")

    iniciar_gira_btn = top_action_button(
        "Iniciar",
        Icons.PLAY_ARROW,
        iniciar_gira,
        Colors.GREEN_700,
        tooltip="Iniciar gira",
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
                            tooltip=(
                                "Endereco do servidor"
                                if IS_SERVER
                                else "Terminal cliente"
                            ),
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
                                        server_address_label() if IS_SERVER else "Cliente",
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
                        iniciar_gira_btn,
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
                desktop_board if state["call_started"] else cadastro_board,
            ],
        )

    # -------- Refresh --------
    def tickets_signature(items: list[dict]) -> tuple:
        return tuple(
            (
                t.get("id"),
                t.get("fila"),
                t.get("status"),
                t.get("seq"),
                t.get("senha"),
                t.get("called_at"),
                t.get("confirmed_at"),
                t.get("updated_at"),
            )
            for t in items
        )

    def refresh(force: bool = False):
        if state["refreshing"]:
            return True
        state["refreshing"] = True
        try:
            all_items = db.list_tickets(state["work_date"])
        except Exception as ex:
            show_snack(f"Erro lendo do banco: {ex}", ok=False)
            state["refreshing"] = False
            return False

        signature = tickets_signature(all_items)
        if not force and signature == state["last_signature"]:
            state["refreshing"] = False
            return True
        state["last_signature"] = signature
        state["tickets_by_id"] = {ticket_id(t): dict(t) for t in all_items}

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

        cadastro_count.value = str(len(items))
        state["render_version"] += 1
        if state["call_started"]:
            normal_list.controls.clear()
            pref_list.controls.clear()
            esp_list.controls.clear()
            aus_list.controls.clear()
            normal_list.controls = [ticket_card(t) for t in by["N"][:LIST_RENDER_LIMIT]]
            pref_list.controls = [ticket_card(t) for t in by["P"][:LIST_RENDER_LIMIT]]
            esp_list.controls = [ticket_card(t) for t in by["E"][:LIST_RENDER_LIMIT]]
            aus_list.controls = [ticket_card(t) for t in by["A"][:LIST_RENDER_LIMIT]]
        else:
            for f in ("N", "P", "E", "A"):
                by[f].sort(key=cadastro_sort_key)
            cadastro_normal_list.controls.clear()
            cadastro_pref_list.controls.clear()
            cadastro_esp_list.controls.clear()
            cadastro_aus_list.controls.clear()
            cadastro_normal_list.controls = [
                cadastro_row(t) for t in by["N"][:LIST_RENDER_LIMIT]
            ]
            cadastro_pref_list.controls = [
                cadastro_row(t) for t in by["P"][:LIST_RENDER_LIMIT]
            ]
            cadastro_esp_list.controls = [
                cadastro_row(t) for t in by["E"][:LIST_RENDER_LIMIT]
            ]
            cadastro_aus_list.controls = [
                cadastro_row(t) for t in by["A"][:LIST_RENDER_LIMIT]
            ]

        try:
            return safe_page_update()
        finally:
            state["refreshing"] = False

    async def auto_refresh():
        while state["active"]:
            route = (page.route or "/").split("?", 1)[0].rstrip("/") or "/"
            if route != "/":
                break
            if state["operation_busy"] or state["refreshing"]:
                await asyncio.sleep(0.5)
                continue
            try:
                result = await asyncio.to_thread(refresh)
                if result is False:
                    break
            except Exception:
                break
            await asyncio.sleep(5)

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
