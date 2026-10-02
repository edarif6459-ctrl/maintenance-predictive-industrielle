"""Génération des rapports (PDF, Excel) et des QR codes."""
import io
from datetime import datetime

import pandas as pd


def build_excel(sheets):
    """sheets : dict nom -> DataFrame. Retourne les octets d'un .xlsx."""
    bio = io.BytesIO()
    with pd.ExcelWriter(bio, engine="openpyxl") as xw:
        for name, df in sheets.items():
            name = str(name)[:31]
            df.to_excel(xw, sheet_name=name, index=False)
            ws = xw.sheets[name]
            for i, col in enumerate(df.columns, 1):
                w = max([len(str(col))] + [len(str(v)) for v in df[col].head(200)]) + 2
                ws.column_dimensions[ws.cell(1, i).column_letter].width = min(w, 45)
            ws.freeze_panes = "A2"
    return bio.getvalue()


def build_pdf(title, subtitle, kpis, table_title, header, rows, risk_col=None, footer=""):
    """PDF A4 : titre, KPI, tableau. risk_col = index de la colonne score (colore la ligne)."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import cm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    ink, copper = colors.HexColor("#0E1B24"), colors.HexColor("#E8833A")
    ss = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=ss["Title"], textColor=ink, fontSize=22, alignment=0, spaceAfter=2)
    sub = ParagraphStyle("sub", parent=ss["Normal"], textColor=colors.HexColor("#5b6f7a"), fontSize=10)
    h2 = ParagraphStyle("h2", parent=ss["Heading2"], textColor=ink, spaceBefore=14)
    cell = ParagraphStyle("cell", parent=ss["Normal"], fontSize=8, leading=10)

    bio = io.BytesIO()
    doc = SimpleDocTemplate(bio, pagesize=A4, leftMargin=1.5 * cm, rightMargin=1.5 * cm,
                            topMargin=1.5 * cm, bottomMargin=1.5 * cm, title=title)
    story = [Paragraph(title, h1), Paragraph(subtitle, sub), Spacer(1, 10)]

    k = Table([[Paragraph(f"<font size=8 color='#5b6f7a'>{lab}</font><br/><font size=15><b>{val}</b></font>", ss["Normal"])
                for lab, val in kpis[i:i + 3]] for i in range(0, len(kpis), 3)], colWidths=[6 * cm] * 3)
    k.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), .5, colors.HexColor("#dde5e9")),
                           ("INNERGRID", (0, 0), (-1, -1), .5, colors.HexColor("#dde5e9")),
                           ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F3F6F8")),
                           ("TOPPADDING", (0, 0), (-1, -1), 8), ("BOTTOMPADDING", (0, 0), (-1, -1), 8)]))
    story += [k, Paragraph(table_title, h2)]

    body = [[Paragraph(str(c), cell) for c in r] for r in rows]
    t = Table([[Paragraph(f"<b>{h}</b>", cell) for h in header]] + body, repeatRows=1)
    style = [("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#dfe8ec")),
             ("GRID", (0, 0), (-1, -1), .25, colors.HexColor("#c5d1d7")),
             ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LINEBELOW", (0, 0), (-1, 0), 1.5, copper)]
    if risk_col is not None:
        for i, r in enumerate(rows, 1):
            try:
                v = float(r[risk_col])
            except Exception:
                continue
            bg = "#fde2e3" if v >= 85 else "#fdebd9" if v >= 60 else "#fdf4d9"
            style.append(("BACKGROUND", (0, i), (-1, i), colors.HexColor(bg)))
    t.setStyle(TableStyle(style))
    story += [t, Spacer(1, 12), Paragraph(f"{footer} · {datetime.now():%Y-%m-%d %H:%M}", sub)]
    doc.build(story)
    return bio.getvalue()


def make_qr_png(text):
    """PNG du QR code, ou None si le module 'qrcode' n'est pas installé."""
    try:
        import qrcode
    except ImportError:
        return None
    qr = qrcode.QRCode(box_size=8, border=2)
    qr.add_data(text)
    qr.make(fit=True)
    bio = io.BytesIO()
    qr.make_image(fill_color="black", back_color="white").save(bio, format="PNG")
    return bio.getvalue()


def qr_sheet_pdf(items, title):
    """Planche d'étiquettes QR à imprimer (3 x 4 par page). items : [(id, url)]."""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import cm
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas

    bio = io.BytesIO()
    c = canvas.Canvas(bio, pagesize=A4)
    w, h = A4
    cw, ch, per_page = w / 3, (h - 2 * cm) / 4, 12
    for n, (mid, url) in enumerate(items):
        if n % per_page == 0:
            if n:
                c.showPage()
            c.setFont("Helvetica-Bold", 12)
            c.drawString(1.5 * cm, h - 1.2 * cm, title)
        i = n % per_page
        x, y = (i % 3) * cw, h - 2 * cm - (i // 3 + 1) * ch
        png = make_qr_png(url)
        if png is None:
            return None
        c.rect(x + .3 * cm, y + .3 * cm, cw - .6 * cm, ch - .6 * cm)
        side = min(cw, ch) - 2.2 * cm
        c.drawImage(ImageReader(io.BytesIO(png)), x + (cw - side) / 2, y + 1.3 * cm, side, side)
        c.setFont("Helvetica-Bold", 13)
        c.drawCentredString(x + cw / 2, y + .7 * cm, str(mid))
    c.save()
    return bio.getvalue()
