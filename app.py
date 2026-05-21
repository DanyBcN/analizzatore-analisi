from __future__ import annotations

import re
import fitz
import pandas as pd
import streamlit as st
from rapidfuzz import process, fuzz


st.set_page_config(
    page_title="Analizzatore Analisi",
    layout="wide"
)


# =========================
# LETTURA RANGE
# =========================

@st.cache_data
def load_ranges():
    df = pd.read_csv("range_laboratorio.csv")
    df["sesso"] = df["sesso"].fillna("ALL").str.upper()
    return df


def build_alias_index(ranges: pd.DataFrame):
    alias_to_canonical = {}

    for _, row in ranges.iterrows():
        aliases = str(row["alias"]).split("|")
        for alias in aliases:
            alias_to_canonical[alias.lower().strip()] = row["analita"]

    return alias_to_canonical


# =========================
# LETTURA PDF
# =========================

def extract_text_from_pdf(uploaded_file):
    doc = fitz.open(stream=uploaded_file.read(), filetype="pdf")
    text = []

    for page in doc:
        text.append(page.get_text("text"))

    return "\n".join(text)


# =========================
# ESTRAZIONE VALORI
# =========================

def normalize_number(value: str):
    value = value.strip()
    value = value.replace(",", ".")
    return float(value)


VALUE_PATTERN = re.compile(
    r"(?P<name>[A-Za-zÀ-ÿ0-9\-\s\(\)\/\.]{2,60})\s+"
    r"(?P<value>[<>]?\s*\d{1,5}(?:[\.,]\d+)?)\s*"
    r"(?P<unit>mg/dL|g/dL|ng/mL|pg/mL|mIU/L|mU/L|µU/mL|uU/mL|U/L|UI/L|%|mmol/L|10\^3/uL|10\^6/uL|x10\^3/uL|x10\^6/uL|mL/min/1\.73m2)?",
    re.IGNORECASE,
)


def extract_lab_values(text: str):
    rows = []

    for line in text.splitlines():
        line = re.sub(r"\s+", " ", line.strip())

        if not line or len(line) < 4:
            continue

        match = VALUE_PATTERN.search(line)

        if not match:
            continue

        raw_value = match.group("value").replace(" ", "")

        if raw_value.startswith("<") or raw_value.startswith(">"):
            raw_value = raw_value[1:]

        try:
            value = normalize_number(raw_value)
        except ValueError:
            continue

        rows.append({
            "nome_letto": match.group("name").strip(" :-"),
            "valore": value,
            "unita_letta": match.group("unit"),
            "riga_originale": line
        })

    return rows


# =========================
# MATCH ANALITA
# =========================

def match_analyte(raw_name: str, alias_index: dict, threshold: int = 80):
    raw_name = raw_name.lower().strip()
    choices = list(alias_index.keys())

    result = process.extractOne(raw_name, choices, scorer=fuzz.partial_ratio)

    if result and result[1] >= threshold:
        return alias_index[result[0]]

    return None


def get_reference(analita: str, sesso: str, ranges: pd.DataFrame):
    if not analita:
        return None

    sesso = sesso.upper()

    sub = ranges[
        (ranges["analita"] == analita) &
        ((ranges["sesso"] == sesso) | (ranges["sesso"] == "ALL"))
    ]

    if sub.empty:
        return None

    specific = sub[sub["sesso"] == sesso]

    if not specific.empty:
        return specific.iloc[0]

    return sub.iloc[0]


def classify_value(value, minimum, maximum):
    if pd.isna(minimum) or pd.isna(maximum):
        return "NON CLASSIFICATO"

    if value < minimum:
        return "BASSO"

    if value > maximum:
        return "ALTO"

    return "NEL RANGE"


# =========================
# CALCOLI DERIVATI
# =========================

def add_derived_markers(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df

    out = df.copy()

    def get_value(name):
        sub = out[out["Analita riconosciuto"] == name]
        if sub.empty:
            return None
        return float(sub.iloc[0]["Valore"])

    glicemia = get_value("Glicemia")
    insulina = get_value("Insulina")
    trigliceridi = get_value("Trigliceridi")
    hdl = get_value("HDL")

    derived = []

    if glicemia is not None and insulina is not None:
        homa = round((glicemia * insulina) / 405, 2)
        derived.append({
            "Analita riconosciuto": "HOMA-IR",
            "Nome letto": "calcolato da glicemia e insulina",
            "Valore": homa,
            "Unità": "",
            "Range minimo": 0,
            "Range massimo": 2.5,
            "Stato": classify_value(homa, 0, 2.5),
            "Nota": "Indice stimato di insulino-resistenza; cut-off indicativo, da contestualizzare.",
            "Riga originale": "calcolo automatico"
        })

    if trigliceridi is not None and hdl is not None and hdl != 0:
        ratio = round(trigliceridi / hdl, 2)
        derived.append({
            "Analita riconosciuto": "Rapporto TG/HDL",
            "Nome letto": "calcolato da trigliceridi e HDL",
            "Valore": ratio,
            "Unità": "",
            "Range minimo": 0,
            "Range massimo": 2.0,
            "Stato": classify_value(ratio, 0, 2.0),
            "Nota": "Indice metabolico indiretto; cut-off indicativo, da contestualizzare.",
            "Riga originale": "calcolo automatico"
        })

    if derived:
        out = pd.concat([out, pd.DataFrame(derived)], ignore_index=True)

    return out


# =========================
# ANALISI
# =========================

def analyze_text(text: str, sesso: str):
    ranges = load_ranges()
    alias_index = build_alias_index(ranges)

    extracted = extract_lab_values(text)
    results = []

    for item in extracted:
        analita = match_analyte(item["nome_letto"], alias_index)
        ref = get_reference(analita, sesso, ranges)

        if ref is not None:
            minimum = float(ref["min"])
            maximum = float(ref["max"])
            unita = item["unita_letta"] or ref["unita"]
            note = ref["note"]
            status = classify_value(item["valore"], minimum, maximum)
        else:
            minimum = None
            maximum = None
            unita = item["unita_letta"]
            note = "Analita non riconosciuto o range assente"
            status = "NON CLASSIFICATO"

        results.append({
            "Analita riconosciuto": analita,
            "Nome letto": item["nome_letto"],
            "Valore": item["valore"],
            "Unità": unita,
            "Range minimo": minimum,
            "Range massimo": maximum,
            "Stato": status,
            "Nota": note,
            "Riga originale": item["riga_originale"]
        })

    df = pd.DataFrame(results)

    if df.empty:
        return df

    df = add_derived_markers(df)

    order = {
        "ALTO": 0,
        "BASSO": 1,
        "NON CLASSIFICATO": 2,
        "NEL RANGE": 3
    }

    df["ordine"] = df["Stato"].map(order).fillna(9)
    df = df.sort_values(["ordine", "Analita riconosciuto", "Nome letto"], na_position="last")
    df = df.drop(columns=["ordine"])

    return df


def build_report(df: pd.DataFrame):
    if df.empty:
        return "Non sono riuscito a estrarre valori strutturati dal referto."

    altered = df[df["Stato"].isin(["ALTO", "BASSO"])]
    not_classified = df[df["Stato"] == "NON CLASSIFICATO"]

    lines = []
    lines.append("REPORT DI SUPPORTO ALLA LETTURA DELLE ANALISI")
    lines.append("")
    lines.append("Nota: questo report non formula diagnosi. I dati vanno interpretati insieme al quadro clinico, ai range del laboratorio, ai farmaci e all'anamnesi.")
    lines.append("")

    if altered.empty:
        lines.append("Non emergono valori fuori range tra quelli riconosciuti.")
    else:
        lines.append("VALORI FUORI RANGE / CUT-OFF SUPERATI:")
        for _, row in altered.iterrows():
            lines.append(
                f"- {row['Analita riconosciuto'] or row['Nome letto']}: {row['Valore']} {row['Unità'] or ''} "
                f"→ {row['Stato']} | range/cut-off usato: {row['Range minimo']} - {row['Range massimo']} {row['Unità'] or ''}. "
                f"Nota: {row['Nota']}"
            )

    if not not_classified.empty:
        lines.append("")
        lines.append("VALORI ESTRATTI MA NON CLASSIFICATI:")
        for _, row in not_classified.iterrows():
            lines.append(
                f"- {row['Nome letto']}: {row['Valore']} {row['Unità'] or ''}"
            )

    return "\n".join(lines)


# =========================
# INTERFACCIA
# =========================

st.title("Analizzatore referti ematochimici")
st.caption("Supporto alla lettura dei valori di laboratorio. Non sostituisce valutazione clinica o diagnosi.")

st.warning(
    "Versione A: nessun archivio pazienti. Il PDF viene letto solo durante la sessione e non viene salvato dall'app."
)

with st.sidebar:
    st.header("Dati paziente")
    sesso = st.selectbox("Sesso biologico per range", ["ALL", "M", "F"], index=0)
    eta = st.number_input("Età", min_value=0, max_value=120, value=40)
    digiuno = st.selectbox("Prelievo a digiuno?", ["Non specificato", "Sì", "No"])

st.subheader("Carica referto")

uploaded_file = st.file_uploader("Carica PDF testuale", type=["pdf"])
pasted_text = st.text_area("Oppure incolla qui il testo del referto", height=250)

text = ""

if uploaded_file:
    text = extract_text_from_pdf(uploaded_file)
elif pasted_text.strip():
    text = pasted_text

if text:
    with st.expander("Testo letto dal referto"):
        st.text(text[:8000])

    df = analyze_text(text, sesso)

    st.subheader("Tabella valori")
    st.dataframe(df, use_container_width=True)

    st.subheader("Valori fuori range")
    if not df.empty:
        altered = df[df["Stato"].isin(["ALTO", "BASSO"])]
        st.dataframe(altered, use_container_width=True)

    st.subheader("Report")
    report = build_report(df)
    st.text_area("Report generato", report, height=350)

    csv = df.to_csv(index=False).encode("utf-8")
    st.download_button(
        "Scarica tabella CSV",
        csv,
        "analisi_estratte.csv",
        "text/csv"
    )

    st.download_button(
        "Scarica report TXT",
        report.encode("utf-8"),
        "report_analisi.txt",
        "text/plain"
    )
else:
    st.info("Carica un PDF oppure incolla il testo del referto.")
