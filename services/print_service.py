# services/print_service.py
from __future__ import annotations

import os
import json
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Dict, List, Optional

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import Table, TableStyle
from reportlab.lib.utils import ImageReader

import qrcode

# A6 (105 x 148 mm)
A6 = (105 * mm, 148 * mm)


@dataclass
class PrintConfig:
    logo_path: str = "assets/logopb.jpg"
    output_dir: str = "outputs"


class PrintService:
    def __init__(self, cfg: Optional[PrintConfig] = None):
        self.cfg = cfg or PrintConfig()
        os.makedirs(self.cfg.output_dir, exist_ok=True)

    # =========================================================
    # Helpers
    # =========================================================
    def _draw_header(self, c: Canvas, titulo: str, subtitulo: str, centro_nome: str):
        w, h = A4
        m = 12 * mm

        if os.path.exists(self.cfg.logo_path):
            try:
                img = ImageReader(self.cfg.logo_path)
                c.drawImage(
                    img,
                    m,
                    h - 25 * mm,
                    width=20 * mm,
                    height=20 * mm,
                    preserveAspectRatio=True,
                    mask="auto",
                )
            except Exception:
                pass

        c.setFillColor(colors.black)
        c.setFont("Helvetica-Bold", 15)
        c.drawString(m + 24 * mm, h - 14 * mm, centro_nome)

        c.setFont("Helvetica-Bold", 12)
        c.drawString(m + 24 * mm, h - 22 * mm, titulo)

        c.setFont("Helvetica", 10)
        c.setFillColor(colors.grey)
        c.drawString(m + 24 * mm, h - 28 * mm, subtitulo)

        c.setStrokeColor(colors.lightgrey)
        c.setLineWidth(1)
        c.line(m, h - 32 * mm, w - m, h - 32 * mm)

        return m, w, h

    def _fila_nome(self, f: str) -> str:
        return {
            "N": "Normal",
            "P": "Preferencial",
            "E": "Espera",
            "A": "Não apareceu",
        }.get(f, str(f))

    def _fila_ord(self, f: str) -> int:
        return {"P": 0, "N": 1, "E": 2, "A": 3}.get(f, 9)

    # =========================================================
    # A6 - Senha (ATUALIZADO)
    # - Logo centralizado e maior
    # - Senha maior (prioridade)
    # =========================================================

    def _parse_notes_dict(self, notes: Any) -> Dict[str, Any]:
        if notes is None:
            return {}
        if isinstance(notes, dict):
            return dict(notes)
        if isinstance(notes, str):
            s = notes.strip()
            if not s:
                return {}
            try:
                obj = json.loads(s)
                return obj if isinstance(obj, dict) else {}
            except Exception:
                return {}
        return {}

    def _get_acompanhantes(self, ticket: Dict[str, Any]) -> int:
        if "acompanhantes" in ticket:
            try:
                n = int(ticket.get("acompanhantes") or 0)
                return n if n in (0, 1, 2) else 0
            except Exception:
                return 0
        notes = self._parse_notes_dict(ticket.get("notes"))
        try:
            n = int(notes.get("acompanhantes", 0) or 0)
            return n if n in (0, 1, 2) else 0
        except Exception:
            return 0

    def _nome_com_acompanhantes(self, ticket: Dict[str, Any]) -> str:
        nome = (ticket.get("nome_livre") or "").strip()
        acomp = self._get_acompanhantes(ticket)
        return f"{nome} +{acomp}" if acomp > 0 else nome

    def gerar_senha_a6_pdf(
        self,
        ticket: Dict[str, Any],
        work_date: date,
        centro_nome: str = "Casa da Vovó Joaquina",
        incluir_qr: bool = False,
        qr_text: str = "@casavovojoaquina",
    ) -> str:
        senha = str(ticket.get("senha", "—"))
        nome = (ticket.get("nome_livre") or "").strip()
        fila = (ticket.get("fila") or "").upper().strip()

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        fname = f"senha_{senha.replace('/', '-')}_{ts}.pdf"
        path = os.path.join(self.cfg.output_dir, fname)

        c = Canvas(path, pagesize=A6)
        w, h = A6
        m = 7 * mm

        # ---- Logo centralizado (maior)
        top_y = h - m
        if os.path.exists(self.cfg.logo_path):
            try:
                img = ImageReader(self.cfg.logo_path)
                logo_w = 34 * mm
                logo_h = 34 * mm
                c.drawImage(
                    img,
                    (w - logo_w) / 2,
                    top_y - logo_h,
                    width=logo_w,
                    height=logo_h,
                    preserveAspectRatio=True,
                    mask="auto",
                )
            except Exception:
                pass

        # ---- Nome do centro abaixo do logo
        y = h - m - 36 * mm
        c.setFillColor(colors.black)
        c.setFont("Helvetica-Bold", 12)
        c.drawCentredString(w / 2, y, centro_nome)

        # ---- Data / fila
        y -= 6 * mm
        c.setFont("Helvetica", 9)
        c.setFillColor(colors.grey)
        c.drawCentredString(
            w / 2,
            y,
            f"Dia: {work_date.strftime('%d/%m/%Y')}  •  Fila: {self._fila_nome(fila)}",
        )

        # ---- Caixa da senha (bem maior)
        box_y = y - 38 * mm
        box_h = 34 * mm
        c.setFillColor(colors.whitesmoke)
        c.roundRect(m, box_y, w - 2 * m, box_h, 10, stroke=0, fill=1)

        c.setFillColor(colors.black)
        c.setFont("Helvetica-Bold", 42)  # maior que antes
        c.drawCentredString(w / 2, box_y + 10 * mm, senha)

        # ---- Consulente
        y2 = box_y - 8 * mm
        c.setFillColor(colors.black)
        c.setFont("Helvetica-Bold", 10)
        c.drawString(m, y2, "Consulente  :")
        c.setFont("Helvetica", 10)
        # quebra simples (1 linha)
        nome_show = nome if nome else "—"
        if len(nome_show) > 40:
            nome_show = nome_show[:40] + "…"
        c.drawString(m + 25 * mm, y2, nome_show.upper())

        # ---- QR (opcional) canto inferior direito
        if incluir_qr:
            if not qr_text:
                qr_text = f"SENHA={senha};DATA={work_date.isoformat()};FILA={fila}"
            try:
                qr_img = qrcode.make(qr_text).convert("RGB")
                qr_path = os.path.join(self.cfg.output_dir, f"qr_{senha}_{ts}.png")
                qr_img.save(qr_path)
                qr_reader = ImageReader(qr_path)
                qr_size = 24 * mm
                c.drawImage(
                    qr_reader,
                    w - m - qr_size,
                    m,
                    width=qr_size,
                    height=qr_size,
                    mask="auto",
                )
                try:
                    os.remove(qr_path)
                except Exception:
                    pass
            except Exception:
                pass

        # Rodapé
        c.setFont("Helvetica", 7.5)
        c.setFillColor(colors.grey)
        c.drawString(m, m, "Gerado pelo Sistema de Filas")

        c.showPage()
        c.save()
        return path

    # =========================================================
    # Relatório 1: Lista de Chamada (backup físico)
    # =========================================================
    def gerar_lista_chamada_por_fila_pdf(
        self,
        work_date: date,
        tickets: List[Dict[str, Any]],
        centro_nome: str = "Casa da Vovó Joaquina",
        titulo_gira: str = "Lista de Chamada (Backup Físico)",
        incluir_status: Optional[set[str]] = None,
    ) -> str:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        fname = f"lista_chamada_{work_date.strftime('%Y%m%d')}_{ts}.pdf"
        path = os.path.join(self.cfg.output_dir, fname)

        # Por padrão, a lista backup só imprime tickets ativos
        if incluir_status is None:
            incluir_status = {"W", "C"}

        tickets = [
            t for t in tickets if (t.get("status") or "").upper() in incluir_status
        ]

        by = {"N": [], "P": [], "E": [], "A": []}
        for t in tickets:
            f = (t.get("fila") or "N").upper()
            if f not in by:
                f = "N"
            by[f].append(t)

        for f in by:
            by[f].sort(key=lambda x: int(x.get("seq", 0)))

        c = Canvas(path, pagesize=A4)

        for fila in ("P", "N", "E", "A"):
            fila_nome = self._fila_nome(fila)
            sub = f"Dia {work_date.strftime('%d/%m/%Y')} — Fila: {fila_nome}"
            m, w, h = self._draw_header(c, titulo_gira, sub, centro_nome)

            rows = [["Senha", "Nome do consulente"]]
            for t in by[fila]:
                rows.append([t.get("senha", ""), self._nome_com_acompanhantes(t)[:80]])

            if len(rows) == 1:
                rows.append(["—", "— (sem registros nesta fila) —"])

            table = Table(rows, colWidths=[30 * mm, (w - 2 * m) - 30 * mm])
            table.setStyle(
                TableStyle(
                    [
                        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                        ("FONTSIZE", (0, 0), (-1, 0), 10),
                        ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
                        ("ALIGN", (0, 0), (-1, 0), "CENTER"),
                        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                        ("FONTSIZE", (0, 1), (-1, -1), 9),
                        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                        (
                            "ROWBACKGROUNDS",
                            (0, 1),
                            (-1, -1),
                            [colors.whitesmoke, colors.white],
                        ),
                        ("LEFTPADDING", (0, 0), (-1, -1), 6),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                        ("TOPPADDING", (0, 0), (-1, -1), 4),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                    ]
                )
            )

            available_w = w - 2 * m
            x = m
            y_top = h - 40 * mm
            tw, th = table.wrap(available_w, h)
            table.drawOn(c, x, y_top - th)

            c.setFont("Helvetica", 8)
            c.setFillColor(colors.grey)
            c.drawString(
                m, 10 * mm, f"Gerado em {datetime.now().strftime('%d/%m/%Y %H:%M')}"
            )
            c.showPage()

        c.save()
        return path

    # =========================================================
    # Relatório 2: Fechamento da Gira
    # =========================================================
    def gerar_fechamento_gira_pdf(
        self,
        work_date: date,
        tickets: List[Dict[str, Any]],
        centro_nome: str = "Casa da Vovó Joaquina",
        titulo: str = "Fechamento da Gira",
        concluidos_status: Optional[set[str]] = None,
    ) -> str:
        if concluidos_status is None:
            concluidos_status = {"F", "D"}

        concl = [t for t in tickets if (t.get("status") in concluidos_status)]

        counts = {"N": 0, "P": 0, "E": 0, "A": 0}
        for t in concl:
            f = (t.get("fila") or "N").upper()
            if f not in counts:
                f = "N"
            counts[f] += 1

        total = counts["N"] + counts["P"] + counts["E"]
        total_acompanhantes = sum(
            self._get_acompanhantes(t)
            for t in concl
            if (t.get("fila") or "").upper() != "A"
        )
        total_pessoas = total + total_acompanhantes

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        fname = f"fechamento_gira_{work_date.strftime('%Y%m%d')}_{ts}.pdf"
        path = os.path.join(self.cfg.output_dir, fname)

        c = Canvas(path, pagesize=A4)
        sub = f"Dia {work_date.strftime('%d/%m/%Y')} - Concluídos"
        m, w, h = self._draw_header(c, titulo, sub, centro_nome)

        box_w = w - 2 * m
        box_h = 78 * mm
        box_y = h - 122 * mm

        c.setFillColor(colors.whitesmoke)
        c.roundRect(m, box_y, box_w, box_h, 8, stroke=0, fill=1)

        c.setFont("Helvetica-Bold", 13)
        c.setFillColor(colors.black)
        c.drawString(m + 10 * mm, box_y + box_h - 12 * mm, "Resumo de Atendimentos")

        card_w = 40 * mm
        card_h = 22 * mm
        gap = 5 * mm

        def fila_card_color(fila: str):
            return {
                "N": colors.HexColor("#DBEAFE"),
                "P": colors.HexColor("#FEF3C7"),
                "E": colors.HexColor("#F3E8FF"),
                "A": colors.HexColor("#FEE2E2"),
            }.get(fila, colors.whitesmoke)

        def fila_text_color(fila: str):
            return {
                "N": colors.HexColor("#1E3A8A"),
                "P": colors.HexColor("#78350F"),
                "E": colors.HexColor("#581C87"),
                "A": colors.HexColor("#7F1D1D"),
            }.get(fila, colors.black)

        def draw_card(x, y, title, value, fila):
            c.setFillColor(fila_card_color(fila))
            c.roundRect(x, y, card_w, card_h, 6, stroke=0, fill=1)

            c.setFillColor(fila_text_color(fila))
            c.setFont("Helvetica-Bold", 16)
            c.drawCentredString(x + card_w / 2, y + 9 * mm, str(value))

            c.setFont("Helvetica-Bold", 8)
            c.drawCentredString(x + card_w / 2, y + 4 * mm, title)

        start_x = m + 10 * mm
        y_cards = box_y + box_h - 42 * mm

        draw_card(start_x + (card_w + gap) * 0, y_cards, "Normal", counts["N"], "N")
        draw_card(
            start_x + (card_w + gap) * 1,
            y_cards,
            "Preferencial",
            counts["P"],
            "P",
        )
        draw_card(start_x + (card_w + gap) * 2, y_cards, "Espera", counts["E"], "E")
        draw_card(
            start_x + (card_w + gap) * 3,
            y_cards,
            "Não apareceu",
            counts["A"],
            "A",
        )

        total_y = box_y + 16 * mm

        c.setFillColor(colors.black)
        c.setFont("Helvetica-Bold", 16)
        c.drawString(m + 10 * mm, total_y, f"TOTAL: {total_pessoas}")

        c.setFont("Helvetica", 12)
        c.drawString(m + 75 * mm, total_y, f"Consulentes: {total}")
        c.drawString(m + 130 * mm, total_y, f"Acompanhantes: {total_acompanhantes}")

        c.setFont("Helvetica", 8)
        c.setFillColor(colors.grey)
        c.drawString(
            m, 10 * mm, f"Gerado em {datetime.now().strftime('%d/%m/%Y %H:%M')}"
        )

        c.showPage()
        c.save()
        return path
