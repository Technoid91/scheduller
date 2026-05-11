import calendar
import os
import tempfile
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

_BASE = os.path.join(os.path.dirname(__file__), "fonts")
pdfmetrics.registerFont(TTFont("DVSans",      os.path.join(_BASE, "DejaVuSans.ttf")))
pdfmetrics.registerFont(TTFont("DVSans-Bold", os.path.join(_BASE, "DejaVuSans-Bold.ttf")))

COL_ROW_ODD     = colors.HexColor("#f5f5f8")
COL_ROW_EVEN    = colors.white
COL_GRID        = colors.HexColor("#bbbbbb")
COL_TEXT        = colors.HexColor("#111111")


def generate_pdf(year: int, month: int, schedule: dict) -> str:
    pdf_path = os.path.join(tempfile.gettempdir(), f"duty_{year}_{month:02d}.pdf")

    page_w, page_h = A4
    margin_x      = 20 * mm
    margin_top    = 18 * mm
    margin_bottom = 12 * mm

    num_days = calendar.monthrange(year, month)[1]

    title_h   = 12 * mm
    title_gap = 4  * mm
    header_h  = 8  * mm

    usable_h  = page_h - margin_top - margin_bottom - title_h - title_gap - header_h
    row_h     = usable_h / 31

    table_w   = page_w - 2 * margin_x
    col_w     = table_w / 3

    table_x    = margin_x
    title_y    = page_h - margin_top - title_h
    header_y   = title_y - title_gap - header_h
    rows_start = header_y

    c = rl_canvas.Canvas(pdf_path, pagesize=A4)

    # Title
    c.setFont("DVSans-Bold", 16)
    c.setFillColor(COL_TEXT)
    c.drawCentredString(page_w / 2, title_y + 3*mm, "ГРАФІК ЧЕРГУВАНЬ")

    # Column headers — no background fill, black bold caps text, border only
    c.setStrokeColor(COL_GRID)
    c.setLineWidth(0.5)
    c.rect(table_x, header_y, table_w, header_h, fill=0, stroke=1)
    # inner vertical dividers for header
    c.line(table_x + col_w,     header_y, table_x + col_w,     header_y + header_h)
    c.line(table_x + col_w * 2, header_y, table_x + col_w * 2, header_y + header_h)

    c.setFillColor(COL_TEXT)
    c.setFont("DVSans-Bold", 9)
    hy = header_y + header_h * 0.3
    c.drawCentredString(table_x + col_w * 0.5, hy, "ДАТА")
    c.drawCentredString(table_x + col_w * 1.5, hy, "КІМНАТА")
    c.drawCentredString(table_x + col_w * 2.5, hy, "ПІДПИС")

    # Data rows
    for day in range(1, num_days + 1):
        row_y = rows_start - day * row_h

        c.setFillColor(COL_ROW_ODD if day % 2 == 1 else COL_ROW_EVEN)
        c.rect(table_x, row_y, table_w, row_h, fill=1, stroke=0)

        c.setStrokeColor(COL_GRID)
        c.setLineWidth(0.3)
        c.line(table_x,              row_y, table_x + table_w,  row_y)
        c.line(table_x,              row_y, table_x,             row_y + row_h)
        c.line(table_x + col_w,      row_y, table_x + col_w,    row_y + row_h)
        c.line(table_x + col_w * 2,  row_y, table_x + col_w*2,  row_y + row_h)
        c.line(table_x + table_w,    row_y, table_x + table_w,  row_y + row_h)

        font_size = min(row_h * 0.45, 11)
        text_y    = row_y + row_h * 0.28

        c.setFillColor(COL_TEXT)
        c.setFont("DVSans-Bold", font_size)
        c.drawCentredString(table_x + col_w * 0.5, text_y, f"{day:02d}.{month:02d}")
        c.setFont("DVSans", font_size)
        c.drawCentredString(table_x + col_w * 1.5, text_y, str(schedule.get(day, "—")))

    # Bottom border
    c.setStrokeColor(COL_GRID)
    c.setLineWidth(0.3)
    c.line(table_x, rows_start - num_days * row_h, table_x + table_w, rows_start - num_days * row_h)

    c.save()
    return pdf_path
