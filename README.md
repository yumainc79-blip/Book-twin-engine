# Book Twin Engine

Book Twin Engine trasforma un libro leggibile in una cartella AI-native orientata al dialogo: Markdown, JSONL, indice SQLite FTS, analisi, modello dell'autore, protocollo dialogico, riflessione del lettore, personas e prompt.

L'obiettivo non è produrre un semplice riassunto. L'obiettivo è creare un **Book Twin dialogico**: una rappresentazione strutturata del libro che permetta di parlare con un autore simulato, discutere idee, limiti teorici, applicazioni personali e fraintendimenti possibili.

## Principio centrale

Il Book Twin non finge che l'autore reale sia presente. Genera invece una **simulazione testualmente vincolata**.

Formula consigliata:

```text
Sono [Nome Autore], in simulazione testualmente vincolata: parliamo.
```

Questa formula permette il dialogo in prima persona, ma mantiene chiara la distinzione tra autore reale e voce simulata.

## Installazione

```powershell
python -m venv .venv
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e .
```

## Uso rapido

```powershell
book-twin ingest .\examples\sample_book.md --out .\output\sample_book --force
book-twin search .\output\sample_book "tesi centrale"
book-twin ask .\output\sample_book "Qual è la tesi centrale?"
```

Senza provider LLM, `ask` mostra il contesto recuperato e il prompt. Con Ollama o OpenAI-compatible genera risposte.

## Uso con Ollama

```powershell
ollama run llama3.1
book-twin analyze .\output\sample_book --provider ollama --model llama3.1
book-twin ask .\output\sample_book "Parliamo della tesi centrale" --provider ollama --model llama3.1 --mode simulated_author
```

## Formati supportati

- TXT
- Markdown
- HTML
- DOCX
- PDF digitale con testo estraibile
- EPUB
- MOBI/AZW3 se `ebook-convert` di Calibre è installato localmente

## Struttura Book Twin generata

```text
book_name/
  README.md
  llms.txt
  prompt_for_ai.md
  book.config.yaml

  canonical/
    book.md
    book.json
    chapters/
    pages/
    figures/
    tables/
    notes/

  analysis/
    00_tesi_centrale.md
    01_mappa_del_libro.md
    02_riassunto_completo.md
    03_argomentazione.md
    04_concetti_chiave.md
    05_glossario.md
    06_domande_profonde.md
    07_limiti_e_critiche.md
    08_collegamenti_esterni.md
    chapters/

  knowledge/
    chunks.jsonl
    claims.jsonl
    concepts.jsonl
    entities.jsonl
    relations.jsonl
    citations.jsonl
    timeline.jsonl
    questions.jsonl
    objections.jsonl
    applications.jsonl
    book_graph.json
    retrieval.sqlite

  author_model/
    author_model.md

  dialogue/
    dialogue_protocol.md
    entrypoints.md

  reader_reflection/
    reader_reflection.md

  personas/
    main_dialogue_persona.md
    faithful_exegete.md
    simulated_author.md
    critical_reviewer.md
    socratic_tutor.md

  prompts/
    dialogue_integrated.md
    first_person_author.md
    answer_grounded.md
    analyze_chapter.md
    extract_claims.md
    extract_concepts.md
    synthesize_book.md
    dialogue_as_author.md

  sessions/
    README.md

  exports/
    obsidian/
    study_guide.md
    anki_flashcards.csv

  logs/
    processing_log.md
```

## Cartella `ai_protocol/`

La repo contiene anche una cartella `ai_protocol/` con istruzioni leggibili da qualsiasi AI:

```text
ai_protocol/
  MASTER_PROMPT.md
  BOOK_TWIN_SCHEMA.md
  DRIVE_OUTPUT_STRUCTURE.md
  QUALITY_RULES.md
  PROMPT_FOR_AI_TEMPLATE.md
```

Questi file servono quando vuoi dare la repo a ChatGPT, Claude, Gemini o altra AI e farle creare un Book Twin direttamente in Drive o in uno ZIP.

## Regole anti-allucinazione

Ogni risposta deve distinguere:

1. direttamente supportato dal testo;
2. inferito dal testo;
3. estensione speculativa.

La modalità autore simulato parla in prima persona, ma deve dichiarare la simulazione testualmente vincolata.
