from __future__ import annotations

import io
import re
import base64
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import pandas as pd
import streamlit as st

try:
    import fitz
except Exception:
    fitz = None

try:
    from PIL import Image
except Exception:
    Image = None

try:
    import pytesseract
except Exception:
    pytesseract = None

try:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image as RLImage
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
except Exception:
    colors = None
    A4 = landscape = mm = None
    SimpleDocTemplate = Table = TableStyle = Paragraph = Spacer = RLImage = None
    getSampleStyleSheet = ParagraphStyle = None

st.set_page_config(page_title="Referto comparativo analisi", page_icon="🧪", layout="wide")

VERSIONE_APP = "VERSIONE CORRETTA 2026-06-01: no griglia, asterischi e valori fuori range rossi anche nel PDF."

DOCTOR_BLOCK = """<b>Dr. Danilo Bramard</b><br>
Biologo Nutrizionista<br>
Laurea Magistrale in Biologia applicata alle scienze della nutrizione<br>
Iscritto all'Ordine Nazionale dei Biologi<br>
P.IVA: 03982150041<br>
☎ +393393121941 | ✉ danilo@newbodycenter.it"""

GROUPS = {
    "Emocromo (Sg)": ["WBC-Globuli Bianchi", "RBC-Globuli Rossi", "HGB-Emoglobina", "HCT-Ematocrito", "MCV-Volume Eritrocitario", "MCH-Contenuto Corpuscolare HGB", "MCHC-Concentrazione Corpuscolare Hgb", "RDW-Indice Anisocitosi Eritrocitaria", "PLT-Piastrine", "MPV-Volume Piastrinico"],
    "Metabolismo glucidico": ["Glucosio", "Glicemia", "Insulina", "HbA1c", "HOMA-IR"],
    "Profilo lipidico": ["Colesterolo totale", "Colesterolo HDL", "Colesterolo LDL", "Trigliceridi", "Rapporto TG/HDL"],
    "Fegato / rene / infiammazione": ["Creatinina", "eGFR", "GammaGT", "AST-GOT", "ALT-GPT", "PCR", "VES", "Uricemia"],
    "Assetto marziale / vitamine / tiroide": ["Ferro", "Ferritina", "Transferrina", "Vitamina D", "TSH-R", "FT3", "FT4", "Vitamina B12", "Folati"],
    "Urine": ["Colore urine", "Aspetto urine", "pH urine", "Glucosio urine", "Proteine urine", "Bilirubina urine", "Urobilinogeno urine", "Emoglobina urine", "Corpi chetonici urine", "Leucociti urine", "Nitriti urine", "Peso specifico urine"],
}

ALIASES: Dict[str, str] = {
    "wbc": "WBC-Globuli Bianchi", "globuli bianchi": "WBC-Globuli Bianchi",
    "rbc": "RBC-Globuli Rossi", "globuli rossi": "RBC-Globuli Rossi",
    "hgb": "HGB-Emoglobina", "emoglobina": "HGB-Emoglobina",
    "hct": "HCT-Ematocrito", "ematocrito": "HCT-Ematocrito",
    "mcv": "MCV-Volume Eritrocitario", "mch": "MCH-Contenuto Corpuscolare HGB", "mchc": "MCHC-Concentrazione Corpuscolare Hgb",
    "rdw": "RDW-Indice Anisocitosi Eritrocitaria", "rdw-indice anisocitosi eritrocitaria": "RDW-Indice Anisocitosi Eritrocitaria",
    "plt": "PLT-Piastrine", "piastrine": "PLT-Piastrine", "mpv": "MPV-Volume Piastrinico",
    "glucosio": "Glucosio", "glicemia": "Glicemia", "creatinina": "Creatinina", "egfr": "eGFR",
    "gammagt": "GammaGT", "gamma gt": "GammaGT", "ggt": "GammaGT",
    "ferro": "Ferro", "ferritina": "Ferritina", "colesterolo": "Colesterolo totale", "colesterolo totale": "Colesterolo totale",
    "colesterolo hdl": "Colesterolo HDL", "hdl": "Colesterolo HDL", "colesterolo ldl": "Colesterolo LDL", "ldl": "Colesterolo LDL",
    "trigliceridi": "Trigliceridi", "tsh": "TSH-R", "tsh-r": "TSH-R", "vitamina d": "Vitamina D",
    "colore": "Colore urine", "aspetto": "Aspetto urine", "ph": "pH urine", "proteine": "Proteine urine",
    "bilirubina": "Bilirubina urine", "urobilinogeno": "Urobilinogeno urine", "corpi chetonici": "Corpi chetonici urine",
    "leucociti": "Leucociti urine", "nitriti": "Nitriti urine", "peso specifico": "Peso specifico urine",
}

DEFAULT_REFS = {"Peso specifico urine": "1,005 - 1,030"}

NOTES = {
    "RDW-Indice Anisocitosi Eritrocitaria": "RDW: variabilità dimensionale dei globuli rossi; utile con MCV e ferritina.",
    "Ferro": "Ferro sierico: variabile; leggere con ferritina, transferrina e emocromo.",
    "Ferritina": "Ferritina: deposito di ferro; aumenta anche con infiammazione.",
    "Peso specifico urine": "Peso specifico urinario alto: urine concentrate; valutare idratazione, perdite di liquidi, sudorazione, dieta e quadro clinico.",
    "Glucosio": "Glucosio/glicemia: dipende dal digiuno e dal metabolismo glucidico.",
    "Colesterolo totale": "Colesterolo totale: leggere insieme a HDL, LDL, TG e rischio cardiovascolare.",
    "Colesterolo HDL": "HDL: frazione protettiva; auspicabile più alta.",
    "Trigliceridi": "Trigliceridi: influenzati da dieta, alcol, peso, digiuno e metabolismo glucidico.",
    "TSH-R": "TSH: marker ipofisario della funzione tiroidea; contestualizzare con FT3/FT4 e terapia.",
}

DATE_RE = re.compile(r"\b\d{1,2}[/.\-]\d{1,2}[/.\-]\d{2,4}\b")
NUM_RE = re.compile(r"^[<>]?\s*\d+(?:[\.,]\d+)?")


def clean(s: str) -> str:
    return re.sub(r"\s+", " ", str(s or "").strip())


def norm(s: str) -> str:
    return clean(s).lower().replace("(s)", "").replace("ì", "i").strip(" :-")


def canonical(name: str, urine: bool = False) -> Optional[str]:
    n = norm(name)
    if not n or n in {"esame richiesto", "risultato", "u.m.", "valori di riferimento", "metodica", "siero"}:
        return None
    if urine and n in {"glucosio", "emoglobina"}:
        return {"glucosio": "Glucosio urine", "emoglobina": "Emoglobina urine"}[n]
    if n in ALIASES:
        return ALIASES[n]
    for k, v in ALIASES.items():
        if n.startswith(k) or k in n:
            return v
    return None


def parse_num(x):
    s = clean(x).replace("*", "").replace("<", "").replace(">", "").replace(",", ".")
    m = re.search(r"\d+(?:\.\d+)?", s)
    if not m:
        return clean(x)
    try:
        return float(m.group(0))
    except Exception:
        return clean(x)


def fmt_value(v) -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return ""
    if isinstance(v, (int, float)):
        return f"{v:g}".replace(".", ",")
    return str(v)


def parse_date(text: str, fallback: str) -> str:
    m = re.search(r"\bdel\s+(\d{1,2}[/.\-]\d{1,2}[/.\-]\d{2,4})\b", text[:4000], re.I)
    raw = m.group(1) if m else None
    if not raw:
        dates = DATE_RE.findall(text[:4000])
        raw = dates[0] if dates else fallback
    raw = str(raw).replace("-", "/").replace(".", "/")
    for f in ("%d/%m/%Y", "%d/%m/%y"):
        try:
            return datetime.strptime(raw, f).strftime("%d/%m/%Y")
        except Exception:
            pass
    return raw


def parse_patient(text: str) -> str:
    lines = [clean(x) for x in text.splitlines() if clean(x)]
    for i, line in enumerate(lines):
        if re.search(r"Nr\.?\s*R", line, re.I) and i + 1 < len(lines):
            cand = lines[i + 1]
            if re.match(r"^[A-ZÀ-Ù' ]{5,}$", cand):
                return cand.title()
    return "Esempio"


def ref_nums(ref: str) -> List[float]:
    return [float(x.replace(",", ".")) for x in re.findall(r"\d+(?:[\.,]\d+)?", ref or "")]


def status_from_ref(value, ref: str) -> str:
    if not isinstance(value, (int, float)) or not ref:
        return ""
    r = ref.lower().replace(" ", "")
    nums = ref_nums(ref)
    if not nums:
        return ""
    if "finoa" in r or "<" in r:
        return "ALTO" if value > nums[-1] else "OK"
    if "oltre" in r or ">" in r:
        return "BASSO" if value < nums[0] else "OK"
    if len(nums) >= 2:
        lo, hi = nums[0], nums[-1]
        if value < lo:
            return "BASSO"
        if value > hi:
            return "ALTO"
        return "OK"
    return ""


def make_row(analita, date, value, unit, ref, original, page):
    unit = clean(unit).replace("mg/dl", "mg/dL").replace("µg/dl", "µg/dL").replace("K/µI", "K/µL").replace("M/µI", "M/µL")
    ref = clean(ref).replace("[", "").replace("]", "").replace("(", "").replace(")", "")
    if analita in DEFAULT_REFS and (not ref or ref in {"O· O", "0- 0", "0 - 0"}):
        ref = DEFAULT_REFS[analita]
    stato = status_from_ref(value, ref)
    return {"Analita": analita, "Data": date, "Valore": value, "UM": unit, "Valori di riferimento": ref, "Stato": stato, "Nota": NOTES.get(analita, "Parametro da contestualizzare con quadro clinico, range del laboratorio e terapia."), "Riga originale": f"pag. {page}: {original}"}


def cluster_words(words):
    rows = []
    for w in words:
        x0, y0, x1, y1, txt = w[:5]
        if not clean(txt):
            continue
        for row in rows:
            if abs(row["y"] - y0) <= 3:
                row["items"].append((x0, txt)); row["y"] = (row["y"] + y0) / 2; break
        else:
            rows.append({"y": y0, "items": [(x0, txt)]})
    out = []
    for row in sorted(rows, key=lambda r: r["y"]):
        cols = {"name": [], "value": [], "unit": [], "ref": []}
        for x, txt in sorted(row["items"]):
            if x < 235: cols["name"].append(txt)
            elif x < 330: cols["value"].append(txt)
            elif x < 430: cols["unit"].append(txt)
            else: cols["ref"].append(txt)
        out.append({"y": row["y"], **{k: clean(" ".join(v)) for k, v in cols.items()}})
    return out


def extract_pdf_structured(data: bytes, filename: str):
    if fitz is None:
        st.error("PyMuPDF non installato. Aggiungi pymupdf al requirements.txt")
        return pd.DataFrame(), "", "", ""
    doc = fitz.open(stream=data, filetype="pdf")
    full_text = "\n".join(p.get_text("text") for p in doc)
    date = parse_date(full_text, filename)
    patient = parse_patient(full_text)
    rows = []
    for pno, page in enumerate(doc, start=1):
        pending = []
        urine_mode = False
        for line in cluster_words(page.get_text("words")):
            y, name_txt, val_txt, unit_txt, ref_txt = line["y"], line["name"], line["value"], line["unit"], line["ref"]
            low = norm(name_txt)
            if "urine" in low and "chimico" in low:
                urine_mode = True
            a = canonical(name_txt, urine_mode)
            if a:
                pending.append({"a": a, "name": name_txt, "y": y, "used": False})
            m = re.match(r"^(?P<num>[<>]?\s*\d+(?:[\.,]\d+)?)(?:\s+(?P<extra>.*))?$", val_txt or "")
            if m:
                cand = [p for p in pending if p["y"] <= y + 2 and not p["used"]]
                if cand:
                    chosen = sorted(cand, key=lambda p: abs(y - p["y"]))[0]
                    chosen["used"] = True
                    extra = clean(m.group("extra") or "")
                    unit = clean((extra + " " + unit_txt).strip())
                    rows.append(make_row(chosen["a"], date, parse_num(m.group("num")), unit, ref_txt, chosen["name"], pno))
            elif urine_mode and val_txt and a:
                rows.append(make_row(a, date, val_txt, unit_txt, ref_txt, name_txt, pno))
    df = pd.DataFrame(rows)
    if df.empty:
        return df, full_text, patient, date
    df = df.drop_duplicates(subset=["Analita", "Data"], keep="first")
    return add_derived(df), full_text, patient, date


def add_derived(df: pd.DataFrame) -> pd.DataFrame:
    extra = []
    for date, sub in df.groupby("Data"):
        vals = dict(zip(sub["Analita"], sub["Valore"]))
        tg, hdl = vals.get("Trigliceridi"), vals.get("Colesterolo HDL")
        if isinstance(tg, (int, float)) and isinstance(hdl, (int, float)) and hdl:
            ratio = round(tg / hdl, 2)
            extra.append({"Analita": "Rapporto TG/HDL", "Data": date, "Valore": ratio, "UM": "", "Valori di riferimento": "< 2", "Stato": "ALTO" if ratio > 2 else "OK", "Nota": "Indice metabolico indiretto; cut-off indicativo.", "Riga originale": "calcolo automatico"})
    return pd.concat([df, pd.DataFrame(extra)], ignore_index=True) if extra else df


def extract_image_text(data: bytes) -> str:
    if Image is None or pytesseract is None:
        st.warning("Per immagini/scansioni serve pillow + pytesseract + Tesseract. Su Streamlit Cloud è meglio caricare PDF testuali.")
        return ""
    return pytesseract.image_to_string(Image.open(io.BytesIO(data)), lang="ita+eng")


def process_upload(uploaded):
    data = uploaded.getvalue()
    if uploaded.name.lower().endswith(".pdf"):
        return extract_pdf_structured(data, uploaded.name)
    return pd.DataFrame(), extract_image_text(data), "Esempio", uploaded.name


def is_date_col(c: str) -> bool:
    return bool(re.match(r"\d{2}/\d{2}/\d{4}$", str(c)))


def delta(v1, v2, unit: str) -> str:
    if v1 == "" or v2 == "": return ""
    try:
        d = float(str(v2).replace(",", ".").replace("*", "")) - float(str(v1).replace(",", ".").replace("*", ""))
        return f"{'+' if d > 0 else ''}{d:g} {unit}".strip().replace(".", ",")
    except Exception:
        return ""


def build_report_table(df: pd.DataFrame, dates: List[str]) -> pd.DataFrame:
    dates = list(dates)
    cols = ["_group", "_status", "Esame richiesto", "U.M"] + dates + [f"Diff. {i+1}-{i}" for i in range(1, len(dates))] + ["Valori di Riferimento", "Nota"]
    if df.empty: return pd.DataFrame(columns=cols)
    pivot = df.pivot_table(index="Analita", columns="Data", values="Valore", aggfunc="first")
    meta = df.drop_duplicates("Analita").set_index("Analita")
    out, used = [], set()

    def status(n):
        s = str(meta.loc[n, "Stato"]).upper().strip() if n in meta.index else ""
        return s if s in ["ALTO", "BASSO"] else ""

    def group_row(g):
        r = {c: "" for c in cols}; r["_group"] = True; r["Esame richiesto"] = g; return r

    def value_row(n):
        unit = meta.loc[n, "UM"] if n in meta.index else ""
        stt = status(n)
        r = {c: "" for c in cols}
        r.update({"_group": False, "_status": stt, "Esame richiesto": n, "U.M": unit, "Valori di Riferimento": meta.loc[n, "Valori di riferimento"] if n in meta.index else "", "Nota": f"{stt}. {meta.loc[n, 'Nota']}" if stt else ""})
        vals = []
        for d in dates:
            fv = fmt_value(pivot.loc[n, d] if d in pivot.columns else "")
            if stt and fv: fv = f"* {fv}"
            r[d] = fv; vals.append(fv)
        for i in range(1, len(dates)):
            r[f"Diff. {i+1}-{i}"] = delta(vals[i-1], vals[i], unit)
        return r

    for g, names in GROUPS.items():
        present = [n for n in names if n in pivot.index]
        if present:
            out.append(group_row(g))
            for n in present:
                used.add(n); out.append(value_row(n))
    leftovers = [n for n in pivot.index if n not in used]
    if leftovers:
        out.append(group_row("Altri esami"))
        for n in leftovers: out.append(value_row(n))
    return pd.DataFrame(out, columns=cols)


def visible_cols(df: pd.DataFrame) -> List[str]:
    return [c for c in df.columns if not c.startswith("_")]


def make_pdf(report_df: pd.DataFrame, patient: str, report_date: str, logo_bytes: Optional[bytes]) -> Optional[bytes]:
    if SimpleDocTemplate is None: return None
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4), leftMargin=10*mm, rightMargin=10*mm, topMargin=10*mm, bottomMargin=10*mm)
    styles = getSampleStyleSheet()
    normal = ParagraphStyle("normal_small", parent=styles["Normal"], fontName="Helvetica", fontSize=7, leading=8)
    center = ParagraphStyle("center", parent=normal, alignment=1)
    bold = ParagraphStyle("bold", parent=normal, fontName="Helvetica-Bold")
    italic = ParagraphStyle("italic", parent=center, fontName="Helvetica-Oblique")
    red_center = ParagraphStyle("red_center", parent=center, textColor=colors.HexColor("#b00000"), fontName="Helvetica-Bold")
    red_note = ParagraphStyle("red_note", parent=normal, textColor=colors.HexColor("#b00000"), fontName="Helvetica-Bold")
    doctor = ParagraphStyle("doctor", parent=styles["Normal"], fontSize=8.5, leading=11)
    elems = []
    logo = RLImage(io.BytesIO(logo_bytes), width=52*mm, height=35*mm) if logo_bytes else Paragraph("<b>DB</b><br/>NUTRITION AND PERFORMANCE", styles["Title"])
    header = Table([[logo, Paragraph(DOCTOR_BLOCK.replace("<br>", "<br/>"), doctor), Paragraph(report_date, doctor)]], colWidths=[58*mm, 130*mm, 70*mm])
    header.setStyle(TableStyle([("VALIGN", (0,0), (-1,-1), "TOP"), ("LINEBEFORE", (1,0), (1,0), 1, colors.HexColor("#6aa0ff")), ("LEFTPADDING", (1,0), (1,0), 7), ("ALIGN", (2,0), (2,0), "RIGHT")]))
    elems += [header, Spacer(1, 8*mm), Paragraph(f"<b>Sig. {patient}</b>", styles["Normal"]), Spacer(1, 4*mm)]
    cols = visible_cols(report_df)
    data = [[Paragraph(str(c).replace("Valori di Riferimento", "Valori di<br/>Riferimento"), italic) for c in cols]]
    row_statuses = []
    for _, r in report_df.iterrows():
        is_group, stt = bool(r.get("_group")), str(r.get("_status", "")).upper()
        row_statuses.append((is_group, stt))
        row = []
        for c in cols:
            txt = str(r.get(c, "") or "")
            style = bold if is_group else (red_center if stt in ["ALTO", "BASSO"] and is_date_col(c) else red_note if stt in ["ALTO", "BASSO"] and c == "Nota" else normal if c in ["Esame richiesto", "Nota"] else center)
            row.append(Paragraph(txt, style))
        data.append(row)
    n_dates = max(1, len([c for c in cols if is_date_col(c)])); n_diffs = len([c for c in cols if str(c).startswith("Diff.")])
    widths = [62*mm, 22*mm, 28*mm, 42*mm, 104*mm] if len(cols) <= 5 else [54*mm, 18*mm] + [max(18*mm, min(26*mm, (267*mm-54*mm-18*mm-40*mm-48*mm)/max(1,n_dates+n_diffs)))]*(n_dates+n_diffs) + [40*mm, 48*mm]
    table = Table(data, colWidths=widths, repeatRows=1)
    ts = [("VALIGN", (0,0), (-1,-1), "MIDDLE"), ("ALIGN", (0,0), (-1,0), "CENTER"), ("LINEBELOW", (0,0), (-1,0), 0.4, colors.black), ("FONTSIZE", (0,0), (-1,-1), 7), ("LEFTPADDING", (0,0), (-1,-1), 4), ("RIGHTPADDING", (0,0), (-1,-1), 4), ("TOPPADDING", (0,0), (-1,-1), 2), ("BOTTOMPADDING", (0,0), (-1,-1), 2)]
    for idx, (is_group, stt) in enumerate(row_statuses, start=1):
        if is_group:
            ts += [("SPAN", (0,idx), (-1,idx)), ("BACKGROUND", (0,idx), (-1,idx), colors.HexColor("#f1f1f1")), ("FONTNAME", (0,idx), (-1,idx), "Helvetica-Bold"), ("LINEBELOW", (0,idx), (-1,idx), 0.25, colors.HexColor("#d0d0d0"))]
    table.setStyle(TableStyle(ts))
    elems.append(table); doc.build(elems); buf.seek(0); return buf.read()


def data_url_from_upload(file) -> Optional[str]:
    if not file: return None
    ext = file.name.split(".")[-1].lower(); mime = "image/png" if ext == "png" else "image/jpeg"
    return f"data:{mime};base64," + base64.b64encode(file.getvalue()).decode("ascii")


def report_html(report_df: pd.DataFrame, patient: str, report_date: str, logo_data_url: Optional[str]) -> str:
    logo = f'<img src="{logo_data_url}" class="logo">' if logo_data_url else '<div class="logo-placeholder">DB<br><span>Nutrition and Performance</span></div>'
    cols = visible_cols(report_df); col_count = len(cols); rows = []
    for _, r in report_df.iterrows():
        stt = str(r.get("_status", "")).upper()
        if r.get("_group"):
            rows.append(f'<tr class="group"><td colspan="{col_count}"><b>{r["Esame richiesto"]}</b></td></tr>')
        else:
            cells = []
            for c in cols:
                classes = []
                if c == "Esame richiesto": classes.append("exam")
                if c == "Nota": classes.append("note")
                if stt in ["ALTO", "BASSO"] and is_date_col(c): classes.append("abnormal-value")
                if stt in ["ALTO", "BASSO"] and c == "Nota": classes.append("abnormal-note")
                cells.append(f'<td class="{" ".join(classes)}">{r.get(c, "")}</td>')
            rows.append("<tr>" + "".join(cells) + "</tr>")
    headers = "".join([f'<th>{str(c).replace("Valori di Riferimento", "Valori di<br>Riferimento")}</th>' for c in cols])
    colgroup = "".join([f'<col style="width:{"22%" if c=="Esame richiesto" else "8%" if c=="U.M" else "22%" if c=="Nota" else "13%" if c=="Valori di Riferimento" else "10%"}">' for c in cols])
    return f"""
<style>
.report-sheet {{background:white;color:#000;width:1180px;padding:24px 34px 38px 34px;border:none;font-family:Arial,Helvetica,sans-serif;}}
.header {{display:flex;align-items:flex-start;gap:28px;}}
.logo {{width:224px;max-height:156px;object-fit:contain;}}
.logo-placeholder {{width:224px;height:130px;font-size:70px;font-weight:900;border-bottom:1px solid #9bbcff;line-height:.85;}}
.logo-placeholder span {{font-size:13px;text-transform:uppercase;font-weight:600;}}
.doctor {{border-left:2px solid #6aa0ff;padding-left:10px;font-size:14px;line-height:1.55;max-width:560px;}}
.date {{margin-left:auto;font-size:14px;padding-top:166px;}}
.patient {{margin-top:24px;margin-bottom:14px;font-size:14px;font-weight:700;}}
table.referto {{width:100%;border-collapse:collapse;table-layout:fixed;font-size:12px;}}
table.referto th, table.referto td {{border:none;padding:4px 7px;vertical-align:middle;word-wrap:break-word;}}
table.referto thead th {{font-style:italic;font-weight:400;text-align:center;border-bottom:1px solid #111;}}
table.referto .group td {{background:#f1f1f1;font-weight:700;text-align:left;padding:4px 8px;border-bottom:1px solid #d0d0d0;}}
table.referto td:not(.exam):not(.note) {{text-align:center;}}
.exam {{padding-left:22px!important;}} .note {{font-size:10px;line-height:1.1;}}
.abnormal-value {{color:#b00000;font-weight:700;}} .abnormal-note {{color:#b00000;font-weight:600;}}
</style>
<div class="report-sheet"><div class="header"><div>{logo}</div><div class="doctor">{DOCTOR_BLOCK}</div><div class="date">{report_date}</div></div><div class="patient">Sig. {patient}</div><table class="referto"><colgroup>{colgroup}</colgroup><thead><tr>{headers}</tr></thead><tbody>{''.join(rows)}</tbody></table></div>"""


st.title("Referto comparativo analisi - layout DB")
st.caption(VERSIONE_APP)

with st.sidebar:
    st.header("Dati referto")
    patient_manual = st.text_input("Nome paziente manuale", "")
    report_date = st.text_input("Data referto", datetime.now().strftime("%d/%m/%Y"))
    logo_file = st.file_uploader("Logo DB", type=["png", "jpg", "jpeg"], key="logo")
    st.info("Per Streamlit Cloud metti in requirements.txt: streamlit, pandas, pymupdf, pillow, pytesseract, reportlab")

uploads = st.file_uploader("Carica uno o più PDF testuali del laboratorio", type=["pdf", "png", "jpg", "jpeg"], accept_multiple_files=True)
all_dfs, texts, patient_auto = [], [], "Esempio"
if uploads:
    for up in uploads:
        df, text, patient, date = process_upload(up)
        if patient and patient != "Esempio": patient_auto = patient
        texts.append((up.name, text[:15000]))
        if not df.empty: all_dfs.append(df)

if all_dfs:
    full_df = pd.concat(all_dfs, ignore_index=True)
    dates = sorted(full_df["Data"].dropna().unique().tolist(), key=lambda d: datetime.strptime(d, "%d/%m/%Y") if re.match(r"\d{2}/\d{2}/\d{4}", d) else datetime.now())
    selected = st.multiselect("Date da confrontare", dates, default=dates)
    report_df = build_report_table(full_df, selected)
    patient = patient_manual.strip() or patient_auto
    st.subheader("Anteprima referto")
    st.components.v1.html(report_html(report_df, patient, report_date, data_url_from_upload(logo_file)), height=760, scrolling=True)
    st.download_button("Scarica CSV valori estratti", full_df.to_csv(index=False).encode("utf-8-sig"), "valori_estratti.csv", "text/csv")
    pdf_bytes = make_pdf(report_df, patient, report_date, logo_file.getvalue() if logo_file else None)
    if pdf_bytes is None:
        st.error("PDF non generato: ReportLab non installato. Aggiungi reportlab al requirements.txt e riavvia l’app.")
    else:
        st.download_button("Scarica PDF impaginato", pdf_bytes, "referto_comparativo.pdf", "application/pdf")
    st.subheader("Valori estratti")
    display_df = full_df.copy()
    display_df["Nota"] = display_df.apply(lambda r: r["Nota"] if str(r.get("Stato", "")).upper() in ["ALTO", "BASSO"] else "", axis=1)
    display_df["Valore"] = display_df.apply(lambda r: f"* {fmt_value(r['Valore'])}" if str(r.get("Stato", "")).upper() in ["ALTO", "BASSO"] else fmt_value(r["Valore"]), axis=1)
    def evidenzia_fuori_range(row):
        return ["color:#b00000;font-weight:700;" for _ in row] if str(row.get("Stato", "")).upper() in ["ALTO", "BASSO"] else ["" for _ in row]
    st.dataframe(display_df.style.apply(evidenzia_fuori_range, axis=1), use_container_width=True, hide_index=True)
    with st.expander("Tabella modificabile / controllo dati"):
        edited = st.data_editor(full_df, use_container_width=True, num_rows="dynamic", hide_index=True)
        if st.button("Rigenera anteprima con tabella modificata"):
            report_df = build_report_table(edited, selected)
            st.components.v1.html(report_html(report_df, patient, report_date, data_url_from_upload(logo_file)), height=760, scrolling=True)
    with st.expander("Testo letto dai referti"):
        for name, txt in texts:
            st.markdown(f"### {name}"); st.text(txt)
else:
    st.warning("Carica almeno un PDF testuale. Per scansioni/foto serve OCR, ma il risultato va sempre controllato.")
