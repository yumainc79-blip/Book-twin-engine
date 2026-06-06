# Book Twin Engine

Book Twin Engine trasforma un libro leggibile in una cartella AI-native: Markdown, JSONL, indice SQLite FTS, analisi, concetti, claim, personas e prompt.

L'obiettivo non è produrre un semplice riassunto, ma creare un **Book Twin**: una rappresentazione strutturata del libro che possa essere interrogata da AI diverse in modo citabile, navigabile e controllato.

## Stato

Questa è una prima versione funzionante.

Funziona già per:

- TXT
- Markdown
- HTML
- DOCX
- PDF digitale con testo estraibile
- EPUB
- MOBI/AZW3 se `ebook-convert` di Calibre è installato localmente

Funzioni già presenti:

- ingest di un libro;
- ricostruzione cartella standard;
- segmentazione euristica in capitoli;
- chunking citabile;
- generazione file Markdown/JSONL;
- indice SQLite FTS5;
- ricerca;
- risposta grounded con contesto recuperato;
- backend LLM opzionali: `none`, `openai-compatible`, `ollama`.

## Installazione

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

Su Windows PowerShell:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e .
```

## Uso rapido

```bash
book-twin ingest examples/sample_book.md --out output/sample_book --force
book-twin index output/sample_book
book-twin search output/sample_book "tesi centrale"
book-twin ask output/sample_book "Qual è la tesi centrale?"
```

## Uso con Ollama

```bash
ollama run llama3.1
book-twin analyze output/sample_book --provider ollama --model llama3.1
book-twin ask output/sample_book "Che cosa sostiene il capitolo 1?" --provider ollama --model llama3.1
```

## Uso con API OpenAI-compatible

```bash
export OPENAI_API_KEY="..."
export OPENAI_BASE_URL="https://api.openai.com/v1"
book-twin analyze output/sample_book --provider openai --model gpt-4o-mini
book-twin ask output/sample_book "Quali sono i concetti principali?" --provider openai --model gpt-4o-mini
```

## Struttura generata

```text
book_name/
  README.md
  llms.txt
  book.config.yaml
  canonical/
  analysis/
  knowledge/
  indexes/
  personas/
  prompts/
  exports/
  logs/
```

## Principio anti-allucinazione

Ogni risposta dovrebbe distinguere tra:

1. direttamente supportato dal testo;
2. inferito dal testo;
3. speculativo.

La prima versione implementa già retrieval e citazione dei chunk. Le modalità autore simulato/critico/tutor sono presenti come personas e prompt; il server MCP completo sarà lo step successivo.
