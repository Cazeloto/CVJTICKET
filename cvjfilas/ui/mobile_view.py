from __future__ import annotations

import asyncio
from datetime import date
from pathlib import Path

import flet as ft

from cvjfilas.core.constants import LOGO_SRC
from services.database_service import DatabaseService
from services.print_service import PrintService


BG = "#F6EEF6"
HEADER = "#8B5A91"
TEXT = "#503054"
DEVICE = "CELULAR"

QUEUE_INFO = {
    "N": ("Normal", ft.Icons.PEOPLE_ALT, "#E8F0FE", "#2855A6"),
    "P": ("Preferencial", ft.Icons.STAR, "#FFF3CD", "#7A5900"),
    "E": ("Espera", ft.Icons.HOURGLASS_BOTTOM, "#F3E5F5", "#6A3472"),
    "A": ("Não apareceu", ft.Icons.PERSON_OFF, "#FDE7E9", "#9B1C31"),
}


def _setup(page: ft.Page, title: str):
    page.title = title
    page.theme_mode = ft.ThemeMode.LIGHT
    page.theme = ft.Theme(color_scheme_seed=HEADER)


def _header(
    page: ft.Page,
    title: str,
    back: str | None = None,
    trailing: ft.Control | None = None,
):
    controls = []
    if back:
        controls.append(
            ft.IconButton(
                icon=ft.Icons.ARROW_BACK,
                icon_color=ft.Colors.WHITE,
                tooltip="Voltar",
                on_click=lambda e: page.go(back),
            )
        )
    controls.extend(
        [
            ft.Image(src=LOGO_SRC, width=44, height=40, fit="contain"),
            ft.Text(
                title,
                expand=True,
                size=20,
                weight=ft.FontWeight.W_900,
                color=ft.Colors.WHITE,
            ),
        ]
    )
    if trailing:
        controls.append(trailing)
    return ft.Container(
        bgcolor=HEADER,
        padding=ft.padding.symmetric(horizontal=8, vertical=9),
        content=ft.Row(controls, vertical_alignment=ft.CrossAxisAlignment.CENTER),
    )


def _snack(page: ft.Page, message: str, ok: bool = True):
    page.snack_bar = ft.SnackBar(
        ft.Text(message, color=ft.Colors.WHITE),
        bgcolor=ft.Colors.GREEN_700 if ok else ft.Colors.RED_700,
    )
    page.snack_bar.open = True
    page.update()


def _ticket_name(ticket: dict) -> str:
    name = str(ticket.get("nome_livre") or "Sem nome").strip()
    companions = int(ticket.get("acompanhantes") or 0)
    return f"{name} +{companions}" if companions else name


def build_mobile_home(page: ft.Page, db: DatabaseService, printer: PrintService) -> ft.View:
    _setup(page, "CVJTICKET no celular")

    def menu_card(title, subtitle, icon, color, route):
        return ft.Container(
            ink=True,
            on_click=lambda e: page.go(route),
            bgcolor=ft.Colors.WHITE,
            border_radius=16,
            padding=20,
            content=ft.Row(
                [
                    ft.Container(
                        width=58,
                        height=58,
                        border_radius=16,
                        bgcolor=color,
                        alignment=ft.Alignment.CENTER,
                        content=ft.Icon(icon, size=32, color=ft.Colors.WHITE),
                    ),
                    ft.Column(
                        [
                            ft.Text(title, size=21, weight=ft.FontWeight.BOLD, color=TEXT),
                            ft.Text(subtitle, size=13, color=ft.Colors.GREY_700),
                        ],
                        spacing=3,
                        expand=True,
                    ),
                    ft.Icon(ft.Icons.CHEVRON_RIGHT, color=HEADER),
                ],
                spacing=14,
            ),
        )

    root = ft.Column(
        [
            _header(page, "CVJTICKET — Celular"),
            ft.Container(
                padding=16,
                content=ft.Column(
                    [
                        ft.Text(
                            "O que você deseja fazer?",
                            size=16,
                            weight=ft.FontWeight.W_700,
                            color=TEXT,
                        ),
                        menu_card(
                            "Cadastrar nas filas",
                            "Gerar senhas e organizar os consulentes",
                            ft.Icons.PERSON_ADD_ALT_1,
                            "#6E4A75",
                            "/Celular/cadastro",
                        ),
                        menu_card(
                            "Chamar consulentes",
                            "Chamar, concluir e controlar as filas",
                            ft.Icons.CAMPAIGN,
                            "#2E7D5B",
                            "/Celular/chamada",
                        ),
                        ft.TextButton(
                            "Abrir versão completa",
                            icon=ft.Icons.DESKTOP_WINDOWS,
                            on_click=lambda e: page.go("/"),
                        ),
                    ],
                    spacing=14,
                    horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
                ),
            ),
        ],
        spacing=0,
    )
    return ft.View(
        route="/Celular",
        padding=0,
        controls=[root],
        bgcolor=BG,
        scroll=ft.ScrollMode.AUTO,
    )


def build_mobile_registration(
    page: ft.Page, db: DatabaseService, printer: PrintService
) -> ft.View:
    _setup(page, "Cadastro de filas — CVJTICKET")
    busy = {"value": False}

    name_field = ft.TextField(
        label="Nome do consulente",
        hint_text="Digite o nome",
        prefix_icon=ft.Icons.PERSON_OUTLINE,
        autofocus=True,
        autocorrect=False,
    )
    loading = ft.ProgressRing(width=20, height=20, stroke_width=2, visible=False)

    def on_name_change(e):
        value = (e.control.value or "").upper()
        if value != e.control.value:
            e.control.value = value
            e.control.update()

    name_field.on_change = on_name_change

    async def create_in_queue(queue: str):
        if busy["value"]:
            return
        name = " ".join((name_field.value or "").strip().split()).upper()
        if not name:
            _snack(page, "Informe o nome do consulente.", False)
            return
        busy["value"] = True
        loading.visible = True
        page.update()
        try:
            ticket = await asyncio.to_thread(
                db.create_ticket,
                date.today(),
                name,
                queue,
                "N",
                DEVICE,
                "",
                "",
                0,
            )
            name_field.value = ""
            _snack(page, f"Senha gerada: {ticket.get('senha')} — {_ticket_name(ticket)}")
        except Exception as ex:
            _snack(page, f"Erro ao gerar senha: {ex}", False)
        finally:
            busy["value"] = False
            loading.visible = False
            page.update()

    def queue_button(queue: str):
        label, icon, background, accent = QUEUE_INFO[queue]
        return ft.ElevatedButton(
            label,
            icon=icon,
            height=52,
            style=ft.ButtonStyle(bgcolor=background, color=accent),
            on_click=lambda e: page.run_task(create_in_queue, queue),
        )

    root = ft.Column(
        [
            _header(page, "Cadastrar nas filas", "/Celular"),
            ft.Container(
                padding=12,
                content=ft.Column(
                    [
                        ft.Text(
                            "Informe o nome e toque na fila desejada.",
                            size=13,
                            color=ft.Colors.GREY_700,
                        ),
                        name_field,
                        ft.Row(
                            [
                                ft.Text(
                                    "Adicionar à fila",
                                    expand=True,
                                    weight=ft.FontWeight.BOLD,
                                    color=TEXT,
                                ),
                                loading,
                            ]
                        ),
                        queue_button("N"),
                        queue_button("P"),
                        queue_button("E"),
                    ],
                    spacing=10,
                    horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
                ),
            ),
        ],
        spacing=0,
    )

    view = ft.View(
        route="/Celular/cadastro",
        padding=0,
        controls=[root],
        bgcolor=BG,
        scroll=ft.ScrollMode.AUTO,
    )
    return view


def build_mobile_call(page: ft.Page, db: DatabaseService, printer: PrintService) -> ft.View:
    _setup(page, "Chamada — CVJTICKET")
    state = {"queue": "P", "busy": False, "sharing": False, "active": True}
    page._mobile_call_session = state
    share = ft.Share()
    list_host = ft.Column(spacing=10)
    counts = {
        queue: ft.Text(
            "0",
            size=11,
            weight=ft.FontWeight.BOLD,
            color=ft.Colors.WHITE,
        )
        for queue in QUEUE_INFO
    }
    open_triages = ft.Text(
        "0",
        size=16,
        weight=ft.FontWeight.W_900,
        color=ft.Colors.WHITE,
    )
    update_text = ft.Text("Carregando...", size=12, color=ft.Colors.WHITE70)

    def route_is_active():
        route = (page.route or "").split("?", 1)[0].rstrip("/").lower()
        return (route in ("/celular", "/celular/chamada")
                and getattr(page, "_mobile_call_session", None) is state)

    def on_disconnect(e=None):
        state["active"] = False

    _prev_disconnect = page.on_disconnect

    def _on_disconnect_chained(e=None):
        on_disconnect(e)
        if callable(_prev_disconnect):
            _prev_disconnect(e)

    page.on_disconnect = _on_disconnect_chained

    def add_waiting(e=None):
        name = ft.TextField(
            label="Nome do consulente", autofocus=True, autocorrect=False,
            capitalization=ft.TextCapitalization.CHARACTERS,
        )
        saving = {"value": False}

        async def save(e=None):
            if saving["value"]:
                return
            value = " ".join((name.value or "").split()).upper()
            if not value:
                name.error_text = "Informe o nome do consulente."
                page.update()
                return
            saving["value"] = True
            submit.disabled = True
            cancel.disabled = True
            name.error_text = None
            page.update()
            try:
                ticket = await asyncio.to_thread(
                    db.create_ticket, date.today(), value, "E", "N", DEVICE,
                )
            except Exception:
                name.error_text = "Não foi possível cadastrar. Verifique a conexão e tente novamente."
                saving["value"] = False
                submit.disabled = False
                cancel.disabled = False
                page.update()
                return
            page.pop_dialog()
            state["queue"] = "E"
            await refresh()
            select_queue("E")
            _snack(page, f"Adicionado à espera: {ticket.get('senha')} — {value}")

        submit = ft.ElevatedButton(
            "Adicionar à espera", icon=ft.Icons.PERSON_ADD_ALT_1,
            height=52, on_click=save,
        )
        cancel = ft.TextButton("Voltar", on_click=lambda e: page.pop_dialog())
        name.on_submit = save
        page.show_dialog(ft.AlertDialog(
            modal=True, title=ft.Text("Adicionar à fila de espera"),
            content=ft.Column([
                ft.Text("Para quem chegou após a distribuição de senhas."), name,
            ], tight=True),
            actions=[cancel, submit],
        ))

    async def call_next(e=None):
        if state["busy"]:
            return
        candidates = [item for item in cache["items"]
                      if item.get("status") == "W"
                      and str(item.get("fila") or "N").upper() == state["queue"]]
        if candidates:
            await act(min(candidates, key=lambda item: int(item.get("seq") or 0)), "call")

    next_button = ft.ElevatedButton(
        "Chamar próximo", icon=ft.Icons.CAMPAIGN, height=56,
        disabled=True, on_click=call_next,
        style=ft.ButtonStyle(bgcolor="#2E7D5B", color=ft.Colors.WHITE),
    )

    async def share_closure(tickets: list[dict]):
        if state["sharing"]:
            return
        state["sharing"] = True
        page.pop_dialog()
        try:
            pdf_path = await asyncio.to_thread(
                printer.gerar_fechamento_gira_pdf,
                date.today(),
                tickets,
            )
            arquivo = Path(pdf_path)
            arquivo_bytes = await asyncio.to_thread(arquivo.read_bytes)
            await share.share_files(
                [
                    ft.ShareFile.from_bytes(
                        arquivo_bytes,
                        mime_type="application/pdf",
                        name=arquivo.name,
                    )
                ],
                title="Fechamento da Gira",
                subject=f"Fechamento da gira - {date.today().strftime('%d/%m/%Y')}",
                text=(
                    "Fechamento da gira da Casa da Vovó Joaquina - "
                    f"{date.today().strftime('%d/%m/%Y')}"
                ),
                download_fallback_enabled=True,
                mail_to_fallback_enabled=False,
            )
            _snack(
                page,
                "PDF pronto. Escolha o WhatsApp; se o menu não abrir, use o arquivo baixado.",
            )
        except Exception as ex:
            _snack(page, f"Erro ao compartilhar o fechamento: {ex}", False)
        finally:
            state["sharing"] = False

    async def show_closure():
        if state["sharing"]:
            return
        try:
            tickets = await asyncio.to_thread(db.list_tickets, date.today())
            concluded = [ticket for ticket in tickets if ticket.get("status") in ("F", "D")]
            concluded_counts = {"N": 0, "P": 0, "E": 0}
            companions = {"N": 0, "P": 0, "E": 0}
            for ticket in concluded:
                queue = str(ticket.get("fila") or "N").upper()
                if queue in concluded_counts:
                    concluded_counts[queue] += 1
                    try:
                        companions[queue] += int(ticket.get("acompanhantes") or 0)
                    except (TypeError, ValueError):
                        pass
            totals = {
                queue: concluded_counts[queue] + companions[queue]
                for queue in concluded_counts
            }
            absent = sum(
                1
                for ticket in tickets
                if str(ticket.get("fila") or "").upper() == "A"
            )
            total_people = sum(totals.values())

            def summary_row(
                label: str,
                value: int,
                color: str,
                subtitle: str | None = None,
            ):
                labels = [
                    ft.Text(label, weight=ft.FontWeight.BOLD, color=TEXT),
                ]
                if subtitle:
                    labels.append(
                        ft.Text(subtitle, size=10, color=ft.Colors.GREY_700)
                    )
                return ft.Container(
                    bgcolor=color,
                    border_radius=9,
                    padding=ft.padding.symmetric(horizontal=12, vertical=9),
                    content=ft.Row(
                        [
                            ft.Column(labels, expand=True, spacing=1),
                            ft.Text(str(value), size=18, weight=ft.FontWeight.W_900, color=TEXT),
                        ]
                    ),
                )

            dialog = ft.AlertDialog(
                modal=True,
                title=ft.Text("Fechamento da gira", weight=ft.FontWeight.W_900),
                content=ft.Column(
                    [
                        ft.Text(
                            date.today().strftime("%d/%m/%Y"),
                            color=ft.Colors.GREY_700,
                        ),
                        summary_row(
                            "Normal",
                            totals["N"],
                            QUEUE_INFO["N"][2],
                            f"sendo {companions['N']} acompanhantes",
                        ),
                        summary_row(
                            "Prioridade",
                            totals["P"],
                            QUEUE_INFO["P"][2],
                            f"sendo {companions['P']} acompanhantes",
                        ),
                        summary_row(
                            "Espera",
                            totals["E"],
                            QUEUE_INFO["E"][2],
                            f"sendo {companions['E']} acompanhantes",
                        ),
                        summary_row("Desistências", absent, QUEUE_INFO["A"][2]),
                        ft.Text(
                            f"Total atendido: {total_people}",
                            size=18,
                            weight=ft.FontWeight.W_900,
                            color=TEXT,
                        ),
                    ],
                    tight=True,
                    spacing=8,
                ),
                actions=[
                    ft.TextButton("Cancelar", on_click=lambda e: page.pop_dialog()),
                    ft.ElevatedButton(
                        "Compartilhar",
                        icon=ft.Icons.SHARE,
                        style=ft.ButtonStyle(
                            bgcolor=ft.Colors.GREEN_700,
                            color=ft.Colors.WHITE,
                        ),
                        on_click=lambda e: page.run_task(share_closure, tickets),
                    ),
                ],
            )
            page.show_dialog(dialog)
        except Exception as ex:
            _snack(page, f"Erro no fechamento: {ex}", False)

    async def act(ticket: dict, action: str, dialog=None):
        if state["busy"]:
            return
        if dialog:
            page.pop_dialog()
        state["busy"] = True
        next_button.disabled = True
        page.update()
        try:
            ticket_id = int(ticket["id"])
            if action == "call":
                await asyncio.to_thread(db.call_ticket, ticket_id, DEVICE)
                message = f"Chamando {ticket.get('senha')} — {_ticket_name(ticket)}"
            elif action == "finish":
                await asyncio.to_thread(db.confirm_ticket, ticket_id, DEVICE)
                message = "Atendimento concluído."
            elif action == "absent":
                await asyncio.to_thread(db.move_ticket, ticket_id, "A", DEVICE)
                message = "Movido para Não apareceu."
            elif str(ticket.get("fila") or "").upper() == "A":
                await asyncio.to_thread(db.delete_ticket, ticket_id, DEVICE)
                message = "Registro removido."
            else:
                await asyncio.to_thread(db.cancel_ticket, ticket_id, DEVICE)
                message = "Senha cancelada."
            _snack(page, message)
            await refresh()
        except Exception as ex:
            _snack(page, f"Erro na operação: {ex}", False)
        finally:
            state["busy"] = False
            render_current()
            page.update()

    def confirm_action(ticket: dict, action: str, title: str, message: str):
        dialog = ft.AlertDialog(modal=True, title=ft.Text(title), content=ft.Text(message))
        dialog.actions = [
            ft.TextButton("Cancelar", on_click=lambda e: close_dialog(dialog)),
            ft.ElevatedButton(
                "Confirmar",
                on_click=lambda e: page.run_task(act, ticket, action, dialog),
            ),
        ]
        page.show_dialog(dialog)

    def close_dialog(dialog):
        page.pop_dialog()

    def ticket_card(ticket: dict):
        queue = str(ticket.get("fila") or "N").upper()
        label, icon, background, accent = QUEUE_INFO.get(queue, QUEUE_INFO["N"])
        called = ticket.get("status") == "C"
        actions = [
            ft.ElevatedButton(
                "Chamar novamente" if called else "Chamar",
                icon=ft.Icons.CAMPAIGN,
                height=46,
                expand=True,
                style=ft.ButtonStyle(bgcolor=accent, color=ft.Colors.WHITE),
                on_click=lambda e: page.run_task(act, ticket, "call"),
            ),
            ft.ElevatedButton(
                "Concluir",
                icon=ft.Icons.CHECK_CIRCLE,
                height=46,
                expand=True,
                style=ft.ButtonStyle(bgcolor=ft.Colors.GREEN_700, color=ft.Colors.WHITE),
                on_click=lambda e: page.run_task(act, ticket, "finish"),
            ),
        ]
        secondary = []
        if queue != "A":
            secondary.append(
                ft.OutlinedButton(
                    "Não apareceu",
                    icon=ft.Icons.PERSON_OFF,
                    on_click=lambda e: confirm_action(
                        ticket,
                        "absent",
                        "Não apareceu",
                        f"Mover {ticket.get('senha')} para Não apareceu?",
                    ),
                )
            )
        secondary.append(
            ft.IconButton(
                icon=ft.Icons.DELETE_OUTLINE,
                icon_color=ft.Colors.RED_700,
                tooltip="Apagar" if queue == "A" else "Cancelar senha",
                on_click=lambda e: confirm_action(
                    ticket,
                    "cancel",
                    "Apagar registro" if queue == "A" else "Cancelar senha",
                    f"Confirmar para {ticket.get('senha')} — {_ticket_name(ticket)}?",
                ),
            )
        )
        return ft.Container(
            bgcolor=ft.Colors.WHITE,
            border_radius=13,
            padding=13,
            border=ft.border.all(2 if called else 1, accent),
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.Container(
                                width=86,
                                padding=10,
                                border_radius=10,
                                bgcolor=background,
                                content=ft.Text(
                                    str(ticket.get("senha") or "-"),
                                    size=19,
                                    weight=ft.FontWeight.W_900,
                                    color=accent,
                                    text_align=ft.TextAlign.CENTER,
                                ),
                            ),
                            ft.Text(
                                _ticket_name(ticket),
                                expand=True,
                                size=18,
                                weight=ft.FontWeight.BOLD,
                                color=TEXT,
                            ),
                        ],
                        spacing=10,
                    ),
                    ft.Text(
                        "Já chamado" if called else "Aguardando chamada",
                        size=12,
                        color=ft.Colors.GREEN_700 if called else ft.Colors.GREY_700,
                        weight=ft.FontWeight.BOLD,
                    ),
                    ft.Row(actions, spacing=8),
                    ft.Row(
                        secondary,
                        alignment=ft.MainAxisAlignment.END,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                ],
                spacing=9,
            ),
        )

    tabs = {}

    def select_queue(queue: str):
        state["queue"] = queue
        for code, control in tabs.items():
            selected = code == queue
            control.bgcolor = QUEUE_INFO[code][2] if selected else "#E5D5E5"
            control.border = ft.border.only(
                bottom=ft.BorderSide(4 if selected else 1, QUEUE_INFO[code][3])
            )
        render_current()
        page.update()

    cache = {"items": []}

    def render_current():
        queue = state["queue"]
        items = [item for item in cache["items"] if str(item.get("fila") or "N").upper() == queue]
        items.sort(key=lambda item: (0 if item.get("status") == "C" else 1, int(item.get("seq") or 0)))
        next_button.text = f"Chamar próximo • {QUEUE_INFO[queue][0]}"
        next_button.disabled = state["busy"] or not any(item.get("status") == "W" for item in items)
        list_host.controls = [ticket_card(item) for item in items]
        if not items:
            list_host.controls = [
                ft.Container(
                    padding=30,
                    alignment=ft.Alignment.CENTER,
                    content=ft.Text("Ninguém aguardando", color=TEXT, weight=ft.FontWeight.BOLD),
                )
            ]

    async def refresh():
        try:
            items = await asyncio.to_thread(db.list_tickets, date.today())
            cache["items"] = [item for item in items if item.get("status") in ("W", "C")]
            open_triages.value = str(len(cache["items"]))
            for queue in QUEUE_INFO:
                counts[queue].value = str(
                    sum(1 for item in cache["items"] if str(item.get("fila") or "N").upper() == queue)
                )
            render_current()
            update_text.value = "Atualizado agora"
            page.update()
        except Exception as ex:
            update_text.value = f"Erro: {ex}"
            page.update()

    tab_controls = []
    for queue, (label, icon, background, accent) in QUEUE_INFO.items():
        short_label = {"N": "Normal", "P": "Prefer.", "E": "Espera", "A": "Ausente"}[queue]
        tab = ft.Container(
            expand=True,
            height=70,
            ink=True,
            on_click=lambda e, q=queue: select_queue(q),
            padding=ft.padding.symmetric(horizontal=2, vertical=6),
            content=ft.Column(
                [
                    ft.Icon(icon, size=23, color=accent),
                    ft.Row(
                        [
                            ft.Text(short_label, size=10, color=TEXT, weight=ft.FontWeight.BOLD),
                            ft.Container(
                                width=20,
                                height=20,
                                alignment=ft.Alignment.CENTER,
                                border_radius=10,
                                bgcolor=accent,
                                content=ft.Text(
                                    counts[queue].value,
                                    color=ft.Colors.WHITE,
                                    size=10,
                                    weight=ft.FontWeight.BOLD,
                                ),
                            ),
                        ],
                        spacing=3,
                        alignment=ft.MainAxisAlignment.CENTER,
                    ),
                ],
                spacing=2,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                alignment=ft.MainAxisAlignment.CENTER,
            ),
        )
        # Keep the live counter control inside the badge.
        tab.content.controls[1].controls[1].content = counts[queue]
        tabs[queue] = tab
        tab_controls.append(tab)

    select_queue("P")

    open_triages_badge = ft.Container(
        tooltip="Total de triagens ainda abertas",
        bgcolor="#6E3F74",
        border_radius=10,
        padding=ft.padding.symmetric(horizontal=8, vertical=5),
        content=ft.Row(
            [
                ft.Text(
                    "Abertas",
                    size=10,
                    color=ft.Colors.WHITE,
                    weight=ft.FontWeight.BOLD,
                ),
                open_triages,
            ],
            spacing=5,
            tight=True,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
    )

    root = ft.Column(
        [
            _header(page, "Chamar consulentes", "/", open_triages_badge),
            ft.Container(
                bgcolor=HEADER,
                padding=ft.padding.only(left=12, right=12, bottom=8),
                content=ft.Row(
                    [
                        ft.Container(content=update_text, expand=True),
                        ft.Row(
                            [
                                ft.TextButton(
                                    "Novo",
                                    icon=ft.Icons.PERSON_ADD_ALT_1,
                                    style=ft.ButtonStyle(color=ft.Colors.WHITE),
                                    on_click=lambda e: page.go("/celular/cadastro"),
                                ),
                                ft.TextButton(
                                    "Finalizar",
                                    icon=ft.Icons.FLAG,
                                    style=ft.ButtonStyle(color=ft.Colors.WHITE),
                                    on_click=lambda e: page.run_task(show_closure),
                                ),
                                ft.IconButton(
                                    icon=ft.Icons.REFRESH,
                                    icon_color=ft.Colors.WHITE,
                                    tooltip="Atualizar",
                                    on_click=lambda e: page.run_task(refresh),
                                ),
                            ],
                            spacing=0,
                        ),
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                ),
            ),
            ft.Row(tab_controls, spacing=0),
            ft.Container(padding=12, content=ft.Column(
                [list_host], scroll=ft.ScrollMode.AUTO, expand=True,
            ), expand=True),
            ft.SafeArea(content=ft.Container(
                padding=12, bgcolor=ft.Colors.WHITE,
                content=ft.Column([
                    next_button,
                    ft.OutlinedButton(
                        "Adicionar à espera", icon=ft.Icons.PERSON_ADD_ALT_1,
                        height=52, on_click=add_waiting,
                    ),
                ], spacing=8, tight=True, horizontal_alignment=ft.CrossAxisAlignment.STRETCH),
            )),
        ],
        spacing=0,
        expand=True,
    )

    async def auto_refresh():
        while state["active"] and route_is_active():
            if not state["busy"]:
                await refresh()
            await asyncio.sleep(3)

    async def bootstrap():
        page.run_task(auto_refresh)

    view = ft.View(
        route=(page.route or "/celular").split("?", 1)[0],
        padding=0,
        controls=[root],
        bgcolor=BG,
    )
    view.data = {"bootstrap": bootstrap}
    return view
