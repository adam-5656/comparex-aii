"""PDF report export."""
from io import BytesIO
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

def make_pdf(products: list[dict], scores: list[dict], review_summaries: dict, verdict: str) -> bytes:
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=42, leftMargin=42, topMargin=44, bottomMargin=42)
    styles = getSampleStyleSheet()
    story = [Paragraph("CompareX AI — Product Comparison", styles["Title"]), Spacer(1, 12), Paragraph(verdict.replace("**", ""), styles["BodyText"]), Spacer(1, 16)]
    headers = ["Product", "Price (INR)", "Score"]
    rows = [headers] + [[p["name"], f"₹{p.get('price', 0):,.0f}", f"{next((s['score'] for s in scores if s['name']==p['name']), 0):.1f}/100"] for p in products]
    table = Table(rows, repeatRows=1, hAlign="LEFT")
    table.setStyle(TableStyle([("BACKGROUND", (0,0), (-1,0), colors.HexColor("#13253f")), ("TEXTCOLOR", (0,0), (-1,0), colors.white), ("GRID",(0,0),(-1,-1),.4,colors.HexColor("#ccd5e1")), ("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.white,colors.HexColor("#f2f6fa")]), ("PADDING",(0,0),(-1,-1),8)]))
    story += [table, Spacer(1, 14), Paragraph("Specifications", styles["Heading2"])]
    keys = sorted({k for p in products for k in p.get("specs", {})})
    detail_rows = [["Specification"] + [p["name"] for p in products]]
    for key in keys:
        detail_rows.append([key.replace("_", " ").title()] + [str(p.get("specs", {}).get(key, "—")) for p in products])
    if keys:
        detail = Table(detail_rows, repeatRows=1, hAlign="LEFT")
        detail.setStyle(TableStyle([("BACKGROUND", (0,0), (-1,0), colors.HexColor("#13253f")), ("TEXTCOLOR",(0,0),(-1,0),colors.white), ("GRID",(0,0),(-1,-1),.3,colors.grey), ("FONTSIZE",(0,0),(-1,-1),8), ("PADDING",(0,0),(-1,-1),5)]))
        story.extend([detail, Spacer(1, 14)])
    story.append(Paragraph("Review summary", styles["Heading2"]))
    for name, summary in review_summaries.items():
        story.append(Paragraph(f"{name}: {summary['sentiment']} sentiment; {summary.get('positive_pct', 0)}% positive reviews. Themes: {', '.join(summary.get('themes', {}).keys()) or 'none detected'}.", styles["BodyText"]))
    story += [Spacer(1, 12), Paragraph("Prices and specifications may change. Confirm details with the retailer. Scores are relative to the products included in this report.", styles["Italic"])]
    doc.build(story)
    return buffer.getvalue()
