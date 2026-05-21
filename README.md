# Analizzatore Analisi - Versione A

App Streamlit per leggere referti ematochimici in PDF testuale o testo incollato.

## Caratteristiche

- Nessun archivio pazienti
- Nessun salvataggio PDF da parte dell'app
- Estrazione valori da PDF/testo
- Confronto con range modificabili in `range_laboratorio.csv`
- Report scaricabile TXT
- Tabella scaricabile CSV

## File principale

`app.py`

## Avvio locale

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Deploy online

Caricare questi file in una repository GitHub e collegare la repository a Streamlit Community Cloud.
