# Changelog

## 0.5.0 — in lavorazione (architettura LLM-native, vedi PROGETTO.md)

### STEP 2 — Core LLM-native

- Layout output v2 (PROGETTO.md §3): `STATUS.json` (macchina a stati per
  capitolo/fase con hash), `book.config.yaml` essenziale, `canonical/`,
  `analysis/chapters/*.json` + `analysis/rendered/`, `knowledge/*.jsonl`,
  niente placeholder di analisi all'ingest.
- ID stabili: `chapter_id = chNNN`, chunk `chunk_chNNN_MMMM` scopati per
  capitolo; re-ingest di testo invariato → ID invariati. Hash del capitolo nei
  chunk e in STATUS.
- Nuovi comandi: `status` (fase + prossima azione), `chapter NNN [--part i/k]`
  (lettura integrale a parti, anti-troncamento), `commit-chapter` e
  `commit-synthesis` (validazione JSON Schema + chunk_ids esistenti e del
  capitolo giusto + anchors verificate nel testo + coverage completo + tesi ≠
  riassunto), `context` (contesto assemblato, la risposta la dà l'LLM in chat),
  `render` (md derivati dal JSON), `pack` (MANIFEST.json + ZIP
  complete|partial), `validate` v2 (strutturale).
- `RUNBOOK.md` v1 per l'LLM esecutore: setup, ingest, checkpoint struttura,
  loop capitoli con commit validati, sintesi, pack; regola dello ZIP parziale
  ripristinabile.
- `build_context` spostata in `indexer.py` (usata da CLI `context` e MCP).

### STEP 4 — Estrazione robusta

- PDF: de-sillabazione, rimozione testatine/piè di pagina ripetuti e numeri di
  pagina isolati; `canonical/pages_map.json` (offset→pagina) e `page_start`/
  `page_end` popolati nei chunk; niente più marker pagina nel testo canonico.
- HTML/EPUB: le tabelle diventano tabelle Markdown; le note `<sup><a>` diventano
  marcatori `[n.X]` con testo estratto (best-effort) in `canonical/notes/`;
  gli esponenti `<sup>` senza link sopravvivono come `10^2`.
- Segmentazione: la fusione automatica si applica solo ai veri divisori
  (<200 char senza paragrafo di corpo) — i capitoli brevi non vengono più
  inghiottiti; ogni fusione e ogni drop di paratesto è loggato in STATUS.log.
- Paratesto: pattern estesi (letture di approfondimento, indici analitici,
  abbreviazioni, glossario, crediti…) — sicuri perché reversibili con `undrop`.
- Nuovo `chapters.override.yaml` (merge/split_at/rename/drop/undrop) con
  `ingest --override` o `booktwin restructure <dir> --override file`; consentito
  solo a zero capitoli committati; l'override applicato è copiato nel twin e
  incluso nel MANIFEST (riproducibilità: libro + engine + override).

### STEP 3 — Stemming italiano

- Ricerca con stemming Snowball per l'italiano: colonne FTS `text_stem` e
  `summary_stem`, query su colonne originali OR stem dei token su colonne
  stemmate. `interpretazioni` trova "interpretazione"; `perché` ≡ `perche`.
- Parametrico su `language` (da book.config.yaml): lingue non supportate →
  comportamento precedente senza stemming, senza errori.
- Indici pre-STEP 3: rilevati automaticamente, la ricerca degrada senza
  crash e suggerisce `booktwin index <dir>` per rigenerare.
- Le colonne stem vengono popolate anche quando l'indice è ricostruito da
  commit-chapter (summary committate dopo l'ingest).

### STEP 2 fix — zip round-trip

- `pack` scrive `.gitkeep` nelle directory vuote: il twin estratto dallo ZIP
  passa `validate` (le dir vuote non sopravvivono allo ZIP).
- `pack` allinea `book.config.yaml.status` alla fase di STATUS.json.
- STATUS.log registra anche i commit rifiutati (timestamp + motivo sintetico).
- RUNBOOK §3: raccomandato ≥1 claim `tipo: "inferenza"` per capitolo.

### STEP 1 — Indexer sicuro

- Nuova `sanitize_query`: ogni query è ripulita dai caratteri sintattici FTS5
  (`"():^*` e backslash) e i token vengono quotati (`"tok1" OR "tok2" …`), così
  gli operatori AND/OR/NOT/NEAR diventano parole normali. Applicata sempre prima
  del MATCH: nessun crash su input arbitrario (virgolette sbilanciate, operatori,
  punteggiatura). Query senza token utili → 0 risultati, senza errore.

### STEP 0 — Bootstrap v0.5

- **Rimossi** `llm.py` (client API Anthropic/OpenAI/Ollama), `qa.py` (comando `ask`),
  `analyzer.py` (comando `analyze`): l'analisi la farà l'LLM esecutore in sandbox
  seguendo `RUNBOOK.md`; nessuna chiamata API dall'engine.
- **Rimossi** `docs/` (PWA), `drive_tools/` (Apps Script), `ai_protocol/`, comando
  `init-drive-layout`: distribuzione e protocollo escono dall'engine.
- Entry point rinominati: `booktwin` e `booktwin-mcp` (prima `book-twin`/`book-twin-mcp`).
- Nuove dipendenze: `jsonschema`, `snowballstemmer`. Versione → 0.5.0.
- Skeleton: `src/book_twin/schemas/` e `RUNBOOK.md` placeholder.
- `build_context` spostata da `qa.py` a `mcp_server.py`; test adattati (le fixture
  fabbricano gli artefatti di analisi senza LLM finto).

## 0.4.0 — Server MCP

- Nuovo server MCP (`book-twin-mcp`): espone un Book Twin a un client MCP (Claude Desktop,
  Claude Code, ...) per l'uso diretto da una LLM in chat, con retrieval reale e senza incollare file.
  - tools: `search`, `context`, `chapter`, `chapters`, `concepts`, `claims`, `analysis`;
  - resources: `book://metadata`, `book://analysis/{section}`, `book://chapter/{ref}`;
  - prompts: `dialogue_integrated`, `simulated_author`.
  - Dipendenza opzionale: `pip install "book-twin-engine[mcp]"`. Extra `[embeddings]` per la
    ricerca semantica locale.
- Rimosso `--copyright-safe` e il campo `copyright_safe`: per l'uso personale non offriva alcuna
  protezione reale (il testo integrale resta comunque in `canonical/` e nei chunk) e aggiungeva
  solo rumore.

## 0.3.1 — Tracciabilità della versione

- Nuovo `book-twin --version` (alias `-V`): mostra la versione dell'engine.
- L'`ingest` registra `engine_version` e `generated_at` (UTC) in `book.config.yaml`, così ogni
  Book Twin sa da quale engine è stato prodotto. Il valore sopravvive ai successivi `analyze`.

## 0.3.0 — Estrazione robusta, analisi LLM reale, validazione e retrieval ibrido

### Estrazione
- `read_epub` legge in ordine di spine ed estrae l'autore dai metadati DC.
- Pulizia HTML/EPUB: rimozione note numeriche e `<sup>`, blocchi solo-numero scartati,
  whitespace compresso. `split_chapters` consapevole del livello dei titoli: niente più
  capitoli duplicati o frammentati (es. Faggin 146→17, Barbero 21, 0 artefatti).

### Analisi
- Rimosso il vecchio `top_terms()` ingenuo. `analyze_book` ora produce schede di capitolo in
  JSON strutturato (sezioni distinte: riassunto ≠ tesi) con i sottotitoli reali come àncore
  anti-allucinazione.
- Popola `summary` e `keywords` nei chunk e ricostruisce l'indice.
- Sintesi di libro e estrazione entità/timeline/relazioni in fasi dedicate; popola tutti i
  JSONL di `knowledge/`.
- Nuovo client `anthropic`; flag `--require-llm/--no-require-llm` (default: esige un LLM reale,
  niente degrado silenzioso) e `--only-missing` (cache delle schede).

### Validazione
- Nuovo comando `validate`: schema dei file + regole di qualità 7-10 (simulazione dichiarata,
  distinzione testo/inferenza/speculazione, domande profonde, limiti e trappole), niente stub
  residui né schede duplicate. Esce con codice ≠0 se fallisce.
- Nuovo comando `verify`: controlla che i concetti analizzati compaiano davvero nel testo
  sorgente del capitolo (stem-aware, italiano), riportando il rapporto documentati/inferiti.

### Retrieval
- Ricerca ibrida FTS5/BM25 + embedding locali opzionali (sentence-transformers), fusione
  Reciprocal Rank Fusion. Fallback morbido alla sola FTS se gli embedding non sono disponibili.
  Mai un'API esterna obbligatoria. Flag `--embeddings/--no-embeddings` e `--hybrid/--no-hybrid`.

### Prompt e personas
- Guard "autore reale e vivente": vietato attribuire all'autore citazioni/opinioni/biografia
  non presenti nel testo.
- Distinzione esplicita a 3 livelli + citazione dell'ID del chunk nei prompt di dialogo.
- Rimosso il linguaggio clinico fuori contesto.

## 0.2.0 — Dialogue-first Book Twin

- Aggiunto `prompt_for_ai.md` nella root di ogni Book Twin.
- Aggiunto `author_model/author_model.md`.
- Aggiunto `dialogue/dialogue_protocol.md`.
- Aggiunto `dialogue/entrypoints.md`.
- Aggiunto `reader_reflection/reader_reflection.md`.
- Aggiunto `personas/main_dialogue_persona.md`.
- Aggiunti prompt per autore simulato in prima persona.
- Aggiunti `knowledge/objections.jsonl` e `knowledge/applications.jsonl`.
- Rafforzata modalità `ask` con protocollo dialogico integrato.
- Aggiunta cartella `ai_protocol/` per far usare la repo direttamente a una AI.
