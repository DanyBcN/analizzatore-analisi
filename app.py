from __future__ import annotations

import re
import fitz
import pandas as pd
import streamlit as st
from rapidfuzz import process, fuzz

st.set_page_config(page_title="Analizzatore Analisi", page_icon="🧪", layout="wide")

CUSTOM_CSS = """
<style>
.block-container {padding-top: 2rem; padding-bottom: 3rem; max-width: 1300px;}
.main-title {font-size: 2.6rem; font-weight: 800; color: #17233c; margin-bottom: 0.2rem;}
.subtitle {color: #667085; font-size: 1rem; margin-bottom: 1.5rem;}
.notice {padding: 1rem 1.2rem; border-radius: 14px; background: #fff8e6; border: 1px solid #f1d48a; color: #7a5200; margin-bottom: 1.5rem;}
.metric-card {padding: 1rem; border-radius: 18px; background: #f8fafc; border: 1px solid #e5e7eb; text-align: center;}
.metric-number {font-size: 2rem; font-weight: 800; color: #17233c;}
.metric-label {color: #667085; font-size: 0.9rem;}
.summary-box {padding: 1.2rem; border-radius: 18px; background: #eef6ff; border: 1px solid #bfdbfe; color: #17324d; line-height: 1.55;}
.footer-note {color: #667085; font-size: 0.85rem;}
</style>
"""
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

@st.cache_data
def load_ranges():
    df = pd.read_csv("range_laboratorio.csv")
    df["sesso"] = df["sesso"].fillna("ALL").str.upper()
    return df


def build_alias_index(ranges: pd.DataFrame):
    alias_to_canonical = {}
    for _, row in ranges.iterrows():
        for alias in str(row["alias"]).split("|"):
            alias_to_canonical[alias.lower().strip()] = row["analita"]
    return alias_to_canonical


def extract_text_from_pdf(uploaded_file):
    doc = fitz.open(stream=uploaded_file.read(), filetype="pdf")
    return "\n".join(page.get_text("text") for page in doc)


def normalize_number(value: str):
    return float(value.strip().replace(",", "."))

VALUE_PATTERN = re.compile(
    r"(?P<name>[A-Za-zÀ-ÿ0-9\-\s\(\)\/\.]{2,65})\s+"
    r"(?P<value>[<>]?\s*\d{1,5}(?:[\.,]\d+)?)\s*"
    r"(?P<unit>mg/dL|g/dL|ng/mL|pg/mL|mIU/L|mU/L|µU/mL|uU/mL|U/L|UI/L|%|mmol/L|fL|pg|mm/h|mg/L|µg/dL|10\^3/uL|10\^6/uL|x10\^3/uL|x10\^6/uL|mL/min/1\.73m2)?",
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
            "riga_originale": line,
        })
    return rows


def match_analyte(raw_name: str, alias_index: dict, threshold: int = 80):
    raw_name = raw_name.lower().strip()
    result = process.extractOne(raw_name, list(alias_index.keys()), scorer=fuzz.partial_ratio)
    if result and result[1] >= threshold:
        return alias_index[result[0]]
    return None


def get_reference(analita: str, sesso: str, ranges: pd.DataFrame):
    if not analita:
        return None
    sesso = sesso.upper()
    sub = ranges[(ranges["analita"] == analita) & ((ranges["sesso"] == sesso) | (ranges["sesso"] == "ALL"))]
    if sub.empty:
        return None
    specific = sub[sub["sesso"] == sesso]
    return specific.iloc[0] if not specific.empty else sub.iloc[0]


def classify_value(value, minimum, maximum):
    if pd.isna(minimum) or pd.isna(maximum):
        return "NON CLASSIFICATO"
    if value < minimum:
        return "BASSO"
    if value > maximum:
        return "ALTO"
    return "NEL RANGE"


def status_icon(status):
    return {"ALTO": "🔴", "BASSO": "🔵", "NEL RANGE": "🟢", "NON CLASSIFICATO": "🟠"}.get(status, "⚪")


def add_derived_markers(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    out = df.copy()

    def get_value(name):
        sub = out[out["Analita riconosciuto"] == name]
        return None if sub.empty else float(sub.iloc[0]["Valore"])

    glicemia = get_value("Glicemia")
    insulina = get_value("Insulina")
    trigliceridi = get_value("Trigliceridi")
    hdl = get_value("HDL")
    derived = []

    if glicemia is not None and insulina is not None:
        homa = round((glicemia * insulina) / 405, 2)
        derived.append({
            "Analita riconosciuto": "HOMA-IR", "Nome letto": "calcolato da glicemia e insulina",
            "Valore": homa, "Unità": "", "Range minimo": 0, "Range massimo": 2.5,
            "Stato": classify_value(homa, 0, 2.5),
            "Nota": "Indice stimato di insulino-resistenza; cut-off indicativo, da contestualizzare.",
            "Riga originale": "calcolo automatico"
        })

    if trigliceridi is not None and hdl is not None and hdl != 0:
        ratio = round(trigliceridi / hdl, 2)
        derived.append({
            "Analita riconosciuto": "Rapporto TG/HDL", "Nome letto": "calcolato da trigliceridi e HDL",
            "Valore": ratio, "Unità": "", "Range minimo": 0, "Range massimo": 2.0,
            "Stato": classify_value(ratio, 0, 2.0),
            "Nota": "Indice metabolico indiretto; cut-off indicativo, da contestualizzare.",
            "Riga originale": "calcolo automatico"
        })

    return pd.concat([out, pd.DataFrame(derived)], ignore_index=True) if derived else out


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
            minimum, maximum = None, None
            unita = item["unita_letta"]
            note = "Analita non riconosciuto o range assente nel database."
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
            "Riga originale": item["riga_originale"],
        })
    df = pd.DataFrame(results)
    if df.empty:
        return df
    df = add_derived_markers(df)
    df["Esito"] = df["Stato"].apply(lambda s: f"{status_icon(s)} {s}")
    order = {"ALTO": 0, "BASSO": 1, "NON CLASSIFICATO": 2, "NEL RANGE": 3}
    df["ordine"] = df["Stato"].map(order).fillna(9)
    return df.sort_values(["ordine", "Analita riconosciuto", "Nome letto"], na_position="last").drop(columns=["ordine"])


def generate_professional_summary(df: pd.DataFrame, sesso: str, eta: int, digiuno: str):
    if df.empty:
        return ("Non sono stati estratti valori strutturati dal referto. Il PDF potrebbe essere scannerizzato o non contenere testo selezionabile. "
                "In questo caso è necessario incollare manualmente il testo oppure integrare una funzione OCR.")

    altered = df[df["Stato"].isin(["ALTO", "BASSO"])]
    high = df[df["Stato"] == "ALTO"]
    low = df[df["Stato"] == "BASSO"]
    not_classified = df[df["Stato"] == "NON CLASSIFICATO"]
    lines = [f"Sono stati riconosciuti {len(df)} valori, di cui {len(altered)} fuori range/cut-off secondo il database interno utilizzato."]

    if not high.empty:
        names = ", ".join([str(x) for x in high["Analita riconosciuto"].dropna().unique()[:8]])
        lines.append(f"Valori aumentati: {names}.")
    if not low.empty:
        names = ", ".join([str(x) for x in low["Analita riconosciuto"].dropna().unique()[:8]])
        lines.append(f"Valori ridotti: {names}.")

    def altered_name(name):
        return not df[(df["Analita riconosciuto"] == name) & (df["Stato"].isin(["ALTO", "BASSO"]))].empty

    patterns = []
    if altered_name("Glicemia") or altered_name("HbA1c") or altered_name("HOMA-IR"):
        patterns.append("possibile alterazione del metabolismo glucidico, da contestualizzare con digiuno, anamnesi, farmaci e quadro clinico")
    if altered_name("LDL") or altered_name("Colesterolo totale") or altered_name("Trigliceridi") or altered_name("HDL") or altered_name("Rapporto TG/HDL"):
        patterns.append("profilo lipidico da attenzionare, con interpretazione da modulare sul rischio cardiovascolare globale")
    if altered_name("Ferritina") or altered_name("Sideremia") or altered_name("Transferrina") or altered_name("MCV") or altered_name("Emoglobina"):
        patterns.append("assetto marziale/emocromo da valutare in modo integrato, considerando infiammazione, perdite ematiche, introito e assorbimento")
    if altered_name("TSH") or altered_name("FT3") or altered_name("FT4"):
        patterns.append("funzione tiroidea da contestualizzare con sintomi, terapia, età e range del laboratorio")
    if altered_name("ALT") or altered_name("AST") or altered_name("Gamma-GT"):
        patterns.append("enzimi epatici da contestualizzare con farmaci, alcol, steatosi, attività fisica intensa e quadro metabolico")
    if altered_name("Creatinina") or altered_name("eGFR") or altered_name("Uricemia"):
        patterns.append("funzione renale/metabolismo purinico da valutare con idratazione, massa muscolare, dieta, farmaci e andamento nel tempo")
    if altered_name("Vitamina D") or altered_name("Vitamina B12") or altered_name("Folati"):
        patterns.append("possibile area carenziale vitaminica, da interpretare con dieta, integrazione, sintomi e storia clinica")
    if altered_name("PCR") or altered_name("VES"):
        patterns.append("possibile segnale infiammatorio aspecifico, non interpretabile isolatamente")

    if patterns:
        lines.append("Dalla lettura automatica emergono questi possibili ambiti di attenzione: " + "; ".join(patterns) + ".")
    if not not_classified.empty:
        lines.append(f"{len(not_classified)} valori sono stati estratti ma non classificati: possono richiedere aggiunta di alias/range nel database.")
    lines.append("La sintesi non costituisce diagnosi: va sempre verificata con range originali del laboratorio, unità di misura, anamnesi, terapia farmacologica e obiettivo clinico-nutrizionale.")
    return "\n\n".join(lines)


def build_report(df: pd.DataFrame, sesso: str, eta: int, digiuno: str):
    summary = generate_professional_summary(df, sesso, eta, digiuno)
    lines = ["REPORT DI SUPPORTO ALLA LETTURA DELLE ANALISI", "=" * 55, "", f"Sesso selezionato: {sesso}", f"Età: {eta}", f"Prelievo a digiuno: {digiuno}", "", "SINTESI", "-" * 55, summary, ""]
    if df.empty:
        return "\n".join(lines)
    altered = df[df["Stato"].isin(["ALTO", "BASSO"])]
    not_classified = df[df["Stato"] == "NON CLASSIFICATO"]
    lines += ["VALORI FUORI RANGE / CUT-OFF SUPERATI", "-" * 55]
    if altered.empty:
        lines.append("Non emergono valori fuori range tra quelli riconosciuti.")
    else:
        for _, row in altered.iterrows():
            lines.append(f"- {row['Analita riconosciuto'] or row['Nome letto']}: {row['Valore']} {row['Unità'] or ''} → {row['Stato']} | range/cut-off usato: {row['Range minimo']} - {row['Range massimo']} {row['Unità'] or ''}. Nota: {row['Nota']}")
    if not not_classified.empty:
        lines += ["", "VALORI ESTRATTI MA NON CLASSIFICATI", "-" * 55]
        for _, row in not_classified.iterrows():
            lines.append(f"- {row['Nome letto']}: {row['Valore']} {row['Unità'] or ''}")
    lines += ["", "NOTA", "-" * 55, "Questo report è uno strumento di supporto alla lettura. Non sostituisce valutazione medica, diagnosi o prescrizione terapeutica. Verificare sempre i range riportati dal laboratorio."]
    return "\n".join(lines)

st.markdown('<div class="main-title">🧪 Analizzatore referti ematochimici</div>', unsafe_allow_html=True)
st.markdown('<div class="subtitle">Dashboard di supporto alla lettura dei valori di laboratorio, con sintesi professionale e report scaricabile.</div>', unsafe_allow_html=True)
st.markdown('<div class="notice">Versione A: nessun archivio pazienti. Il PDF viene letto durante la sessione e non viene salvato dall’app.</div>', unsafe_allow_html=True)

with st.sidebar:
    st.header("Dati paziente")
    sesso = st.selectbox("Sesso biologico per range", ["ALL", "M", "F"], index=0)
    eta = st.number_input("Età", min_value=0, max_value=120, value=40)
    digiuno = st.selectbox("Prelievo a digiuno?", ["Non specificato", "Sì", "No"])
    st.divider()
    st.caption("Nota: i range sono indicativi e modificabili nel file range_laboratorio.csv.")

col_upload, col_info = st.columns([2, 1])
with col_upload:
    st.subheader("Carica referto")
    uploaded_file = st.file_uploader("Carica PDF testuale", type=["pdf"])
    pasted_text = st.text_area("Oppure incolla qui il testo del referto", height=220)
with col_info:
    st.subheader("Come usarlo")
    st.markdown("""
    1. Carica un PDF testuale oppure incolla il testo.
    2. Seleziona sesso/età.
    3. Controlla prima la sintesi.
    4. Verifica sempre i range originali del laboratorio.
    """)
    st.info("Se la tabella resta vuota, il PDF è probabilmente scannerizzato: serve OCR o testo copiato/incollato.")

text = extract_text_from_pdf(uploaded_file) if uploaded_file else (pasted_text if pasted_text.strip() else "")

if text:
    df = analyze_text(text, sesso)
    total = len(df)
    altered_count = len(df[df["Stato"].isin(["ALTO", "BASSO"])]) if not df.empty else 0
    high_count = len(df[df["Stato"] == "ALTO"]) if not df.empty else 0
    low_count = len(df[df["Stato"] == "BASSO"]) if not df.empty else 0

    st.divider()
    c1, c2, c3, c4 = st.columns(4)
    with c1: st.markdown(f'<div class="metric-card"><div class="metric-number">{total}</div><div class="metric-label">Valori riconosciuti</div></div>', unsafe_allow_html=True)
    with c2: st.markdown(f'<div class="metric-card"><div class="metric-number">{altered_count}</div><div class="metric-label">Fuori range</div></div>', unsafe_allow_html=True)
    with c3: st.markdown(f'<div class="metric-card"><div class="metric-number">{high_count}</div><div class="metric-label">Alti</div></div>', unsafe_allow_html=True)
    with c4: st.markdown(f'<div class="metric-card"><div class="metric-number">{low_count}</div><div class="metric-label">Bassi</div></div>', unsafe_allow_html=True)

    st.subheader("Sintesi scritta")
    summary = generate_professional_summary(df, sesso, eta, digiuno)
    st.markdown(f'<div class="summary-box">{summary.replace(chr(10), "<br>")}</div>', unsafe_allow_html=True)
    report = build_report(df, sesso, eta, digiuno)

    st.subheader("Valori fuori range")
    if not df.empty:
        altered = df[df["Stato"].isin(["ALTO", "BASSO"])]
        if altered.empty:
            st.success("Non emergono valori fuori range tra quelli riconosciuti.")
        else:
            st.dataframe(altered[["Esito", "Analita riconosciuto", "Valore", "Unità", "Range minimo", "Range massimo", "Nota"]], use_container_width=True, hide_index=True)
    else:
        st.warning("Nessun valore strutturato estratto.")

    with st.expander("Tabella completa"):
        if not df.empty:
            st.dataframe(df[["Esito", "Analita riconosciuto", "Nome letto", "Valore", "Unità", "Range minimo", "Range massimo", "Nota", "Riga originale"]], use_container_width=True, hide_index=True)
    with st.expander("Testo letto dal referto"):
        st.text(text[:10000] if text else "")

    st.subheader("Scarica")
    col_a, col_b = st.columns(2)
    with col_a:
        if not df.empty:
            st.download_button("Scarica tabella CSV", df.to_csv(index=False).encode("utf-8"), "analisi_estratte.csv", "text/csv", use_container_width=True)
    with col_b:
        st.download_button("Scarica report TXT", report.encode("utf-8"), "report_analisi.txt", "text/plain", use_container_width=True)
else:
    st.divider()
    st.info("Carica un PDF oppure incolla il testo del referto per generare sintesi, tabella e report.")
