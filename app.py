from __future__ import annotations

import io
import re
from datetime import datetime
from typing import Dict, List, Optional

import pandas as pd
import streamlit as st
from rapidfuzz import process, fuzz

try:
    import fitz  # PyMuPDF
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
    from reportlab.lib.enums import TA_CENTER, TA_LEFT
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import cm
    from reportlab.platypus import Image as RLImage
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
except Exception:
    colors = None

st.set_page_config(page_title="Referto comparativo analisi", page_icon="🧪", layout="wide")

APP_CSS = """
<style>
.block-container {max-width: 1400px; padding-top: 1.5rem; padding-bottom: 3rem;}
.main-title {font-size: 2.15rem; font-weight: 800; color: #111827; margin-bottom: .15rem;}
.sub {color:#667085; margin-bottom:1.2rem;}
.card {border:1px solid #e5e7eb; border-radius:16px; padding:1rem; background:#ffffff;}
.warn {border:1px solid #f1d48a; background:#fff8e6; color:#7a5200; border-radius:12px; padding:.8rem 1rem;}
</style>
"""
st.markdown(APP_CSS, unsafe_allow_html=True)

DEFAULT_RANGES = pd.DataFrame([
    # Emocromo
    ["WBC-Globuli Bianchi", "wbc|globuli bianchi|leucociti|white blood cells", "10^3/uL", 4.0, 10.0, "ALL", "Leucociti: cellule immunitarie; aumento/riduzione va interpretato con formula leucocitaria e clinica."],
    ["RBC-Globuli Rossi", "rbc|globuli rossi|eritrociti|red blood cells", "10^6/uL", 4.2, 5.8, "ALL", "Eritrociti: trasportano emoglobina; utili con Hb, HCT e indici eritrocitari."],
    ["HGB-Emoglobina", "hgb|hb|emoglobina|hemoglobin", "g/dL", 13.0, 17.5, "M", "Emoglobina: proteina che trasporta ossigeno; bassa suggerisce possibile anemia da contestualizzare."],
    ["HGB-Emoglobina", "hgb|hb|emoglobina|hemoglobin", "g/dL", 12.0, 16.0, "F", "Emoglobina: proteina che trasporta ossigeno; bassa suggerisce possibile anemia da contestualizzare."],
    ["HCT-Ematocrito", "hct|ematocrito|hematocrit", "%", 40.0, 52.0, "M", "Ematocrito: quota percentuale di volume occupata dai globuli rossi."],
    ["HCT-Ematocrito", "hct|ematocrito|hematocrit", "%", 36.0, 48.0, "F", "Ematocrito: quota percentuale di volume occupata dai globuli rossi."],
    ["MCV", "mcv|volume corpuscolare medio", "fL", 80, 100, "ALL", "MCV: dimensione media dei globuli rossi; utile nella classificazione delle anemie."],
    ["MCH", "mch|contenuto emoglobinico medio", "pg", 27, 33, "ALL", "MCH: contenuto medio di emoglobina per globulo rosso."],
    ["PLT-Piastrine", "plt|piastrine|platelets", "10^3/uL", 150, 450, "ALL", "Piastrine: coinvolte nella coagulazione; interpretare con anamnesi e farmaci."],
    # Metabolismo glucidico
    ["Glicemia", "glicemia|glucosio|glucose", "mg/dL", 70, 99, "ALL", "Glicemia: glucosio ematico; il digiuno e la terapia influenzano l'interpretazione."],
    ["HbA1c", "hba1c|emoglobina glicata|glicata", "%", 4.0, 5.6, "ALL", "HbA1c: stima dell'esposizione media al glucosio negli ultimi 2-3 mesi."],
    ["Insulina", "insulina|insulin", "uU/mL", 2, 15, "ALL", "Insulina: ormone pancreatico; utile con glicemia per stimare HOMA-IR."],
    # Lipidi
    ["Colesterolo totale", "colesterolo totale|cholesterol total|totale colesterolo", "mg/dL", 0, 200, "ALL", "Colesterolo totale: va letto insieme a LDL, HDL, trigliceridi e rischio cardiovascolare globale."],
    ["LDL", "ldl|colesterolo ldl", "mg/dL", 0, 116, "ALL", "LDL: frazione aterogena; target dipendente dal rischio cardiovascolare individuale."],
    ["HDL", "hdl|colesterolo hdl", "mg/dL", 40, 999, "M", "HDL: frazione protettiva; valori bassi peggiorano il profilo cardiometabolico."],
    ["HDL", "hdl|colesterolo hdl", "mg/dL", 50, 999, "F", "HDL: frazione protettiva; valori bassi peggiorano il profilo cardiometabolico."],
    ["Trigliceridi", "trigliceridi|triglycerides|tg", "mg/dL", 0, 150, "ALL", "Trigliceridi: sensibili a carboidrati, alcol, digiuno, peso e controllo glicemico."],
    # Rene/fegato/infiammazione
    ["Creatinina", "creatinina|creatinine", "mg/dL", 0.6, 1.3, "ALL", "Creatinina: marker indiretto della funzione renale, influenzato dalla massa muscolare."],
    ["eGFR", "egfr|filtrato glomerulare|gfr", "mL/min/1.73m2", 60, 999, "ALL", "eGFR: stima del filtrato glomerulare; da leggere con età, massa muscolare e idratazione."],
    ["Uricemia", "uricemia|acido urico|uric acid", "mg/dL", 3.5, 7.2, "ALL", "Uricemia: metabolismo purinico; utile con dieta, alcol, farmaci, rene e rischio gotta."],
    ["AST-GOT", "ast|got|aspartato aminotransferasi", "U/L", 0, 40, "ALL", "AST/GOT: enzima epatico e muscolare; può aumentare anche dopo esercizio intenso."],
    ["ALT-GPT", "alt|gpt|alanina aminotransferasi", "U/L", 0, 41, "ALL", "ALT/GPT: enzima più orientativo per danno/sofferenza epatocellulare."],
    ["Gamma-GT", "gamma gt|ggt|gamma-glutamil transferasi|gamma glutamil transferasi", "U/L", 0, 60, "ALL", "Gamma-GT: enzima epato-biliare; sensibile ad alcol, farmaci e steatosi."],
    ["PCR", "pcr|proteina c reattiva|crp", "mg/L", 0, 5, "ALL", "PCR: marker infiammatorio aspecifico; non identifica da sola la causa."],
    ["VES", "ves|velocita eritrosedimentazione|esr", "mm/h", 0, 20, "ALL", "VES: marker infiammatorio aspecifico, più lento e meno dinamico della PCR."],
    # Assetto marziale/vitamine/tiroide
    ["Ferritina", "ferritina|ferritin", "ng/mL", 30, 400, "M", "Ferritina: deposito di ferro; aumenta anche con infiammazione."],
    ["Ferritina", "ferritina|ferritin", "ng/mL", 15, 150, "F", "Ferritina: deposito di ferro; aumenta anche con infiammazione."],
    ["Sideremia", "sideremia|ferro sierico|serum iron", "ug/dL", 50, 170, "ALL", "Sideremia: ferro circolante; variabile, da interpretare con ferritina/transferrina."],
    ["Vitamina D", "vitamina d|25-oh vitamina d|25 oh d|25ohd", "ng/mL", 30, 100, "ALL", "Vitamina D: stato vitaminico; interpretare con stagione, supplementazione e obiettivo clinico."],
    ["Vitamina B12", "vitamina b12|cobalamina|b12", "pg/mL", 200, 900, "ALL", "Vitamina B12: importante per eritropoiesi e funzione neurologica."],
    ["Folati", "folati|acido folico|folate", "ng/mL", 3, 20, "ALL", "Folati: utili per eritropoiesi e metabolismo dell'omocisteina."],
    ["TSH", "tsh|tireotropina", "mIU/L", 0.4, 4.0, "ALL", "TSH: principale indicatore di regolazione tiroidea; da leggere con FT3/FT4 e terapia."],
    ["FT3", "ft3|triiodotironina libera", "pg/mL", 2.0, 4.4, "ALL", "FT3: quota libera della triiodotironina."],
    ["FT4", "ft4|tiroxina libera", "ng/dL", 0.8, 1.8, "ALL", "FT4: quota libera della tiroxina."],
], columns=["analita", "alias", "unita", "min", "max", "sesso", "note"])

GROUPS = {
    "Emocromo (Sg)": ["WBC-Globuli Bianchi", "RBC-Globuli Rossi", "HGB-Emoglobina", "HCT-Ematocrito", "MCV", "MCH", "PLT-Piastrine"],
    "Metabolismo glucidico": ["Glicemia", "HbA1c", "Insulina", "HOMA-IR"],
    "Profilo lipidico": ["Colesterolo totale", "LDL", "HDL", "Trigliceridi", "Rapporto TG/HDL"],
    "Fegato / rene / infiammazione": ["AST-GOT", "ALT-GPT", "Gamma-GT", "Creatinina", "eGFR", "Uricemia", "PCR", "VES"],
    "Assetto marziale / vitamine / tiroide": ["Ferritina", "Sideremia", "Vitamina D", "Vitamina B12", "Folati", "TSH", "FT3", "FT4"],
}

VALUE_PATTERN = re.compile(
    r"(?P<name>[A-Za-zÀ-ÿ0-9\-\s\(\)\/\.]{2,70})\s+"
    r"(?P<value>[<>]?\s*\d{1,6}(?:[\.,]\d+)?)\s*"
    r"(?P<unit>mg/dL|g/dL|ng/mL|pg/mL|mIU/L|mU/L|µU/mL|uU/mL|U/L|UI/L|%|mmol/L|fL|pg|mm/h|mg/L|µg/dL|ug/dL|10\^3/uL|10\^6/uL|x10\^3/uL|x10\^6/uL|mL/min/1\.73m2)?",
    re.IGNORECASE,
)

DATE_PATTERNS = [
    re.compile(r"(?:data\s*(?:prelievo|accettazione|referto|esame)?\s*[:\-]?\s*)?(\d{1,2}[\/\.-]\d{1,2}[\/\.-]\d{2,4})", re.I),
]


def load_ranges() -> pd.DataFrame:
    try:
        df = pd.read_csv("range_laboratorio.csv")
        needed = {"analita", "alias", "unita", "min", "max", "sesso", "note"}
        if needed.issubset(df.columns):
            df["sesso"] = df["sesso"].fillna("ALL").str.upper()
            return df
    except Exception:
        pass
    return DEFAULT_RANGES.copy()


def build_alias_index(ranges: pd.DataFrame) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for _, row in ranges.iterrows():
        for alias in str(row["alias"]).split("|"):
            out[alias.lower().strip()] = row["analita"]
        out[str(row["analita"]).lower().strip()] = row["analita"]
    return out


def normalize_number(value: str) -> Optional[float]:
    value = value.strip().replace(" ", "").replace(",", ".")
    value = value.lstrip("<>")
    try:
        return float(value)
    except Exception:
        return None


def parse_date(text: str, fallback_name: str) -> str:
    candidates: List[datetime] = []
    for pat in DATE_PATTERNS:
        for raw in pat.findall(text[:5000]):
            raw = raw.replace("-", "/").replace(".", "/")
            for fmt in ["%d/%m/%Y", "%d/%m/%y"]:
                try:
                    candidates.append(datetime.strptime(raw, fmt))
                    break
                except Exception:
                    pass
    if candidates:
        return min(candidates).strftime("%d/%m/%Y")
    return fallback_name


def extract_text_from_upload(uploaded_file) -> str:
    name = uploaded_file.name.lower()
    data = uploaded_file.read()
    if name.endswith(".pdf"):
        if fitz is None:
            st.error("PyMuPDF non installato: impossibile leggere PDF testuali.")
            return ""
        doc = fitz.open(stream=data, filetype="pdf")
        text = "\n".join(page.get_text("text") for page in doc)
        return text
    if name.endswith((".png", ".jpg", ".jpeg", ".webp")):
        if Image is None or pytesseract is None:
            st.warning("Per leggere immagini scannerizzate serve OCR: installa pillow + pytesseract + Tesseract.")
            return ""
        image = Image.open(io.BytesIO(data))
        return pytesseract.image_to_string(image, lang="ita+eng")
    return ""


def match_analyte(raw_name: str, alias_index: Dict[str, str], threshold: int = 82) -> Optional[str]:
    raw = raw_name.lower().strip(" :-\t")
    if raw in alias_index:
        return alias_index[raw]
    result = process.extractOne(raw, list(alias_index.keys()), scorer=fuzz.partial_ratio)
    if result and result[1] >= threshold:
        return alias_index[result[0]]
    return None


def get_reference(analita: Optional[str], sesso: str, ranges: pd.DataFrame):
    if not analita:
        return None
    sesso = sesso.upper()
    sub = ranges[(ranges["analita"] == analita) & ((ranges["sesso"] == sesso) | (ranges["sesso"] == "ALL"))]
    if sub.empty:
        return None
    specific = sub[sub["sesso"] == sesso]
    return specific.iloc[0] if not specific.empty else sub.iloc[0]


def classify(value: float, minimum: Optional[float], maximum: Optional[float]) -> str:
    if minimum is None or maximum is None or pd.isna(minimum) or pd.isna(maximum):
        return ""
    if value < float(minimum):
        return "BASSO"
    if value > float(maximum):
        return "ALTO"
    return "OK"


def extract_values(text: str, sesso: str, source_date: str) -> pd.DataFrame:
    ranges = load_ranges()
    alias_index = build_alias_index(ranges)
    rows = []
    seen = set()
    for line in text.splitlines():
        line = re.sub(r"\s+", " ", line.strip())
        if len(line) < 4:
            continue
        m = VALUE_PATTERN.search(line)
        if not m:
            continue
        value = normalize_number(m.group("value"))
        if value is None:
            continue
        raw_name = m.group("name").strip(" :-")
        analita = match_analyte(raw_name, alias_index)
        if not analita:
            continue
        key = (analita, source_date)
        if key in seen:
            continue
        seen.add(key)
        ref = get_reference(analita, sesso, ranges)
        if ref is not None:
            unit = m.group("unit") or ref["unita"]
            rmin, rmax, note = float(ref["min"]), float(ref["max"]), ref["note"]
        else:
            unit, rmin, rmax, note = m.group("unit") or "", None, None, "Range non presente nel database."
        rows.append({
            "Analita": analita,
            "Data": source_date,
            "Valore": value,
            "UM": unit,
            "Range minimo": rmin,
            "Range massimo": rmax,
            "Valori di riferimento": ref_string(rmin, rmax, unit),
            "Stato": classify(value, rmin, rmax),
            "Nota": note,
            "Riga originale": line,
        })
    return pd.DataFrame(rows)


def add_derived(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    rows = []
    for date, sub in df.groupby("Data"):
        vals = dict(zip(sub["Analita"], sub["Valore"]))
        if "Glicemia" in vals and "Insulina" in vals:
            homa = round(vals["Glicemia"] * vals["Insulina"] / 405, 2)
            rows.append({"Analita": "HOMA-IR", "Data": date, "Valore": homa, "UM": "", "Range minimo": 0, "Range massimo": 2.5,
                         "Valori di riferimento": "0 - 2.5", "Stato": classify(homa, 0, 2.5),
                         "Nota": "Indice stimato di insulino-resistenza calcolato da glicemia e insulina.", "Riga originale": "calcolo automatico"})
        if "Trigliceridi" in vals and "HDL" in vals and vals["HDL"]:
            ratio = round(vals["Trigliceridi"] / vals["HDL"], 2)
            rows.append({"Analita": "Rapporto TG/HDL", "Data": date, "Valore": ratio, "UM": "", "Range minimo": 0, "Range massimo": 2.0,
                         "Valori di riferimento": "0 - 2.0", "Stato": classify(ratio, 0, 2.0),
                         "Nota": "Indice metabolico indiretto; cut-off indicativo.", "Riga originale": "calcolo automatico"})
    return pd.concat([df, pd.DataFrame(rows)], ignore_index=True) if rows else df


def ref_string(rmin, rmax, unit: str) -> str:
    if rmin is None or rmax is None or pd.isna(rmin) or pd.isna(rmax):
        return ""
    if float(rmin) == 0:
        return f"< {rmax:g} {unit}".strip()
    if float(rmax) >= 900:
        return f"> {rmin:g} {unit}".strip()
    return f"{rmin:g} - {rmax:g} {unit}".strip()


def fmt_val(x) -> str:
    if pd.isna(x):
        return ""
    try:
        return f"{float(x):g}"
    except Exception:
        return str(x)


def delta_text(v1, v2, unit: str) -> str:
    if pd.isna(v1) or pd.isna(v2):
        return ""
    d = float(v2) - float(v1)
    sign = "+" if d > 0 else ""
    pct = (d / float(v1) * 100) if float(v1) != 0 else None
    if pct is None:
        return f"{sign}{d:g} {unit}".strip()
    return f"{sign}{d:g} {unit} ({sign}{pct:.1f}%)".strip()


def build_comparison(df: pd.DataFrame, selected_dates: List[str]) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    dates = selected_dates[:2]
    pivot = df.pivot_table(index="Analita", columns="Data", values="Valore", aggfunc="first")
    meta = df.drop_duplicates("Analita").set_index("Analita")
    order_rows = []
    all_known = []
    for group, analytes in GROUPS.items():
        order_rows.append({"_group": True, "Esame richiesto": group})
        all_known += analytes
        for a in analytes:
            if a in pivot.index:
                v1 = pivot.loc[a, dates[0]] if len(dates) > 0 and dates[0] in pivot.columns else pd.NA
                v2 = pivot.loc[a, dates[1]] if len(dates) > 1 and dates[1] in pivot.columns else pd.NA
                unit = str(meta.loc[a, "UM"] or "") if a in meta.index else ""
                stato = ""
                if a in meta.index:
                    stati = df[df["Analita"] == a]["Stato"].dropna().unique().tolist()
                    if "ALTO" in stati or "BASSO" in stati:
                        stato = " | Attenzione: valore fuori range in almeno una data."
                order_rows.append({
                    "_group": False,
                    "Esame richiesto": a,
                    "U.M": unit,
                    "Data 1": fmt_val(v1),
                    "Data 2": fmt_val(v2),
                    "Differenza": delta_text(v1, v2, unit),
                    "Valori di Riferimento": meta.loc[a, "Valori di riferimento"] if a in meta.index else "",
                    "Nota": (meta.loc[a, "Nota"] if a in meta.index else "") + stato,
                })
    # analiti riconosciuti non presenti nei gruppi
    for a in [x for x in pivot.index if x not in all_known]:
        v1 = pivot.loc[a, dates[0]] if len(dates) > 0 and dates[0] in pivot.columns else pd.NA
        v2 = pivot.loc[a, dates[1]] if len(dates) > 1 and dates[1] in pivot.columns else pd.NA
        unit = str(meta.loc[a, "UM"] or "") if a in meta.index else ""
        order_rows.append({"_group": False, "Esame richiesto": a, "U.M": unit, "Data 1": fmt_val(v1), "Data 2": fmt_val(v2),
                           "Differenza": delta_text(v1, v2, unit), "Valori di Riferimento": meta.loc[a, "Valori di riferimento"], "Nota": meta.loc[a, "Nota"]})
    return pd.DataFrame(order_rows)


def make_pdf(report_df: pd.DataFrame, patient: str, report_date: str, logo_file, doctor_block: str) -> bytes:
    if colors is None:
        raise RuntimeError("ReportLab non installato. Installa: pip install reportlab")
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(A4), leftMargin=1.0*cm, rightMargin=1.0*cm, topMargin=.8*cm, bottomMargin=.8*cm)
    styles = getSampleStyleSheet()
    small = ParagraphStyle("small", parent=styles["Normal"], fontSize=7, leading=8.5)
    small_center = ParagraphStyle("small_center", parent=small, alignment=TA_CENTER)
    normal = ParagraphStyle("normal", parent=styles["Normal"], fontSize=9, leading=11)
    elems = []
    header_cells = []
    if logo_file is not None:
        raw = logo_file.getvalue()
        img = RLImage(io.BytesIO(raw), width=5.8*cm, height=3.0*cm, kind="proportional")
        header_cells.append(img)
    else:
        header_cells.append(Paragraph("<b>LOGO</b>", normal))
    header_cells.append(Paragraph(doctor_block.replace("\n", "<br/>"), normal))
    header_cells.append(Paragraph(report_date, normal))
    header = Table([header_cells], colWidths=[6.2*cm, 13.5*cm, 6.2*cm])
    header.setStyle(TableStyle([("VALIGN", (0,0), (-1,-1), "TOP"), ("ALIGN", (2,0), (2,0), "RIGHT")]))
    elems.append(header)
    elems.append(Spacer(1, .4*cm))
    elems.append(Paragraph(f"Sig. {patient}", normal))
    elems.append(Spacer(1, .25*cm))
    data = [[Paragraph("<i>Esame richiesto</i>", small_center), Paragraph("<i>U.M</i>", small_center), Paragraph("Data 1", small_center), Paragraph("Data 2", small_center), Paragraph("<i>Differenza</i>", small_center), Paragraph("Valori di<br/>Riferimento", small_center), Paragraph("Nota", small_center)]]
    for _, r in report_df.iterrows():
        if bool(r.get("_group", False)):
            data.append([Paragraph(f"<b>{r['Esame richiesto']}</b>", small), "", "", "", "", "", ""])
        else:
            data.append([Paragraph(str(r.get("Esame richiesto", "")), small), Paragraph(str(r.get("U.M", "")), small_center), Paragraph(str(r.get("Data 1", "")), small_center), Paragraph(str(r.get("Data 2", "")), small_center), Paragraph(str(r.get("Differenza", "")), small_center), Paragraph(str(r.get("Valori di Riferimento", "")), small_center), Paragraph(str(r.get("Nota", "")), small)])
    table = Table(data, colWidths=[5.6*cm, 1.7*cm, 2.4*cm, 2.4*cm, 3.4*cm, 3.2*cm, 8.0*cm], repeatRows=1)
    style = TableStyle([
        ("GRID", (0,0), (-1,-1), .45, colors.black),
        ("BACKGROUND", (0,0), (-1,0), colors.whitesmoke),
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
        ("FONTSIZE", (0,0), (-1,-1), 7),
    ])
    for idx, r in report_df.iterrows():
        table_row = idx + 1
        if bool(r.get("_group", False)):
            style.add("BACKGROUND", (0, table_row), (-1, table_row), colors.HexColor("#f3f4f6"))
            style.add("SPAN", (0, table_row), (-1, table_row))
    table.setStyle(style)
    elems.append(table)
    doc.build(elems)
    return buffer.getvalue()


st.markdown('<div class="main-title">Referto comparativo analisi ematochimiche</div>', unsafe_allow_html=True)
st.markdown('<div class="sub">Carica uno o più PDF/immagini: l\'app riconosce data, analiti, valori, unità, range, differenza tra due referti e genera una tabella in stile professionale.</div>', unsafe_allow_html=True)

with st.sidebar:
    st.header("Intestazione")
    patient = st.text_input("Nome paziente", "Esempio")
    sesso = st.selectbox("Sesso biologico per range", ["ALL", "M", "F"], index=0)
    report_date = st.text_input("Data report", datetime.today().strftime("%d/%m/%Y"))
    logo = st.file_uploader("Logo intestazione", type=["png", "jpg", "jpeg"])
    doctor_block = st.text_area("Dati professionista", "Dr. Danilo Bramard\nBiologo Nutrizionista\nLaurea Magistrale in Biologia applicata alle scienze della nutrizione\nIscritto all'Ordine Nazionale dei Biologi\nP.IVA: 03982150041\n☎ +393393121941 | ✉ danilo@newbodycenter.it", height=170)
    st.divider()
    st.caption("Per PDF scannerizzati/immagini serve OCR installato nell'ambiente Python.")

files = st.file_uploader("Carica referti PDF o immagini", type=["pdf", "png", "jpg", "jpeg", "webp"], accept_multiple_files=True)

all_rows = []
texts = {}
if files:
    for f in files:
        text = extract_text_from_upload(f)
        date = parse_date(text, f.name)
        texts[f.name] = text
        part = extract_values(text, sesso, date)
        all_rows.append(part)

if all_rows:
    raw_df = pd.concat(all_rows, ignore_index=True) if all_rows else pd.DataFrame()
    raw_df = add_derived(raw_df)
    dates = sorted(raw_df["Data"].dropna().unique().tolist()) if not raw_df.empty else []
    if len(dates) >= 2:
        selected_dates = st.multiselect("Scegli le due date da confrontare", dates, default=[dates[0], dates[-1]], max_selections=2)
    else:
        selected_dates = dates

    if not raw_df.empty and selected_dates:
        comparison = build_comparison(raw_df, selected_dates)
        visible = comparison.drop(columns=["_group"], errors="ignore")
        st.subheader("Schema comparativo")
        st.dataframe(visible, use_container_width=True, hide_index=True)
        st.subheader("Valori estratti")
        st.dataframe(raw_df[["Analita", "Data", "Valore", "UM", "Valori di riferimento", "Stato", "Nota", "Riga originale"]], use_container_width=True, hide_index=True)
        csv = visible.to_csv(index=False).encode("utf-8")
        st.download_button("Scarica tabella CSV", csv, "referto_comparativo.csv", "text/csv")
        try:
            pdf_bytes = make_pdf(comparison, patient, report_date, logo, doctor_block)
            st.download_button("Scarica PDF impaginato", pdf_bytes, "referto_comparativo.pdf", "application/pdf")
        except Exception as e:
            st.warning(f"PDF non generato: {e}")
    else:
        st.warning("Sono stati caricati file, ma non sono stati riconosciuti valori strutturati.")

    with st.expander("Testo letto dai referti"):
        for name, text in texts.items():
            st.markdown(f"**{name}**")
            st.text(text[:8000] if text else "Nessun testo letto.")
else:
    st.info("Carica almeno un referto. Con due referti viene calcolata la differenza Data 2 - Data 1.")

st.markdown('<div class="warn">Nota: la lettura automatica va sempre verificata sui PDF originali. I range sono indicativi e possono essere sostituiti con quelli reali del laboratorio nel file range_laboratorio.csv.</div>', unsafe_allow_html=True)
