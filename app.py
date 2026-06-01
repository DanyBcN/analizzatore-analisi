from __future__ import annotations

import io
import re
from datetime import datetime
from typing import Dict, List, Optional, Tuple

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

st.set_page_config(page_title="Referto comparativo analisi", page_icon="🧪", layout="wide")

# ----------------------------
# CONFIGURAZIONE BASE
# ----------------------------
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
        "RDW-Indice Anisocitosi Eritrocitaria", "PLT-Piastrine", "MPV-Volume Piastrinico",
        "Neutrofili %", "Linfociti %", "Monociti %", "Eosinofili %", "Basofili %",
        "Neutrofili assoluti", "Linfociti assoluti", "Monociti assoluti", "Eosinofili assoluti", "Basofili assoluti",
    ],
    "Metabolismo glucidico": ["Glucosio", "Glicemia", "Insulina", "HbA1c", "HOMA-IR"],
    "Profilo lipidico": ["Colesterolo totale", "Colesterolo HDL", "Colesterolo LDL", "Trigliceridi", "Rapporto TG/HDL"],
    "Fegato / rene / infiammazione": ["Creatinina", "eGFR", "GammaGT", "AST-GOT", "ALT-GPT", "PCR", "VES", "Uricemia"],
    "Assetto marziale / vitamine / tiroide": ["Ferro", "Ferritina", "Transferrina", "Vitamina D", "TSH-R", "FT3", "FT4", "Vitamina B12", "Folati"],
    "Urine": ["Colore urine", "Aspetto urine", "pH urine", "Glucosio urine", "Proteine urine", "Bilirubina urine", "Urobilinogeno urine", "Emoglobina urine", "Corpi chetonici urine", "Leucociti urine", "Nitriti urine", "Peso specifico urine"],
}

ALIASES: Dict[str, str] = {
    "wbc-globuli bianchi": "WBC-Globuli Bianchi", "wbc": "WBC-Globuli Bianchi", "globuli bianchi": "WBC-Globuli Bianchi",
    "rbc-globuli rossi": "RBC-Globuli Rossi", "rbc": "RBC-Globuli Rossi", "globuli rossi": "RBC-Globuli Rossi",
    "hgb-emoglobina": "HGB-Emoglobina", "emoglobina": "HGB-Emoglobina", "hgb": "HGB-Emoglobina",
    "hct-ematocrito": "HCT-Ematocrito", "ematocrito": "HCT-Ematocrito", "hct": "HCT-Ematocrito",
    "mcv-volume eritrocitario": "MCV-Volume Eritrocitario", "mcv": "MCV-Volume Eritrocitario",
    "mch-contenuto corpuscolare hgb": "MCH-Contenuto Corpuscolare HGB", "mch": "MCH-Contenuto Corpuscolare HGB",
    "mchc-concentrazione corpuscolare hgb": "MCHC-Concentrazione Corpuscolare Hgb", "mchc": "MCHC-Concentrazione Corpuscolare Hgb",
    "rdw-lndice anisocitosi eritrocitaria": "RDW-Indice Anisocitosi Eritrocitaria", "rdw-indice anisocitosi eritrocitaria": "RDW-Indice Anisocitosi Eritrocitaria", "rdw": "RDW-Indice Anisocitosi Eritrocitaria",
    "pl t-piastrine": "PLT-Piastrine", "plt-piastrine": "PLT-Piastrine", "piastrine": "PLT-Piastrine", "plt": "PLT-Piastrine",
    "mpv-volume piastrinico": "MPV-Volume Piastrinico", "mpv": "MPV-Volume Piastrinico",
    "neutrofili": "Neutrofili %", "linfociti": "Linfociti %", "monociti": "Monociti %", "eosinofili": "Eosinofili %", "eosinofi/i": "Eosinofili %", "basofili": "Basofili %",
    "glucosio": "Glucosio", "glucosio (s)": "Glucosio", "glicemia": "Glicemia",
    "creatinina": "Creatinina", "egfr": "eGFR", "egfr (velocità filtrato glomerulare stimata)": "eGFR", "velocità filtrato glomerulare stimata": "eGFR",
    "gammagt": "GammaGT", "gamma gt": "GammaGT", "ggt": "GammaGT",
    "ferro": "Ferro", "ferro (s)": "Ferro",
    "colesterolo": "Colesterolo totale", "colesterolo (s)": "Colesterolo totale", "colesterolo totale": "Colesterolo totale",
    "colesterolo hdl": "Colesterolo HDL", "colesterolo hdl (s)": "Colesterolo HDL", "hdl": "Colesterolo HDL",
    "trigliceridi": "Trigliceridi", "trigliceridi (s)": "Trigliceridi",
    "tsh-r": "TSH-R", "tsh-r (s)": "TSH-R", "tsh": "TSH-R",
    "ferritina": "Ferritina", "ferritina (s)": "Ferritina",
    "colore": "Colore urine", "aspetto": "Aspetto urine", "ph": "pH urine", "proteine": "Proteine urine", "bilirubina": "Bilirubina urine", "urobilinogeno": "Urobilinogeno urine", "emoglobina": "Emoglobina urine", "corpi chetonici": "Corpi chetonici urine", "leucociti": "Leucociti urine", "nitriti": "Nitriti urine", "peso specifico": "Peso specifico urine",
}


DEFAULT_REFS = {
    # Il laboratorio nel PDF di prova non riporta un range chiaro per il peso specifico urinario.
    # Range operativo usato per evidenziare urine concentrate. Modificabile in base al laboratorio.
    "Peso specifico urine": "1,005 - 1,030",
}

DEFAULT_UNITS = {
    "Peso specifico urine": "",
}

NOTES = {
    "WBC-Globuli Bianchi": "Leucociti: difesa immunitaria; valutare con formula leucocitaria.",
    "RBC-Globuli Rossi": "Eritrociti: da leggere con Hb, HCT e indici eritrocitari.",
    "HGB-Emoglobina": "Emoglobina: trasporto dell'ossigeno; bassa compatibile con quadro anemico da contestualizzare.",
    "HCT-Ematocrito": "Ematocrito: quota volumetrica dei globuli rossi.",
    "MCV-Volume Eritrocitario": "MCV: volume medio dei globuli rossi; utile per classificare micro/macro-citosi.",
    "MCH-Contenuto Corpuscolare HGB": "MCH: contenuto medio di emoglobina per eritrocita.",
    "MCHC-Concentrazione Corpuscolare Hgb": "MCHC: concentrazione media di emoglobina negli eritrociti.",
    "RDW-Indice Anisocitosi Eritrocitaria": "RDW: variabilità dimensionale dei globuli rossi; utile con MCV e ferritina.",
    "PLT-Piastrine": "Piastrine: coagulazione/emostasi; interpretare con clinica e farmaci.",
    "Glucosio": "Glucosio/glicemia: dipende dal digiuno e dal metabolismo glucidico.",
    "Glicemia": "Glicemia: dipende dal digiuno e dal metabolismo glucidico.",
    "Creatinina": "Creatinina: indicatore indiretto della funzione renale, influenzato dalla massa muscolare.",
    "eGFR": "eGFR: stima del filtrato glomerulare; cautela in masse muscolari estreme.",
    "GammaGT": "GammaGT: enzima epato-biliare; sensibile ad alcol, farmaci e steatosi.",
    "Ferro": "Ferro sierico: variabile; leggere con ferritina, transferrina e emocromo.",
    "Ferritina": "Ferritina: deposito di ferro; aumenta anche con infiammazione.",
    "Colesterolo totale": "Colesterolo totale: leggere insieme a HDL, LDL, TG e rischio cardiovascolare.",
    "Colesterolo HDL": "HDL: frazione protettiva; auspicabile più alta, specie nel profilo cardiometabolico.",
    "Trigliceridi": "Trigliceridi: influenzati da dieta, alcol, peso, digiuno e metabolismo glucidico.",
    "TSH-R": "TSH: marker ipofisario della funzione tiroidea; contestualizzare con FT3/FT4 e terapia.",
    "pH urine": "pH urinario: dipende da dieta, idratazione e condizioni metaboliche.",
    "Peso specifico urine": "Peso specifico urinario alto: urine concentrate; valutare idratazione, perdite di liquidi, sudorazione, dieta e quadro clinico.",
}

IGNORE_NAMES = {"esame richiesto", "risultato", "u.m.", "valori di riferimento", "metodica", "siero", "formula leucocitaria strumentale", "valori percentuali", "valori assolu", "urine: chimico fisico e microscopico", "es. microscopico del sedimento"}

NUM_RE = re.compile(r"^[<>]?\s*\d+(?:[\.,]\d+)?(?:\s*\*)?$")
DATE_REQUEST_RE = re.compile(r"\bdel\s+(\d{1,2}[-/.]\d{1,2}[-/.]\d{2,4})\b", re.I)
DATE_ANY_RE = re.compile(r"\b\d{1,2}[-/.]\d{1,2}[-/.]\d{2,4}\b")


def clean(s: str) -> str:
    return re.sub(r"\s+", " ", str(s).strip())


def norm_name(s: str) -> str:
    s = clean(s).lower().replace("(s)", "").strip()
    s = s.replace("ì", "i").replace("lnd", "ind")
    return s.strip(" :-")


def canonicalize_name(name: str, urine_mode: bool = False) -> Optional[str]:
    n = norm_name(name)
    if not n or n in IGNORE_NAMES:
        return None
    if urine_mode and n in {"glucosio", "emoglobina"}:
        return {"glucosio": "Glucosio urine", "emoglobina": "Emoglobina urine"}[n]
    if n in ALIASES:
        return ALIASES[n]
    # match robusto ma controllato
    for k, v in ALIASES.items():
        if n == k or n.startswith(k + " ") or k in n:
            return v
    return None


def parse_num(s: str):
    s = clean(s).replace("*", "").replace("<", "").replace(">", "").replace(",", ".")
    try:
        return float(s)
    except Exception:
        return s


def fmt_value(v) -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return ""
    if isinstance(v, (int, float)):
        return f"{v:g}".replace(".", ",")
    return str(v)


def parse_date(text: str, fallback: str = "") -> str:
    m = DATE_REQUEST_RE.search(text[:3000])
    raw = m.group(1) if m else None
    if not raw:
        # evita di prendere la data di nascita: di solito la data referto è vicina a Nr. Richiesta
        near = re.search(r"Nr\.?\s*R\w+[^\n]{0,80}", text[:3000], re.I)
        if near:
            mm = DATE_ANY_RE.search(near.group(0))
            raw = mm.group(0) if mm else None
    if not raw:
        all_dates = DATE_ANY_RE.findall(text[:3000])
        raw = all_dates[0] if all_dates else None
    if not raw:
        return fallback
    raw = raw.replace("-", "/").replace(".", "/")
    for fmt in ("%d/%m/%Y", "%d/%m/%y"):
        try:
            return datetime.strptime(raw, fmt).strftime("%d/%m/%Y")
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


def cluster_lines(words):
    rows = []
    for w in words:
        x0, y0, x1, y1, txt = w[:5]
        if not txt.strip():
            continue
        placed = False
        for row in rows:
            if abs(row["y"] - y0) <= 3.0:
                row["items"].append((x0, txt))
                row["y"] = (row["y"] + y0) / 2
                placed = True
                break
        if not placed:
            rows.append({"y": y0, "items": [(x0, txt)]})
    out = []
    for row in sorted(rows, key=lambda r: r["y"]):
        items = sorted(row["items"])
        cols = {"name": [], "value": [], "unit": [], "ref": []}
        for x, txt in items:
            if x < 235:
                cols["name"].append(txt)
            elif x < 330:
                cols["value"].append(txt)
            elif x < 430:
                cols["unit"].append(txt)
            else:
                cols["ref"].append(txt)
        out.append({"y": row["y"], **{k: clean(" ".join(v)) for k, v in cols.items()}})
    return out


def extract_pdf_structured(data: bytes, filename: str) -> Tuple[pd.DataFrame, str, str, str]:
    if fitz is None:
        st.error("PyMuPDF non installato. Aggiungi pymupdf al requirements.txt")
        return pd.DataFrame(), "", "", ""
    doc = fitz.open(stream=data, filetype="pdf")
    full_text = "\n".join(page.get_text("text") for page in doc)
    date = parse_date(full_text, filename)
    patient = parse_patient(full_text)
    rows = []

    for pno, page in enumerate(doc, start=1):
        lines = cluster_lines(page.get_text("words"))
        pending: List[dict] = []
        urine_mode = False
        pct_names = ["Neutrofili %", "Linfociti %", "Monociti %", "Eosinofili %", "Basofili %"]
        abs_names = ["Neutrofili assoluti", "Linfociti assoluti", "Monociti assoluti", "Eosinofili assoluti", "Basofili assoluti"]
        pct_idx = 0
        abs_idx = 0

        for line in lines:
            y, name_txt, val_txt, unit_txt, ref_txt = line["y"], line["name"], line["value"], line["unit"], line["ref"]
            nlow = norm_name(name_txt)
            if "urine" in nlow and "chimico" in nlow:
                urine_mode = True
            if "formula leucocitaria" in nlow:
                urine_mode = False

            # nome analita dalla colonna sinistra
            canonical = canonicalize_name(name_txt, urine_mode=urine_mode)
            if canonical:
                pending.append({"Analita": canonical, "Nome letto": name_txt, "y": y, "page": pno})

            # formule leucocitarie: valore percentuale a x 235-330 e assoluto a x 330-430/ref x>430
            if nlow in ["neutrofili", "linfociti", "monociti", "eosinofi/i", "eosinofili", "basofili"] and NUM_RE.match(val_txt):
                rows.append(make_row(pct_names[pct_idx], date, parse_num(val_txt), "%", unit_txt if unit_txt.startswith("[") else ref_txt, name_txt, pno))
                pct_idx = min(pct_idx + 1, len(pct_names)-1)
                # assoluti nello stesso rigo: spesso sono nella colonna unit/ref. Qui recuperiamo con regex da unit/ref non sempre pulito.
                abs_match = re.search(r"\d+[\.,]\d+", unit_txt)
                if abs_match and abs_idx < len(abs_names):
                    rows.append(make_row(abs_names[abs_idx], date, parse_num(abs_match.group(0)), "K/µl", ref_txt, name_txt, pno))
                    abs_idx += 1
                continue

            # valore presente nella colonna risultato. Alcuni PDF infilano anche l'unità nella colonna valore
            # es. "103 mUmin/1,73mq": prendiamo il primo numero come valore e il resto come unità.
            value_match = re.match(r"^(?P<num>[<>]?\s*\d+(?:[\.,]\d+)?(?:\s*\*)?)(?:\s+(?P<extra>.*))?$", val_txt or "")
            if value_match:
                # prendi l'analita pendente più vicina sopra, non già usata alla stessa pagina
                candidates = [p for p in pending if p["y"] <= y + 2 and not p.get("used")]
                if not candidates:
                    continue
                chosen = sorted(candidates, key=lambda p: abs(y - p["y"]))[0]
                chosen["used"] = True
                extra_unit = clean(value_match.group("extra") or "")
                unit = clean((extra_unit + " " + unit_txt).strip())
                ref = ref_txt
                rows.append(make_row(chosen["Analita"], date, parse_num(value_match.group("num")), unit, ref, chosen["Nome letto"], pno))

            # valori testuali urine, es. PAGLIA/LIMPIDO/NEGATIVO, spesso in colonna risultato
            elif urine_mode and val_txt and canonical:
                rows.append(make_row(canonical, date, val_txt, unit_txt, ref_txt, name_txt, pno))

    df = pd.DataFrame(rows)
    if df.empty:
        return df, full_text, patient, date
    # deduplica: conserva prima occorrenza plausibile
    df = df.drop_duplicates(subset=["Analita", "Data"], keep="first")
    df = add_derived(df)
    return df, full_text, patient, date


def make_row(analita, date, value, unit, ref, original, page):
    unit = clean(unit)
    ref = clean(ref).replace("[", "").replace("]", "").replace("(", "").replace(")", "")
    # Se il PDF non porta un riferimento utilizzabile, applica un range operativo interno.
    # Serve soprattutto per il peso specifico urinario, che nel PDF di prova compare senza range leggibile.
    if analita in DEFAULT_REFS and (not ref or ref.strip() in {"", "O· O", "0- 0", "0 - 0"}):
        ref = DEFAULT_REFS[analita]
    if analita in DEFAULT_UNITS and not unit:
        unit = DEFAULT_UNITS[analita]
    # sistemazioni unità frequenti OCR/PDF
    unit = unit.replace("mg/dl", "mg/dL").replace("µg/dl", "µg/dL").replace("K/µI", "K/µL").replace("M/µI", "M/µL")
    stato = stato_from_ref(value, ref)
    return {
        "Analita": analita,
        "Data": date,
        "Valore": value,
        "UM": unit,
        "Valori di riferimento": ref,
        "Stato": stato,
        "Nota": NOTES.get(analita, "Parametro da contestualizzare con quadro clinico, range del laboratorio e terapia."),
        "Riga originale": f"pag. {page}: {original}",
    }


def ref_nums(ref: str):
    nums = [float(x.replace(",", ".")) for x in re.findall(r"\d+(?:[\.,]\d+)?", ref or "")]
    return nums


def stato_from_ref(value, ref: str) -> str:
    if not isinstance(value, (int, float)) or not ref:
        return ""
    r = ref.lower().replace(" ", "")
    nums = ref_nums(ref)
    if not nums:
        return ""
    if "finoa" in r or "<" in r:
        return "ALTO" if float(value) > nums[-1] else "OK"
    if "oltre" in r or ">" in r:
        return "BASSO" if float(value) < nums[0] else "OK"
    if len(nums) >= 2:
        lo, hi = nums[0], nums[-1]
        if float(value) < lo: return "BASSO"
        if float(value) > hi: return "ALTO"
        return "OK"
    return ""


def add_derived(df: pd.DataFrame) -> pd.DataFrame:
    extra = []
    for date, sub in df.groupby("Data"):
        vals = dict(zip(sub["Analita"], sub["Valore"]))
        glu = vals.get("Glucosio") or vals.get("Glicemia")
        ins = vals.get("Insulina")
        if isinstance(glu, (int, float)) and isinstance(ins, (int, float)):
            homa = round(glu * ins / 405, 2)
            extra.append({"Analita":"HOMA-IR", "Data":date, "Valore":homa, "UM":"", "Valori di riferimento":"< 2,5", "Stato":"ALTO" if homa>2.5 else "OK", "Nota":"Indice stimato di insulino-resistenza calcolato da glicemia e insulina.", "Riga originale":"calcolo automatico"})
        tg, hdl = vals.get("Trigliceridi"), vals.get("Colesterolo HDL")
        if isinstance(tg, (int, float)) and isinstance(hdl, (int, float)) and hdl:
            ratio = round(tg/hdl, 2)
            extra.append({"Analita":"Rapporto TG/HDL", "Data":date, "Valore":ratio, "UM":"", "Valori di riferimento":"< 2", "Stato":"ALTO" if ratio>2 else "OK", "Nota":"Indice metabolico indiretto; cut-off indicativo.", "Riga originale":"calcolo automatico"})
    return pd.concat([df, pd.DataFrame(extra)], ignore_index=True) if extra else df


def extract_image_text(data: bytes) -> str:
    if Image is None or pytesseract is None:
        st.warning("Per immagini/scansioni serve pillow + pytesseract + Tesseract nel sistema. Su Streamlit Cloud è meglio caricare PDF testuali.")
        return ""
    img = Image.open(io.BytesIO(data))
    return pytesseract.image_to_string(img, lang="ita+eng")


def process_upload(uploaded) -> Tuple[pd.DataFrame, str, str, str]:
    data = uploaded.getvalue()
    name = uploaded.name
    if name.lower().endswith(".pdf"):
        return extract_pdf_structured(data, name)
    text = extract_image_text(data)
    return pd.DataFrame(), text, "Esempio", name


def delta(v1, v2, unit: str) -> str:
    if v1 == "" or v2 == "":
        return ""
    try:
        d = float(str(v2).replace(",", ".")) - float(str(v1).replace(",", "."))
        sign = "+" if d > 0 else ""
        return f"{sign}{d:g} {unit}".strip().replace(".", ",")
    except Exception:
        return ""


def build_report_table(df: pd.DataFrame, dates: List[str]) -> pd.DataFrame:
    """Costruisce la tabella finale.
    Nota: la colonna Nota viene compilata SOLO per gli esami fuori range.
    La colonna _status serve solo per colorare le righe fuori range nell'anteprima HTML.
    """
    if df.empty:
        return pd.DataFrame(columns=["_group", "_status", "Esame richiesto", "U.M", "Data 1", "Data 2", "Differenza", "Valori di Riferimento", "Nota"])
    dates = dates[:2]
    pivot = df.pivot_table(index="Analita", columns="Data", values="Valore", aggfunc="first")
    meta = df.drop_duplicates("Analita").set_index("Analita")
    out = []
    used = set()

    def row_status(n: str) -> str:
        if n not in meta.index:
            return ""
        status = str(meta.loc[n, "Stato"]).upper().strip()
        return status if status in ["ALTO", "BASSO"] else ""

    def row_note(n: str) -> str:
        status = row_status(n)
        if not status:
            return ""
        base = str(meta.loc[n, "Nota"]) if n in meta.index else ""
        return f"{status}. {base}".strip()

    for group, names in GROUPS.items():
        present = [n for n in names if n in pivot.index]
        out.append({"_group": True, "_status": "", "Esame richiesto": group, "U.M":"", "Data 1":"", "Data 2":"", "Differenza":"", "Valori di Riferimento":"", "Nota":""})
        for n in present:
            used.add(n)
            v1 = pivot.loc[n, dates[0]] if len(dates) > 0 and dates[0] in pivot.columns else ""
            v2 = pivot.loc[n, dates[1]] if len(dates) > 1 and dates[1] in pivot.columns else ""
            unit = meta.loc[n, "UM"] if n in meta.index else ""
            out.append({
                "_group": False,
                "_status": row_status(n),
                "Esame richiesto": n,
                "U.M": unit,
                "Data 1": fmt_value(v1),
                "Data 2": fmt_value(v2),
                "Differenza": delta(fmt_value(v1), fmt_value(v2), unit),
                "Valori di Riferimento": meta.loc[n, "Valori di riferimento"],
                "Nota": row_note(n),
            })

    for n in [x for x in pivot.index if x not in used]:
        v1 = pivot.loc[n, dates[0]] if len(dates) > 0 and dates[0] in pivot.columns else ""
        v2 = pivot.loc[n, dates[1]] if len(dates) > 1 and dates[1] in pivot.columns else ""
        unit = meta.loc[n, "UM"] if n in meta.index else ""
        out.append({
            "_group": False,
            "_status": row_status(n),
            "Esame richiesto": n,
            "U.M": unit,
            "Data 1": fmt_value(v1),
            "Data 2": fmt_value(v2),
            "Differenza": delta(fmt_value(v1), fmt_value(v2), unit),
            "Valori di Riferimento": meta.loc[n, "Valori di riferimento"],
            "Nota": row_note(n),
        })
    return pd.DataFrame(out)

def report_html(report_df: pd.DataFrame, patient: str, report_date: str, logo_data_url: Optional[str], d1: str, d2: str) -> str:
    logo = f'<img src="{logo_data_url}" class="logo">' if logo_data_url else '<div class="logo-placeholder">DB<br><span>Nutrition and Performance</span></div>'
    rows = []
    for _, r in report_df.iterrows():
        if r.get("_group"):
            rows.append(f'<tr class="group"><td colspan="7"><b>{r["Esame richiesto"]}</b></td></tr>')
        else:
            row_class = " abnormal" if str(r.get("_status", "")).upper() in ["ALTO", "BASSO"] else ""
            rows.append(f'<tr class="{row_class.strip()}">' + "".join([
                f'<td class="exam">{r["Esame richiesto"]}</td>',
                f'<td>{r["U.M"]}</td>',
                f'<td>{r["Data 1"]}</td>',
                f'<td>{r["Data 2"]}</td>',
                f'<td>{r["Differenza"]}</td>',
                f'<td>{r["Valori di Riferimento"]}</td>',
                f'<td class="note">{r["Nota"]}</td>',
            ]) + "</tr>")
    return f"""
<style>
.report-sheet {{background:white; color:#000; width:1180px; padding:24px 34px 38px 34px; border:1px solid #ddd; font-family:Arial, Helvetica, sans-serif;}}
.header {{display:flex; align-items:flex-start; gap:28px;}}
.logo {{width:224px; max-height:156px; object-fit:contain;}}
.logo-placeholder {{width:224px;height:130px;font-size:70px;font-weight:900;border-bottom:1px solid #9bbcff;line-height:.85;}}
.logo-placeholder span {{font-size:13px;text-transform:uppercase;font-weight:600;}}
.doctor {{border-left:2px solid #6aa0ff; padding-left:10px; font-size:14px; line-height:1.55; max-width:560px;}}
.date {{margin-left:auto; font-size:14px; padding-top:166px;}}
.patient {{margin-top:24px; margin-bottom:14px; font-size:14px;}}
table.referto {{width:100%; border-collapse:collapse; table-layout:fixed; font-size:12px;}}
table.referto th, table.referto td {{border:1px solid #111; padding:4px 7px; vertical-align:middle; word-wrap:break-word;}}
table.referto th {{font-style:italic; font-weight:400; text-align:center;}}
table.referto .group td {{background:#f1f1f1; font-weight:700; text-align:left; padding:4px 8px;}}
table.referto tr.abnormal td {{color:#b00000; font-weight:700;}}
table.referto tr.abnormal td.note {{font-weight:600;}}
table.referto td {{height:21px;}}
table.referto td:not(.exam):not(.note) {{text-align:center;}}
.exam {{padding-left:22px !important;}}
.note {{font-size:10px; line-height:1.1;}}
@media print {{
  body * {{ visibility:hidden; }}
  .report-sheet, .report-sheet * {{ visibility:visible; }}
  .report-sheet {{ position:absolute; left:0; top:0; border:0; width:100%; padding:18mm 12mm; }}
}}
</style>
<div class="report-sheet">
  <div class="header">
    <div>{logo}</div>
    <div class="doctor">{DOCTOR_BLOCK}</div>
    <div class="date">{report_date}</div>
  </div>
  <div class="patient">Sig. {patient}</div>
  <table class="referto">
    <colgroup>
      <col style="width:22%"><col style="width:8%"><col style="width:9%"><col style="width:13%"><col style="width:13%"><col style="width:13%"><col style="width:22%">
    </colgroup>
    <thead><tr><th>Esame richiesto</th><th>U.M</th><th>{d1 or 'Data 1'}</th><th>{d2 or 'Data 2'}</th><th>Differenza</th><th>Valori di<br>Riferimento</th><th>Nota</th></tr></thead>
    <tbody>{''.join(rows)}</tbody>
  </table>
</div>"""


def data_url_from_upload(file) -> Optional[str]:
    if not file:
        return None
    raw = file.getvalue()
    import base64
    ext = file.name.split(".")[-1].lower()
    mime = "image/png" if ext in ["png"] else "image/jpeg"
    return f"data:{mime};base64," + base64.b64encode(raw).decode("ascii")


# ----------------------------
# INTERFACCIA STREAMLIT
# ----------------------------
st.title("Referto comparativo analisi - layout DB")
st.caption("Versione corretta v4: note solo sui fuori range, righe rosse e range operativo per peso specifico urine.")

with st.sidebar:
    st.header("Dati referto")
    patient_manual = st.text_input("Nome paziente manuale", "")
    report_date = st.text_input("Data referto", datetime.now().strftime("%d/%m/%Y"))
    logo_file = st.file_uploader("Logo DB", type=["png", "jpg", "jpeg"], key="logo")
    st.info("Per Streamlit Cloud metti in requirements.txt: streamlit, pandas, pymupdf, pillow, pytesseract")

uploads = st.file_uploader("Carica uno o più PDF testuali del laboratorio", type=["pdf", "png", "jpg", "jpeg"], accept_multiple_files=True)

all_dfs, texts, patient_auto = [], [], "Esempio"
if uploads:
    for up in uploads:
        df, text, patient, date = process_upload(up)
        if patient and patient != "Esempio":
            patient_auto = patient
        texts.append((up.name, text[:15000]))
        if not df.empty:
            all_dfs.append(df)

if all_dfs:
    full_df = pd.concat(all_dfs, ignore_index=True)
    dates = sorted(full_df["Data"].dropna().unique().tolist(), key=lambda d: datetime.strptime(d, "%d/%m/%Y") if re.match(r"\d{2}/\d{2}/\d{4}", d) else datetime.now())
    selected = st.multiselect("Date da confrontare", dates, default=dates[:2] if len(dates) > 1 else dates[:1])
    report_df = build_report_table(full_df, selected)
    patient = patient_manual.strip() or patient_auto
    d1 = selected[0] if len(selected) > 0 else "Data 1"
    d2 = selected[1] if len(selected) > 1 else "Data 2"

    st.subheader("Anteprima referto")
    html = report_html(report_df, patient, report_date, data_url_from_upload(logo_file), d1, d2)
    st.components.v1.html(html, height=760, scrolling=True)

    st.download_button("Scarica CSV valori estratti", full_df.to_csv(index=False).encode("utf-8-sig"), "valori_estratti.csv", "text/csv")
    st.download_button("Scarica HTML stampabile", html.encode("utf-8"), "referto_comparativo.html", "text/html")

    st.subheader("Valori estratti")
    display_df = full_df.copy()
    display_df["Nota"] = display_df.apply(lambda r: r["Nota"] if str(r.get("Stato", "")).upper() in ["ALTO", "BASSO"] else "", axis=1)

    def evidenzia_fuori_range(row):
        stato = str(row.get("Stato", "")).upper()
        if stato in ["ALTO", "BASSO"]:
            return ["color: #b00000; font-weight: 700;" for _ in row]
        return ["" for _ in row]

    st.dataframe(display_df.style.apply(evidenzia_fuori_range, axis=1), use_container_width=True, hide_index=True)
    with st.expander("Tabella modificabile / controllo dati"):
        edited = st.data_editor(full_df, use_container_width=True, num_rows="dynamic", hide_index=True)
        if st.button("Rigenera anteprima con tabella modificata"):
            report_df = build_report_table(edited, selected)
            html = report_html(report_df, patient, report_date, data_url_from_upload(logo_file), d1, d2)
            st.components.v1.html(html, height=760, scrolling=True)
    with st.expander("Testo letto dai referti"):
        for name, txt in texts:
            st.markdown(f"### {name}")
            st.text(txt)
else:
    st.warning("Carica almeno un PDF testuale. Per scansioni/foto serve OCR, ma il risultato va sempre controllato.")
