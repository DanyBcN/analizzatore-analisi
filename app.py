from __future__ import annotations

import base64
import io
import re
from datetime import datetime
from typing import Dict, List, Optional

import pandas as pd
import streamlit as st

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
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image as RLImage
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
except Exception:
    colors = None
    SimpleDocTemplate = Table = TableStyle = Paragraph = Spacer = RLImage = None
    getSampleStyleSheet = ParagraphStyle = None

st.set_page_config(page_title="Referto comparativo analisi", page_icon="🧪", layout="wide")

VERSIONE_APP = "VERSIONE CORRETTA 2026-06-01-quater: confronto completo, unione di tutti gli esami, OCR per PDF scansionati."

DOCTOR_BLOCK = """<b>Dr. Danilo Bramard</b><br>
Biologo Nutrizionista<br>
Laurea Magistrale in Biologia applicata alle scienze della nutrizione<br>
Iscritto all'Ordine Nazionale dei Biologi<br>
P.IVA: 03982150041<br>
☎ +393393121941 | ✉ danilo@newbodycenter.it"""

GROUPS = {
    "Emocromo (Sg)": [
        "WBC-Globuli Bianchi", "RBC-Globuli Rossi", "HGB-Emoglobina", "HCT-Ematocrito",
        "MCV-Volume Eritrocitario", "MCH-Contenuto Corpuscolare HGB", "MCHC-Concentrazione Corpuscolare Hgb",
        "RDW-Indice Anisocitosi Eritrocitaria", "RDW-SD", "PLT-Piastrine", "MPV-Volume Piastrinico",
        "Neutrofili %", "Linfociti %", "Monociti %", "Eosinofili %", "Basofili %",
        "Neutrofili assoluti", "Linfociti assoluti", "Monociti assoluti", "Eosinofili assoluti", "Basofili assoluti",
    ],
    "Coagulazione": ["INR", "aPTT tempo", "aPTT ratio", "Tempo tromboplastina parziale", "Ratio PTT"],
    "Metabolismo glucidico": ["Glucosio", "Glicemia", "Insulina", "HbA1c", "HOMA-IR"],
    "Profilo lipidico": ["Colesterolo totale", "Colesterolo HDL", "Colesterolo LDL", "Trigliceridi", "Rapporto TG/HDL"],
    "Fegato / rene / infiammazione": [
        "Creatinina", "eGFR", "GammaGT", "AST-GOT", "ALT-GPT", "Bilirubina totale", "CPK", "PCR", "VES",
        "Potassio", "Sodio", "Uricemia"
    ],
    "Assetto marziale / vitamine / tiroide": ["Ferro", "Ferritina", "Transferrina", "Vitamina D", "TSH-R", "FT3", "FT4", "Vitamina B12", "Folati"],
    "Microbiologia / sierologia": ["SARS-CoV-2 IgG", "SARS-CoV-2 IgM"],
    "Urine": ["Colore urine", "Aspetto urine", "pH urine", "Glucosio urine", "Proteine urine", "Bilirubina urine", "Urobilinogeno urine", "Emoglobina urine", "Corpi chetonici urine", "Leucociti urine", "Nitriti urine", "Peso specifico urine"],
}

ALIASES: Dict[str, str] = {
    "wbc": "WBC-Globuli Bianchi", "globuli bianchi": "WBC-Globuli Bianchi",
    "rbc": "RBC-Globuli Rossi", "globuli rossi": "RBC-Globuli Rossi",
    "hgb": "HGB-Emoglobina", "emoglobina": "HGB-Emoglobina",
    "hct": "HCT-Ematocrito", "ematocrito": "HCT-Ematocrito",
    "mcv": "MCV-Volume Eritrocitario", "mch": "MCH-Contenuto Corpuscolare HGB", "mchc": "MCHC-Concentrazione Corpuscolare Hgb",
    "rdw-indice anisocitosi eritrocitaria": "RDW-Indice Anisocitosi Eritrocitaria", "rdw cv": "RDW-Indice Anisocitosi Eritrocitaria", "rdw - cv": "RDW-Indice Anisocitosi Eritrocitaria", "rdw": "RDW-Indice Anisocitosi Eritrocitaria", "rdw-sd": "RDW-SD", "rdw - sd": "RDW-SD",
    "plt": "PLT-Piastrine", "piastrine": "PLT-Piastrine", "conteggio piastrine": "PLT-Piastrine", "mpv": "MPV-Volume Piastrinico",
    "neutrofili": "Neutrofili %", "linfociti": "Linfociti %", "monociti": "Monociti %", "eosinofili": "Eosinofili %", "basofili": "Basofili %",
    "inr": "INR", "tempo": "aPTT tempo", "ratio": "aPTT ratio", "t tromboplastina parziale": "Tempo tromboplastina parziale", "ratio ptt": "Ratio PTT",
    "glucosio": "Glucosio", "glicemia": "Glicemia", "glicemia basale": "Glicemia",
    "creatinina": "Creatinina", "egfr": "eGFR", "filtrato glomerulare": "eGFR",
    "gammagt": "GammaGT", "gamma gt": "GammaGT", "ggt": "GammaGT", "gammaglutamiltranspeptidasi": "GammaGT",
    "alt": "ALT-GPT", "alanina amino t": "ALT-GPT", "alat": "ALT-GPT",
    "ast": "AST-GOT", "aspartato amino t": "AST-GOT", "asat": "AST-GOT",
    "bilirubina totale": "Bilirubina totale", "creatinfosfochinasi": "CPK", "cpk": "CPK", "proteina c reattiva": "PCR", "pcr": "PCR",
    "potassio ematico": "Potassio", "potassio": "Potassio", "sodio ematico": "Sodio", "sodio": "Sodio",
    "ferro": "Ferro", "ferritina": "Ferritina", "colesterolo": "Colesterolo totale", "colesterolo totale": "Colesterolo totale",
    "colesterolo hdl": "Colesterolo HDL", "hdl": "Colesterolo HDL", "colesterolo ldl": "Colesterolo LDL", "ldl": "Colesterolo LDL",
    "trigliceridi": "Trigliceridi", "tsh": "TSH-R", "tsh-r": "TSH-R", "tsh reflex": "TSH-R", "vitamina d": "Vitamina D",
    "sars-cov-2 anticorpi igg": "SARS-CoV-2 IgG", "anticorpi igg": "SARS-CoV-2 IgG", "sars-cov-2 anticorpi igm": "SARS-CoV-2 IgM", "anticorpi igm": "SARS-CoV-2 IgM",
    "colore": "Colore urine", "aspetto": "Aspetto urine", "ph": "pH urine", "proteine": "Proteine urine",
    "bilirubina": "Bilirubina urine", "urobilinogeno": "Urobilinogeno urine", "corpi chetonici": "Corpi chetonici urine",
    "leucociti": "Leucociti urine", "nitriti": "Nitriti urine", "peso specifico": "Peso specifico urine", "emoglobina urine": "Emoglobina urine",
}

DEFAULT_REFS = {"Peso specifico urine": "1,005 - 1,030"}

NOTES = {
    "RDW-Indice Anisocitosi Eritrocitaria": "RDW: variabilità dimensionale dei globuli rossi; utile con MCV e ferritina.",
    "Ferro": "Ferro sierico: variabile; leggere con ferritina, transferrina ed emocromo.",
    "Ferritina": "Ferritina: deposito di ferro; aumenta anche con infiammazione.",
    "Peso specifico urine": "Peso specifico urinario alto: urine concentrate; valutare idratazione, perdite di liquidi e quadro clinico.",
    "Colesterolo totale": "Colesterolo totale: leggere insieme a HDL, LDL, TG e rischio cardiovascolare.",
    "ALT-GPT": "ALT: enzima epatico; contestualizzare con AST, GGT, farmaci, alcol e attività fisica.",
    "AST-GOT": "AST: enzima epatico/muscolare; contestualizzare con ALT, GGT e attività fisica.",
    "eGFR": "eGFR: stima della filtrazione renale; da interpretare con età, massa muscolare e creatinina.",
}

DATE_RE = re.compile(r"\b\d{1,2}[/\.\-]\d{1,2}[/\.\-]\d{2,4}\b")


def clean(s: str) -> str:
    return re.sub(r"\s+", " ", str(s or "").strip())


def norm(s: str) -> str:
    s = clean(s).lower().replace("ì", "i").replace("µ", "u")
    s = re.sub(r"[()\[\],;:]", " ", s)
    return re.sub(r"\s+", " ", s).strip(" -")


def canonical(name: str, urine: bool = False) -> Optional[str]:
    n = norm(name)
    if not n or n in {"esame richiesto", "risultato", "u m", "valori di riferimento", "metodo", "metodica", "siero", "plasma"}:
        return None
    if urine and n in {"glucosio", "emoglobina", "proteine", "bilirubina"}:
        return {"glucosio": "Glucosio urine", "emoglobina": "Emoglobina urine", "proteine": "Proteine urine", "bilirubina": "Bilirubina urine"}[n]
    if n in ALIASES:
        return ALIASES[n]
    for k, v in sorted(ALIASES.items(), key=lambda kv: len(kv[0]), reverse=True):
        if n.startswith(k) or re.search(r"\b" + re.escape(k) + r"\b", n):
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
    patterns = [
        r"Nr\.?\s*Richiesta[^\n]{0,80}\bdel\s+(\d{1,2}[/\.\-]\d{1,2}[/\.\-]\d{2,4})",
        r"\bli\s*,?\s*(\d{1,2}[/\.\-]\d{1,2}[/\.\-]\d{2,4})",
        r"Firmato\s+il\s+(\d{1,2}[/\.\-]\d{1,2}[/\.\-]\d{2,4})",
        r"\bdel\s+(\d{1,2}[/\.\-]\d{1,2}[/\.\-]\d{2,4})",
    ]
    raw = None
    for pat in patterns:
        m = re.search(pat, text[:6000], re.I)
        if m:
            raw = m.group(1)
            break
    if not raw:
        dates = DATE_RE.findall(text[:6000])
        candidates = []
        for d in dates:
            dd = d.replace("-", "/").replace(".", "/")
            for f in ("%d/%m/%Y", "%d/%m/%y"):
                try:
                    dt = datetime.strptime(dd, f)
                    if dt.year >= 2000:
                        candidates.append(dt)
                    break
                except Exception:
                    pass
        if candidates:
            return candidates[-1].strftime("%d/%m/%Y")
        raw = fallback
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
        if re.search(r"Nr\.?\s*Richiesta", line, re.I) and i + 1 < len(lines):
            cand = lines[i + 1]
            if re.match(r"^[A-ZÀ-Ù' ]{5,}$", cand):
                return cand.title()
    m = re.search(r"BRAMARD\s+DANILO\s+GUIDO", text, re.I)
    if m:
        return "Bramard Danilo Guido"
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


def normalize_ref(ref: str) -> str:
    ref = clean(ref).replace("[", "").replace("]", "").replace("(", "").replace(")", "")
    ref = ref.replace("–", "-").replace("< ", "<").replace("> ", ">")
    return ref


def make_row(analita, date, value, unit, ref, original, source):
    unit = clean(unit).replace("mg/dl", "mg/dL").replace("g/dl", "g/dL").replace("K/µI", "K/µL").replace("M/µI", "M/µL").replace("ul", "µL")
    ref = normalize_ref(ref)
    if analita in DEFAULT_REFS and not ref:
        ref = DEFAULT_REFS[analita]
    stato = status_from_ref(value, ref)
    return {"Analita": analita, "Data": date, "Valore": value, "UM": unit, "Valori di riferimento": ref, "Stato": stato, "Nota": NOTES.get(analita, "Parametro da contestualizzare con quadro clinico, range del laboratorio e terapia."), "Riga originale": f"{source}: {original}"}


def ocr_pdf(doc) -> str:
    if pytesseract is None or Image is None:
        return ""
    texts = []
    for page in doc:
        pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
        img = Image.open(io.BytesIO(pix.tobytes("png")))
        try:
            txt = pytesseract.image_to_string(img, lang="ita+eng", config="--psm 6")
        except Exception:
            try:
                txt = pytesseract.image_to_string(img, config="--psm 6")
            except Exception:
                txt = ""
        texts.append(txt)
    return "\n".join(texts)


def extract_pdf_text(data: bytes) -> tuple[str, bool]:
    if fitz is None:
        return "", False
    doc = fitz.open(stream=data, filetype="pdf")
    text = "\n".join(p.get_text("text") for p in doc)
    if len(clean(text)) < 300 or len(DATE_RE.findall(text)) == 0:
        ocr = ocr_pdf(doc)
        if len(clean(ocr)) > len(clean(text)):
            return ocr, True
    return text, False


def extract_rows_from_text(text: str, date: str, filename: str) -> pd.DataFrame:
    rows = []
    lines = [clean(x) for x in text.splitlines() if clean(x)]
    urine_mode = False
    pending = None
    skip_words = {"metodo", "metodica", "siero", "plasma", "pagina", "referto", "firmato", "direttrice", "telefono", "codice", "sede"}

    def parse_value_ref(s: str):
        ref = ""
        ref_m = re.search(r"[\[\(]?\s*((?:<|>|fino a|oltre|da)?\s*\d+(?:[\.,]\d+)?\s*(?:-|a|–)?\s*\d*(?:[\.,]\d+)?)[\]\)]?", s, re.I)
        val_m = re.search(r"(?<!\d)([<>]?\s*\d+(?:[\.,]\d+)?)(?!\d)", s)
        if not val_m:
            return None, "", ""
        val = parse_num(val_m.group(1))
        after = s[val_m.end():]
        unit_m = re.search(r"([A-Za-zµ/%]+(?:/[A-Za-z0-9µ²\.]+)?|10\^?\d+/[A-Za-zµ]+|mL/min/1,73mq|ml/min/1,73\s*m\²)", after)
        unit = clean(unit_m.group(1)) if unit_m else ""
        all_refs = re.findall(r"[\[\(]\s*([^\[\]\(\)]*\d[^\[\]\(\)]*)\s*[\]\)]", s)
        if all_refs:
            ref = all_refs[-1]
        else:
            tail_refs = re.findall(r"(?:<|>|fino a|oltre|da)?\s*\d+(?:[\.,]\d+)?\s*(?:-|a|–)\s*\d+(?:[\.,]\d+)?|(?:<|>|fino a|oltre)\s*\d+(?:[\.,]\d+)?", after, re.I)
            if tail_refs:
                ref = tail_refs[-1]
        return val, unit, ref

    for i, line in enumerate(lines):
        low = norm(line)
        if any(w in low for w in skip_words):
            continue
        if "urine" in low:
            urine_mode = True
        a = canonical(line, urine_mode)
        if a:
            val, unit, ref = parse_value_ref(line)
            if val is not None and not (isinstance(val, (int, float)) and val == 0 and a not in {"SARS-CoV-2 IgG", "SARS-CoV-2 IgM"}):
                rows.append(make_row(a, date, val, unit, ref, line, filename))
                pending = None
            else:
                pending = (a, line)
            continue
        if pending:
            val, unit, ref = parse_value_ref(" ".join(lines[i:i+3]))
            if val is not None:
                rows.append(make_row(pending[0], date, val, unit, ref, pending[1] + " | " + line, filename))
                pending = None

    df = pd.DataFrame(rows)
    if df.empty:
        return df
    return df.drop_duplicates(subset=["Analita", "Data"], keep="first")


def add_derived(df: pd.DataFrame) -> pd.DataFrame:
    extra = []
    for date, sub in df.groupby("Data"):
        vals = dict(zip(sub["Analita"], sub["Valore"]))
        tg, hdl = vals.get("Trigliceridi"), vals.get("Colesterolo HDL")
        if isinstance(tg, (int, float)) and isinstance(hdl, (int, float)) and hdl:
            ratio = round(tg / hdl, 2)
            extra.append({"Analita": "Rapporto TG/HDL", "Data": date, "Valore": ratio, "UM": "", "Valori di riferimento": "< 2", "Stato": "ALTO" if ratio > 2 else "OK", "Nota": "Indice metabolico indiretto; cut-off indicativo.", "Riga originale": "calcolo automatico"})
    return pd.concat([df, pd.DataFrame(extra)], ignore_index=True) if extra else df


def process_upload(uploaded):
    data = uploaded.getvalue()
    if uploaded.name.lower().endswith(".pdf"):
        text, used_ocr = extract_pdf_text(data)
    else:
        text, used_ocr = "", False
    date = parse_date(text, uploaded.name)
    patient = parse_patient(text)
    df = extract_rows_from_text(text, date, uploaded.name)
    if not df.empty:
        df = add_derived(df)
        df["File"] = uploaded.name
        df["OCR"] = used_ocr
    return df, text, patient, date, used_ocr


def is_date_col(c: str) -> bool:
    return bool(re.match(r"^\d{2}/\d{2}/\d{4}", str(c)))


def date_sort_key(label: str):
    m = re.match(r"^(\d{2}/\d{2}/\d{4})", str(label))
    if not m:
        return datetime.max
    try:
        return datetime.strptime(m.group(1), "%d/%m/%Y")
    except Exception:
        return datetime.max


def delta(v1, v2, unit: str) -> str:
    if v1 == "" or v2 == "":
        return ""
    try:
        d = float(str(v2).replace(",", ".").replace("*", "")) - float(str(v1).replace(",", ".").replace("*", ""))
        return f"{'+' if d > 0 else ''}{d:g} {unit}".strip().replace(".", ",")
    except Exception:
        return ""


def build_report_table(df: pd.DataFrame, dates: List[str]) -> pd.DataFrame:
    dates = list(dates)
    cols = ["_group", "_status", "Esame richiesto", "U.M"] + dates + [f"Diff. {i+1}-{i}" for i in range(1, len(dates))] + ["Valori di Riferimento", "Nota"]
    if df.empty:
        return pd.DataFrame(columns=cols)
    pivot = df.pivot_table(index="Analita", columns="Data", values="Valore", aggfunc="first", dropna=False)
    meta = df.drop_duplicates("Analita", keep="last").set_index("Analita")
    out, used = [], set()

    def row_status(n):
        ss = [str(x).upper().strip() for x in df[df["Analita"] == n]["Stato"].tolist()]
        return "ALTO" if "ALTO" in ss else "BASSO" if "BASSO" in ss else ""

    def group_row(g):
        r = {c: "" for c in cols}
        r["_group"] = True
        r["Esame richiesto"] = g
        return r

    def value_row(n):
        unit = meta.loc[n, "UM"] if n in meta.index else ""
        stt = row_status(n)
        r = {c: "" for c in cols}
        r.update({"_group": False, "_status": stt, "Esame richiesto": n, "U.M": unit, "Valori di Riferimento": meta.loc[n, "Valori di riferimento"] if n in meta.index else "", "Nota": f"{stt}. {meta.loc[n, 'Nota']}" if stt else ""})
        vals = []
        for d in dates:
            raw = pivot.loc[n, d] if d in pivot.columns and n in pivot.index else ""
            fv = fmt_value(raw)
            sub = df[(df["Analita"] == n) & (df["Data"] == d)]
            stato_singolo = str(sub.iloc[0]["Stato"]).upper().strip() if not sub.empty else ""
            if stato_singolo in ["ALTO", "BASSO"] and fv:
                fv = f"* {fv}"
            r[d] = fv
            vals.append(fv)
        for i in range(1, len(dates)):
            r[f"Diff. {i+1}-{i}"] = delta(vals[i-1], vals[i], unit)
        return r

    for g, names in GROUPS.items():
        present = [n for n in names if n in pivot.index]
        if present:
            out.append(group_row(g))
            for n in present:
                used.add(n)
                out.append(value_row(n))
    leftovers = [n for n in pivot.index.tolist() if n not in used]
    if leftovers:
        out.append(group_row("Altri esami"))
        for n in leftovers:
            out.append(value_row(n))
    return pd.DataFrame(out, columns=cols)


def visible_cols(df: pd.DataFrame) -> List[str]:
    return [c for c in df.columns if not c.startswith("_")]


def data_url_from_upload(file) -> Optional[str]:
    if not file:
        return None
    ext = file.name.split(".")[-1].lower()
    mime = "image/png" if ext == "png" else "image/jpeg"
    return f"data:{mime};base64," + base64.b64encode(file.getvalue()).decode("ascii")


def report_html(report_df: pd.DataFrame, patient: str, report_date: str, logo_data_url: Optional[str]) -> str:
    logo = f'<img src="{logo_data_url}" class="logo">' if logo_data_url else '<div class="logo-placeholder">DB<br><span>Nutrition and Performance</span></div>'
    cols = visible_cols(report_df)
    body = []
    for _, r in report_df.iterrows():
        stt = str(r.get("_status", "")).upper()
        if r.get("_group"):
            body.append(f'<tr class="group"><td colspan="{len(cols)}"><b>{r["Esame richiesto"]}</b></td></tr>')
        else:
            cells = []
            for c in cols:
                txt = str(r.get(c, "") or "")
                classes = []
                if c == "Esame richiesto": classes.append("exam")
                if c == "Nota": classes.append("note")
                if is_date_col(c) and txt.startswith("*"): classes.append("abnormal-value")
                if c == "Nota" and stt in ["ALTO", "BASSO"]: classes.append("abnormal-note")
                cells.append(f'<td class="{" ".join(classes)}">{txt}</td>')
            body.append("<tr>" + "".join(cells) + "</tr>")
    headers = "".join([f'<th>{str(c).replace("Valori di Riferimento", "Valori di<br>Riferimento")}</th>' for c in cols])
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
<div class="report-sheet"><div class="header"><div>{logo}</div><div class="doctor">{DOCTOR_BLOCK}</div><div class="date">{report_date}</div></div><div class="patient">Sig. {patient}</div><table class="referto"><thead><tr>{headers}</tr></thead><tbody>{''.join(body)}</tbody></table></div>"""


def make_pdf(report_df: pd.DataFrame, patient: str, report_date: str, logo_bytes: Optional[bytes]) -> Optional[bytes]:
    if SimpleDocTemplate is None:
        return None
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4), leftMargin=10*mm, rightMargin=10*mm, topMargin=10*mm, bottomMargin=10*mm)
    styles = getSampleStyleSheet()
    normal = ParagraphStyle("normal_small", parent=styles["Normal"], fontName="Helvetica", fontSize=7, leading=8)
    center = ParagraphStyle("center", parent=normal, alignment=1)
    bold = ParagraphStyle("bold", parent=normal, fontName="Helvetica-Bold")
    red_center = ParagraphStyle("red_center", parent=center, textColor=colors.HexColor("#b00000"), fontName="Helvetica-Bold")
    red_note = ParagraphStyle("red_note", parent=normal, textColor=colors.HexColor("#b00000"), fontName="Helvetica-Bold")
    doctor = ParagraphStyle("doctor", parent=styles["Normal"], fontSize=8.5, leading=11)
    elems = []
    logo = RLImage(io.BytesIO(logo_bytes), width=52*mm, height=35*mm) if logo_bytes else Paragraph("<b>DB</b><br/>NUTRITION AND PERFORMANCE", styles["Title"])
    header = Table([[logo, Paragraph(DOCTOR_BLOCK.replace("<br>", "<br/>"), doctor), Paragraph(report_date, doctor)]], colWidths=[58*mm, 130*mm, 70*mm])
    header.setStyle(TableStyle([("VALIGN", (0,0), (-1,-1), "TOP"), ("LINEBEFORE", (1,0), (1,0), 1, colors.HexColor("#6aa0ff")), ("LEFTPADDING", (1,0), (1,0), 7), ("ALIGN", (2,0), (2,0), "RIGHT")]))
    elems += [header, Spacer(1, 8*mm), Paragraph(f"<b>Sig. {patient}</b>", styles["Normal"]), Spacer(1, 4*mm)]
    cols = visible_cols(report_df)
    data = [[Paragraph(str(c).replace("Valori di Riferimento", "Valori di<br/>Riferimento"), center) for c in cols]]
    row_statuses = []
    for _, r in report_df.iterrows():
        is_group, stt = bool(r.get("_group")), str(r.get("_status", "")).upper()
        row_statuses.append((is_group, stt))
        row = []
        for c in cols:
            txt = str(r.get(c, "") or "")
            style = bold if is_group else (red_center if is_date_col(c) and txt.startswith("*") else red_note if c == "Nota" and stt in ["ALTO", "BASSO"] else normal if c in ["Esame richiesto", "Nota"] else center)
            row.append(Paragraph(txt, style))
        data.append(row)
    n_dates = len([c for c in cols if is_date_col(c)])
    n_diffs = len([c for c in cols if str(c).startswith("Diff.")])
    widths = [54*mm, 18*mm] + [max(18*mm, min(26*mm, (267*mm-54*mm-18*mm-40*mm-48*mm)/max(1,n_dates+n_diffs)))]*(n_dates+n_diffs) + [40*mm, 48*mm]
    if len(cols) <= 5:
        widths = [62*mm, 22*mm, 28*mm, 42*mm, 104*mm]
    table = Table(data, colWidths=widths, repeatRows=1)
    ts = [("VALIGN", (0,0), (-1,-1), "MIDDLE"), ("LINEBELOW", (0,0), (-1,0), 0.4, colors.black), ("FONTSIZE", (0,0), (-1,-1), 7), ("LEFTPADDING", (0,0), (-1,-1), 4), ("RIGHTPADDING", (0,0), (-1,-1), 4), ("TOPPADDING", (0,0), (-1,-1), 2), ("BOTTOMPADDING", (0,0), (-1,-1), 2)]
    for idx, (is_group, stt) in enumerate(row_statuses, start=1):
        if is_group:
            ts += [("SPAN", (0,idx), (-1,idx)), ("BACKGROUND", (0,idx), (-1,idx), colors.HexColor("#f1f1f1")), ("LINEBELOW", (0,idx), (-1,idx), 0.25, colors.HexColor("#d0d0d0"))]
    table.setStyle(TableStyle(ts))
    elems.append(table)
    doc.build(elems)
    buf.seek(0)
    return buf.read()


st.title("Referto comparativo analisi - layout DB")
st.caption(VERSIONE_APP)

with st.sidebar:
    st.header("Dati referto")
    patient_manual = st.text_input("Nome paziente manuale", "")
    report_date = st.text_input("Data referto", datetime.now().strftime("%d/%m/%Y"))
    logo_file = st.file_uploader("Logo DB", type=["png", "jpg", "jpeg"], key="logo")
    st.info("Per PDF scansionati serve anche packages.txt con tesseract-ocr.")

uploads = st.file_uploader("Carica uno o più PDF del laboratorio", type=["pdf"], accept_multiple_files=True)
all_dfs, texts, patient_auto = [], [], "Esempio"
if uploads:
    for up in uploads:
        df, text, patient, date, used_ocr = process_upload(up)
        if patient and patient != "Esempio":
            patient_auto = patient
        texts.append((up.name, text[:20000], used_ocr, date, 0 if df.empty else len(df)))
        if not df.empty:
            all_dfs.append(df)

if all_dfs:
    full_df = pd.concat(all_dfs, ignore_index=True)
    dates = sorted(full_df["Data"].dropna().unique().tolist(), key=date_sort_key)
    selected = st.multiselect("Date/referti da confrontare", dates, default=dates)
    report_df = build_report_table(full_df, selected)
    patient = patient_manual.strip() or patient_auto
    st.subheader("Anteprima referto")
    st.components.v1.html(report_html(report_df, patient, report_date, data_url_from_upload(logo_file)), height=760, scrolling=True)
    pdf_bytes = make_pdf(report_df, patient, report_date, logo_file.getvalue() if logo_file else None)
    if pdf_bytes is None:
        st.error("PDF non generato: ReportLab non installato. Aggiungi reportlab al requirements.txt e riavvia l’app.")
    else:
        st.download_button("Scarica PDF impaginato", pdf_bytes, "referto_comparativo.pdf", "application/pdf")
    st.download_button("Scarica CSV valori estratti", full_df.to_csv(index=False).encode("utf-8-sig"), "valori_estratti.csv", "text/csv")
    st.subheader("Valori estratti")
    display_df = full_df.copy()
    display_df["Nota"] = display_df.apply(lambda r: r["Nota"] if str(r.get("Stato", "")).upper() in ["ALTO", "BASSO"] else "", axis=1)
    display_df["Valore"] = display_df.apply(lambda r: f"* {fmt_value(r['Valore'])}" if str(r.get("Stato", "")).upper() in ["ALTO", "BASSO"] else fmt_value(r["Valore"]), axis=1)
    def evidenzia_fuori_range(row):
        return ["color:#b00000;font-weight:700;" for _ in row] if str(row.get("Stato", "")).upper() in ["ALTO", "BASSO"] else ["" for _ in row]
    st.dataframe(display_df.style.apply(evidenzia_fuori_range, axis=1), use_container_width=True, hide_index=True)
    with st.expander("Controllo lettura file"):
        for name, txt, used_ocr, date, nrows in texts:
            st.markdown(f"### {name}")
            st.write(f"Data letta: **{date}** | OCR usato: **{used_ocr}** | Esami estratti: **{nrows}**")
            st.text(txt)
else:
    st.warning("Carica almeno un PDF. Se un PDF è una scansione, l’app usa OCR; il risultato va sempre controllato.")
