# PROGRESS — book-twin-engine 0.4.0 → 0.5.0 (PROGETTO.md)

Stato ricostruibile dal disco. Aggiornato dopo ogni STEP.
Lo storico 0.2→0.4 è nel CHANGELOG e nel commit baseline `Baseline v0.4.0 (pre STEP 0)`.

## STEP 0 — Bootstrap v0.5 ✅ COMPLETATO

File toccati:
- Eliminati: `src/book_twin/llm.py`, `src/book_twin/qa.py`, `src/book_twin/analyzer.py`,
  `docs/`, `drive_tools/`, `ai_protocol/`, `tests/test_analyzer.py`.
- Modificati: `src/book_twin/cli.py` (via `ask`/`analyze`/`init-drive-layout` e import morti),
  `src/book_twin/mcp_server.py` (`build_context` portata dentro da qa.py),
  `pyproject.toml` (0.5.0; + `jsonschema`, `snowballstemmer`; script `booktwin`/`booktwin-mcp`),
  `src/book_twin/__init__.py` (0.5.0),
  `tests/test_validation.py`, `tests/test_mcp_server.py` (fixture senza FakeLLM).
- Creati: `src/book_twin/schemas/__init__.py`, `RUNBOOK.md` (placeholder), `.venv` (locale, ignorato).

### Decisioni
1. **`analyzer.py` eliminato già in STEP 0** (lo scope cita llm.py/qa.py): importava `llm.py`
   e serviva solo il comando `analyze` rimosso — tenerlo avrebbe violato "nessun import morto".
   Coerente con §1.1 (l'analisi la fa l'LLM esecutore). `tests/test_analyzer.py` eliminato con esso.
2. **Entry point rinominati `booktwin` / `booktwin-mcp`** (prima `book-twin`/`book-twin-mcp`):
   §4 e l'accettazione di STEP 0 usano `booktwin`.
3. **`build_context` spostata in `mcp_server.py`**: unica funzione di `qa.py` ancora usata
   (da `grounded_context`); è logica pura di assemblaggio contesto, in linea con §2
   ("`ask` sostituito da `booktwin context`" — il comando CLI arriva con STEP 2).
4. **Fixture test senza LLM finto**: i test di validation/mcp fabbricano gli artefatti di
   analisi scrivendo i file direttamente (in v0.5 li produce l'LLM esecutore). I test
   `test_config_marks_analyzed` e quelli sul caching dell'analyzer sono caduti col modulo.
5. **`git init` eseguito**: il repo non era versionato ma il metodo richiede commit atomici.
   Commit baseline v0.4.0 prima dello STEP 0 per un diff pulito.
6. **`validation.py`/`repository.py` non toccati** (oltre il minimo): il layout v2 e
   validate v2 sono scope di STEP 2; i riferimenti testuali a "book-twin analyze" nei
   template generati spariranno lì.

### Risultati test
- `pytest tests/` → **23 passed** (test_indexer, test_mcp_server, test_structure,
  test_utils, test_validation).
- `booktwin --version` → `booktwin 0.5.0`. ✅
- Nessun import morto: grep su `llm|qa|analyzer|init_drive|answer_question` → 0 match in `*.py`. ✅

## STEP 1 — Indexer sicuro ✅ COMPLETATO

File toccati: `src/book_twin/indexer.py`, `tests/test_indexer.py`.
- `sanitize_query(q)`: rimuove `"():^*` e backslash, quota ogni token
  (`"tok1" OR "tok2" …`) — il quoting neutralizza gli operatori FTS5
  (AND/OR/NOT/NEAR diventano parole). Stringa vuota se non resta alcun token.
- `_fts_rows` applica SEMPRE `sanitize_query` prima del MATCH; query vuota → `[]`;
  l'except residuo su OperationalError ora ritorna `[]` (rete di sicurezza, non
  più un secondo tentativo col raw input).

### Decisioni
1. **Query sanitizzata vuota → 0 risultati senza errore** (es. input di soli
   caratteri speciali): è il comportamento più semplice e coerente con "nessuna
   eccezione non gestita su input arbitrario"; documentato nel docstring.
2. La neutralizzazione degli operatori avviene per quoting del token (un token
   quotato in FTS5 è una frase, mai un operatore): niente lista-parole da
   mantenere né case-folding speciale.

### Risultati test
- `pytest tests/` → **26 passed** (23 precedenti + 3 nuovi su sanitize/ricerca).
- Accettazione: `tesi" injected`, `NEAR AND tesi`, `cita la "rivoluzione
  cognitiva"`, `perché?` → nessun crash, tutte trovano i chunk con i token
  significativi presenti nel testo. ✅

## STEP 2 — Core LLM-native ✅ COMPLETATO

File toccati:
- Nuovi: `src/book_twin/status.py` (STATUS.json §5.1: init/load/save, transizioni di
  fase, render leggibile con "prossima azione"), `src/book_twin/commit.py`
  (commit-chapter/commit-synthesis validati + render dei .md derivati),
  `tests/test_core.py` (17 test).
- Riscritti: `src/book_twin/schemas/__init__.py` (JSON Schema §5.2/§5.3),
  `src/book_twin/repository.py` (ingest layout v2, chunk ID v2, split_parts,
  pack con MANIFEST+ZIP), `src/book_twin/cli.py` (ingest/status/chapter/
  commit-chapter/commit-synthesis/index/search/context/render/pack/validate),
  `src/book_twin/validation.py` (validate v2 strutturale),
  `RUNBOOK.md` (v1 per l'LLM esecutore), `tests/test_validation.py`.
- Modificati: `src/book_twin/indexer.py` (build_context spostata qui da
  mcp_server, da aggiunta allo scope), `src/book_twin/mcp_server.py` (import).

### Decisioni
1. **Chunk ID v2 assegnati in repository.py, non in structure.py**: structure.py è
   scope di STEP 4; il re-id post `chunk_text` (`ch{order:03d}`,
   `chunk_chNNN_{contatore per capitolo:04d}`) è deterministico e tiene lo step chiuso.
2. **`chapter_hash` come campo extra nelle righe di chunks.jsonl** (non nel dataclass
   Chunk): evita di toccare models.py fuori scope.
3. **Anchors**: oltre alla presenza normalizzata (lowercase, deaccento, whitespace),
   il commit rifiuta anchor < 3 parole ("frase di 3–8 parole" di §5.2: il minimo è
   deterministico e anti-banalità; nessun massimo imposto).
4. **`chunk_summaries` opzionale nella scheda**: §4 chiede "aggiorna summary/keywords
   nei chunk" — le keywords derivano dai concetti che citano il chunk; le summary per
   chunk possono solo venire dall'LLM, quindi campo opzionale validato nello schema.
5. **commit-synthesis richiede tutti i capitoli committati** (ordine del RUNBOOK §3→§4).
6. **pack su twin parziale non cambia fase** (resta es. "analyzing": lo ZIP parziale
   deve riprendere da lì); fase "packed" solo se complete. In STEP 2 complete =
   capitoli+sintesi; STEP 5 aggiungerà author_model+verify come condizione.
7. **`verify` CLI v0.4 rimosso** (keyword-based, già deprecato in §2): torna in STEP 5
   come verifica deterministica delle citazioni. `validate` v2 è solo strutturale.
8. **`chapter` senza `--part`** stampa il capitolo intero con nota se multi-parte;
   `--parts` stampa il numero di parti; `--part i/k` esige k == parts_total.
9. **part_chars in book.config.yaml** (default 20000, opzione `--part-chars`
   all'ingest): "configurabile" di §4 risolto via config del twin.

### Risultati test
- `pytest tests/` → **42 passed** (26 → 42: +17 nuovi in test_core, test_validation
  riscritto a 5, -1 obsoleto).
- Accettazione STEP 2 (corretta: un commit per capitolo rilevato, oggi 2 sul sample):
  end-to-end ingest → 2 commit-chapter → commit-synthesis → render → pack con
  MANIFEST `complete` ✅; chunk_id inesistente → CommitError/exit≠0 col nome dell'id ✅;
  anchor assente → rifiutato col testo dell'anchor ✅; coverage incompleto → rifiutato ✅;
  re-ingest stesso testo → chunk ID e hash identici ✅; pack parziale legale ✅.
- Smoke test CLI reale: ingest + status su examples/sample_book.md OK.

## STEP 2 fix — zip round-trip ✅

Bug emersi dal round-trip reale pack→unzip→validate con esecutore terzo.
File toccati: `src/book_twin/repository.py`, `src/book_twin/commit.py`,
`RUNBOOK.md`, `tests/test_core.py`.
- pack scrive `.gitkeep` in OGNI dir vuota del twin prima dello ZIP (scelta:
  più semplice di far ricreare le dir a validate, che resterebbe puro/non
  mutante; copre anche dir svuotate dall'utente, non solo quelle del layout).
- pack allinea `book.config.yaml.status` alla fase di STATUS.json (packed sul
  completo, fase corrente sul parziale — niente più "ingested" fossile).
- STATUS.log registra anche i commit rifiutati: `_log_rejection` con timestamp
  e motivo troncato a 200 char, sia per commit-chapter sia per commit-synthesis.
- RUNBOOK §3: "dove pertinente, includi almeno 1 claim tipo inferenza per capitolo".

### Risultati test
- `pytest tests/` → **45 passed** (+3: round-trip pack→unzip→validate verde;
  config.status allineato su complete e partial; rifiuto loggato in STATUS.log).

## STEP 3 — Stemming italiano ✅ COMPLETATO

File toccati: `src/book_twin/indexer.py`, `tests/test_indexer.py`,
`tests/test_core.py` (solo assert del percorso commit).
- `get_stemmer(language)`: Snowball via `snowballstemmer`, mappa `it→italian`;
  lingue non supportate → None (no-stem, nessun errore).
- Colonne FTS `text_stem`/`summary_stem` popolate a indicizzazione; build_index
  legge `language` da book.config.yaml se non passato → il percorso di
  ricostruzione indice eseguito da commit-chapter popola gli stem anche per
  summary committate dopo l'ingest (aggiunta scope #2).
- Query: `({chapter_title text summary keywords} : (token originali)) OR
  ({text_stem summary_stem} : (token stemmati))`.
- Compat pre-STEP 3 (aggiunta scope #1): `_has_stem_columns` via PRAGMA; se
  l'indice è vecchio degrada alla ricerca senza stem e stampa su stderr la nota
  "rigenera con `booktwin index <dir>`".

### Decisioni
1. **Deaccento PRIMA dello stemming** (e anche dopo, sul risultato): garantisce
   `perché` ≡ `perche` per costruzione, a costo di una qualità di stem
   marginalmente peggiore sulle desinenze accentate. Più semplice e
   deterministico di regole ad hoc sugli accenti.
2. **Nota legacy su stderr** (non in banda nei risultati): search_index è una
   funzione di libreria; stderr non sporca l'output machine-readable.
3. **`keywords` non stemmate**: lo scope cita solo text/summary; le keywords
   sono nomi di concetti già normalizzati dall'LLM.

### Risultati test
- `pytest tests/` → **50 passed** (+5: flesso→singolare, perché≡perche,
  ranking esatto in testa, lingua `xx` no-stem senza errori, indice legacy
  degradato con nota).
- Accettazione: `interpretazioni` trova "interpretazione" ✅; `perché`/`perche`
  stesso top result ✅; match esatto resta primo ✅; twin pre-STEP 3 → nessun
  crash + suggerimento `booktwin index` ✅; stem popolati dal percorso
  commit-chapter ("ermeneutiche" trova summary committata) ✅.

## STEP 4 — Estrazione robusta ✅ COMPLETATO

File toccati: `src/book_twin/converters.py`, `src/book_twin/structure.py`,
`src/book_twin/repository.py` (integrazione + restructure), `src/book_twin/cli.py`
(`--override`, comando `restructure`), `RUNBOOK.md` (§2), `pyproject.toml`
(reportlab in dev), `tests/test_converters.py` (nuovo), `tests/test_structure.py`,
`tests/test_core.py`.

- **PDF**: de-sillabazione (`parola-\n parola`, entrambe minuscole); testatine/piè
  (righe ≤60 char ripetute ≥4 volte a inizio/fine pagina) e numeri di pagina
  isolati rimossi; `pages_map.json` (offset→pagina) costruita sulle pagine pulite
  PRIMA del join (niente marker `<!-- page:N -->` nel canonico); `page_start/page_end`
  popolati nei chunk via localizzazione best-effort del prefisso/suffisso del chunk.
- **HTML/EPUB**: `<table>` → tabella Markdown (celle non duplicate come blocchi);
  `<sup><a>` → marcatore `[n.X]` + testo nota risolto best-effort (stesso documento)
  in `canonical/notes/notes.md`; `<sup>` senza link conservato come `^contenuto`
  (`10^2` sopravvive, con fix dello spazio da get_text).
- **split_chapters v2**: fusione SOLO per divisori (<200 char e nessuna riga di
  corpo >80 char); ogni merge e ogni drop FRONTBACK loggato (events→STATUS.log e
  processing_log); FRONTBACK_RE esteso (letture di approfondimento, indici
  analitici/figure/tavole, abbreviazioni, glossario, crediti, bibliography…).
- **Override** `chapters.override.yaml` (`actions:` merge/split_at/rename/drop/
  undrop) con `ingest --override` o `booktwin restructure`.

### Decisioni
1. **Restructure/override solo a zero capitoli committati** (aggiunta scope):
   rifiuto con messaggio che rimanda a `ingest --force --override`.
2. **Override copiato nel twin** come `chapters.override.yaml` e incluso negli
   hash del MANIFEST (aggiunta scope): riproducibilità (libro, engine, override).
3. **Note**: estrazione best-effort dichiarata — risolte solo entro lo stesso
   documento spine; href cross-file lasciano il solo marcatore `[n.X]`.
4. **Numerazione nelle azioni override**: si riferisce alla numerazione CORRENTE
   al momento dell'azione (rinumerazione dopo ogni azione); documentato nel RUNBOOK.
5. **Undrop** reinserisce nella posizione originale (tracking `_seq` dei segmenti).
6. **`min_chapter_chars` rimosso** dalla firma di split_chapters: sostituito dalla
   regola divisori; i call-site non lo passavano.
7. **Esponenti**: lo spazio introdotto da `get_text(" ")` prima di `^` viene
   compresso (`10 ^2` → `10^2`).

### Risultati test
- `pytest tests/` → **66 passed** (50 → 66: +5 converters, +7 structure, +4 core).
- Accettazione: sample → **3 capitoli** (ch003 "Il dialogo" non più inghiottito) ✅;
  tabella HTML → markdown ✅; `10<sup>2</sup>` → `10^2` ✅; nota `<sup><a>12</a></sup>`
  → testo pulito con `[n.12]` + nota estratta ✅; PDF sintetico (reportlab):
  sillabazione ricomposta, testatina rimossa, pages_map corretta, chunk con
  page_start/page_end ✅; drop "Indice" nel log ✅; restructure bloccato dopo commit ✅;
  override nel twin e nel MANIFEST ✅.

## PROSSIMO STEP
STEP 5 — Author model + verify v2: commit-author-model (§5.4), verify.py
deterministico + verify_report.md con spot-check, pack che esige author_model
e verify per dichiarare complete.
