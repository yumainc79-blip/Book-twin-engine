# PROGETTO — Book Twin Engine v0.5 → Author Twin

> Fonte di verità per l'implementazione. Eseguire per STEP atomici, nell'ordine dato.
> Base di partenza: repo `book-twin-engine` v0.4.0 (riuso stimato ~60%).
> Versione progetto: 1.0 — giugno 2026.

---

## 0. Obiettivo e flusso d'uso

**Flusso target (fase 1 — Book Twin):**

1. L'utente incolla a un LLM con sandbox di esecuzione (Claude.ai, Claude Code, ChatGPT) due file: il libro (epub/pdf/docx/html/md) e lo ZIP dell'engine.
2. L'LLM estrae l'engine, legge `RUNBOOK.md` e lo esegue: ingest deterministico, poi analisi capitolo per capitolo fatta **dall'LLM stesso** (niente API esterne), con commit validati.
3. L'LLM restituisce uno ZIP: il **Book Twin**, completo o parziale-ripristinabile.
4. Lo ZIP viene usato in una nuova conversazione (o via MCP) per il **dialogo con l'autore simulato**, testualmente vincolato.

**Flusso target (fase 2 — Author Twin):** più Book Twin dello stesso autore vengono composti (mai fusi) in un layer che aggiunge conoscenza cross-libro (invarianti, traiettorie, tensioni) per un dialogo diacronicamente fedele.

**Vincolo accettato:** l'LLM esecutore deve avere esecuzione codice + filesystem. Senza sandbox il flusso di *generazione* non esiste (il *consumo* del twin invece funziona anche senza, vedi STEP 6).

---

## 1. Decisioni architetturali vincolanti

1. **L'engine è un toolkit deterministico.** Fa solo: estrazione, segmentazione, indicizzazione, validazione, gestione stato, packaging. **L'analisi la fa l'LLM esecutore** seguendo `RUNBOOK.md`. Nessuna chiamata API dall'engine.
2. **Fedeltà imposta in scrittura, non misurata dopo.** Ogni artefatto di analisi entra solo via `booktwin commit-*`, validato con JSON Schema (libreria `jsonschema`). Ogni claim porta `chunk_ids` esistenti e `anchors` testuali verificate deterministicamente nei chunk citati. Commit fallito = messaggio d'errore esatto, l'LLM corregge e riprova.
3. **Anti-troncamento esplicito.** L'LLM legge i capitoli interi via `booktwin chapter NNN [--part i/k]`. La scheda dichiara `coverage` (parti lette / parti totali); il commit rifiuta coverage incompleto. Mai più analisi su testo troncato in silenzio.
4. **Stato ripristinabile.** `STATUS.json` è una macchina a stati per capitolo/fase, con hash. Uno ZIP parziale è legale: ricaricato con l'engine in una sessione nuova, riprende da dove era.
5. **ID stabili.** Chunk ID scopati per capitolo: `chunk_ch004_0012`. Re-ingest di testo invariato → ID invariati (le citazioni delle sessioni passate non si rompono). Hash del capitolo registrato in STATUS e nei chunk.
6. **Un solo entrypoint di consumo:** `START_DIALOGUE.md` (consolida prompt_for_ai + llms.txt + protocollo + persona). Le persona alternative diventano appendici dello stesso file.
7. **MCP resta** come modalità di consumo opzionale (la logica pura di v0.4 era buona: si porta sul nuovo layout).
8. **JSON è la fonte di verità dell'analisi** (`analysis/chapters/*.json`, `analysis/synthesis.json`); il Markdown leggibile è derivato con `booktwin render`.
9. **Lingua:** italiano come default; lo stemming/normalizzazione è parametrico su `language` nel config (implementato per `it`, fallback no-stem per altre lingue).

### Decisioni prese su punti aperti (reversibili, ma valgono salvo contrordine)

- **Niente modalità headless/API nel core.** `llm.py` e i tre client vengono eliminati. Se in futuro servirà batch non presidiato, si reintroduce come extra `[headless]` — fuori da questo progetto.
- **Document twin (interviste, saggi brevi) fuori scope.** Citati in §9 come estensione futura; nessuna predisposizione nel codice ora.
- **Entities/timeline/relations/book_graph: eliminati dal percorso obbligatorio.** Erano derivati di derivati, senza evidenza. Restano `concepts`, `claims`, `questions`, `objections`, `applications` — tutti con ancoraggio.

---

## 2. Cosa si elimina da v0.4.0

| Elemento | Motivo |
|---|---|
| `src/book_twin/llm.py` + provider in `cli.py` | L'LLM esecutore è in chat; muoiono API key, retry, 429, max_tokens |
| `src/book_twin/qa.py` (comando `ask`) | Sostituito da `booktwin context` (stampa contesto; la risposta la dà l'LLM in chat) |
| `docs/` (PWA) e `drive_tools/` (Apps Script) | Distribuzione, non engine. Lo ZIP si carica su Drive come si preferisce |
| `ai_protocol/` | Sostituita da `RUNBOOK.md` (engine) + `START_DIALOGUE.md` (output) |
| `exports/` stub (study_guide, anki) | Dead feature; eventuale estensione futura |
| 5 personas + 8 prompt template nell'output | Consolidati in `START_DIALOGUE.md` |
| `verify` a keyword + stemmer artigianale | Sostituito da verifica deterministica delle citazioni + spot-check da runbook (STEP 5) |
| `citations.jsonl`, `figures/`, `tables/` vuoti | Mai popolati in v0.4; tabelle ora finiscono nel markdown (STEP 4), figure fuori scope |

**Cosa si porta (riuso):** `converters.py` (base, da rinforzare), `structure.py` (da correggere), `indexer.py` (da sanitizzare + stemming), `mcp_server.py` (logica pura, da adattare al layout), `utils.py`, `models.py`, test esistenti come base.

---

## 3. Struttura output Book Twin v2

```text
nome_libro/
  START_DIALOGUE.md          # unico entrypoint per l'LLM dialogante
  book.config.yaml           # title, author, year?, language, engine_version, generated_at, status
  STATUS.json                # macchina a stati (vedi §5)
  MANIFEST.json              # generato da pack: hash, conteggi, complete|partial

  canonical/
    book.md                  # testo ricostruito, senza marker pagina
    chapters/                # NNN_slug.md
    notes/                   # note a piè di pagina/finali estratte (STEP 4)
    pages_map.json           # solo PDF: offset → pagina

  analysis/
    chapters/                # chNNN.json (fonte di verità)
    synthesis.json
    rendered/                # .md derivati da `booktwin render` (per lettura umana)

  knowledge/
    chunks.jsonl             # id, chapter_id, chapter_title, order, text, page_start?, page_end?, summary, keywords
    claims.jsonl             # aggregato dai capitoli, con chunk_ids + anchors
    concepts.jsonl           # con chunk_ids
    questions.jsonl  objections.jsonl  applications.jsonl
    index.md                 # mappa concetti→capitoli leggibile SENZA esecuzione codice
    retrieval.sqlite         # FTS5 (+ colonne stemmate)
    embeddings.npz           # opzionale

  author_model.md            # generato e validato (STEP 5), marcato [testo]/[inferenza]
  verify_report.md           # esito verifica deterministica + spot-check
  sessions/                  # dialoghi salvati dall'utente
  logs/processing_log.md     # include fusioni/drop di capitoli, decisioni di estrazione
```

---

## 4. CLI `booktwin` — comandi

| Comando | Funzione |
|---|---|
| `ingest <src> --out <dir> [--force] [--override chapters.override.yaml]` | Estrazione + segmentazione + chunks + indice + skeleton. Logga fusioni/drop |
| `status <dir>` | Stato leggibile: fase, capitoli fatti/mancanti, prossima azione (è ciò che il runbook fa leggere all'LLM) |
| `chapter <dir> NNN [--part i/k]` | Stampa il testo canonico del capitolo; `--parts NNN` dice quante parti servono per stare in ~N char (default 20000, configurabile) |
| `commit-chapter <dir> NNN --file card.json` | Valida (schema + chunk_ids + anchors + coverage) e registra. Aggiorna summary/keywords nei chunk del capitolo e l'indice |
| `commit-synthesis <dir> --file synthesis.json` | Valida e scrive synthesis + aggrega i JSONL knowledge |
| `commit-author-model <dir> --file author_model.json` | Valida contenuto (sezioni non vuote, riferimenti minimi) e renderizza `author_model.md` |
| `index <dir> [--no-embeddings]` | (Ri)costruisce FTS + embedding opzionali |
| `search <dir> "query" [-k 8] [--no-hybrid]` | Ricerca sanitizzata, stemmata, ibrida |
| `context <dir> "domanda" [-k 8]` | Contesto assemblato con header `[chunk_id | capitolo | pp.]` |
| `verify <dir>` | Verifica deterministica citazioni/anchors; exit ≠0 se fallisce; scrive `verify_report.md` |
| `render <dir>` | Genera i .md derivati da JSON |
| `pack <dir>` | Valida → MANIFEST.json → ZIP in `<dir>.zip` (status complete|partial dichiarato) |
| `validate <dir>` | Schema strutturale completo (sostituisce il validate v0.4, adattato al layout v2) |
| `author ...` | Vedi §7 (STEP 7–9) |

---

## 5. Schemi dati (campi obbligatori; JSON Schema completi in `src/book_twin/schemas/`)

### 5.1 `STATUS.json`

```json
{
  "engine_version": "0.5.0",
  "book_hash": "sha256:…",
  "phase": "ingested|analyzing|synthesized|author_modeled|verified|packed",
  "chapters": {
    "ch001": {"status": "pending|committed", "hash": "…", "committed_at": "…", "parts_total": 3}
  },
  "synthesis": "pending|committed",
  "author_model": "pending|committed",
  "log": ["…eventi: merge proposti, drop frontmatter, override applicati…"]
}
```

### 5.2 Scheda capitolo `analysis/chapters/chNNN.json`

```json
{
  "chapter_id": "ch004",
  "title": "…",
  "coverage": {"parts_read": 3, "parts_total": 3},
  "funzione": "ruolo del capitolo nel libro",
  "riassunto": "fedele, ≥300 caratteri",
  "tesi": "distinta dal riassunto (il commit rifiuta se uguale)",
  "concetti": [{"name": "…", "definition": "…", "chunk_ids": ["chunk_ch004_0002"]}],
  "claims": [{
    "claim": "…",
    "tipo": "testo|inferenza",
    "chunk_ids": ["chunk_ch004_0012"],
    "anchors": ["frase di 3–8 parole presente nel chunk citato"]
  }],
  "passaggi": [{"testo": "…", "chunk_id": "…"}],
  "domande": ["…"], "obiezioni": ["…"], "applicazioni": ["…"],
  "cosa_memorizzare": "…"
}
```

**Regole di validazione del commit (deterministiche):**
- `coverage.parts_read == parts_total` registrato in STATUS per quel capitolo;
- ogni `chunk_id` citato esiste e appartiene al capitolo giusto;
- ogni `anchor` è presente nel testo di almeno uno dei chunk citati (confronto normalizzato: lowercase, deaccentato, whitespace compresso);
- `tesi != riassunto`; ≥1 claim, ≥1 concetto;
- claims con `tipo: "testo"` richiedono anchors; `tipo: "inferenza"` richiede comunque chunk_ids (la base dell'inferenza).

### 5.3 `analysis/synthesis.json`

`tesi_centrale`, `formula`, `mappa[]`, `argomentazione`, `concetti_globali[{name, definition, chapter_ids}]`, `domande_profonde[]`, `limiti[]`, `collegamenti_esterni[]` (questi ultimi marcati implicitamente speculativi nel render). Validazione: chapter_ids esistenti, campi non vuoti.

### 5.4 `author_model.json` (singolo libro)

Sezioni obbligatorie: `profilo_intellettuale`, `concetti_centrali[{name, chunk_ids}]`, `stile_argomentativo{descrizione, esempi[{chunk_id, nota}]}`, `valori_impliciti[]` (renderizzati come [inferenza]), `forza[]`, `confini[]` (cosa il libro non copre). Validazione: nessuna sezione vuota; ≥5 riferimenti chunk totali.

---

## 6. STEP di implementazione — fase 1 (Book Twin)

> Ogni step: scope chiuso, test, accettazione verificabile, commit atomico. Vedi §8 per la Definition of Done.

### STEP 0 — Bootstrap v0.5
**Scope:** potatura + skeleton.
- Elimina: `llm.py`, `qa.py`, `docs/`, `drive_tools/`, `ai_protocol/`, comandi CLI `ask`/`analyze`/`init-drive-layout`; riferimenti relativi nei test.
- `pyproject.toml` → 0.5.0; dipendenze: `typer, rich, PyYAML, pypdf, python-docx, beautifulsoup4, ebooklib, jsonschema, snowballstemmer`; extra `[mcp]`, `[embeddings]`, `[dev]`.
- Crea `src/book_twin/schemas/` (vuoto con `__init__`), `RUNBOOK.md` placeholder.
**Accettazione:** `booktwin --version` → 0.5.0; pytest verde sui test residui adattati; nessun import morto.

### STEP 1 — Indexer sicuro (fix crash)
**Scope:** `indexer.py`.
- `sanitize_query(q)`: rimuove `"():^*` e backslash, neutralizza operatori FTS5 (`AND OR NOT NEAR`) trattandoli come parole; output = `"tok1" OR "tok2" …`. Applicata SEMPRE prima del MATCH (non solo in fallback). Nessuna eccezione non gestita su input arbitrario.
**Accettazione (test):** `tesi" injected`, `NEAR AND tesi`, `cita la "rivoluzione cognitiva"`, `perché?` → nessun crash; tutte trovano i chunk contenenti i token significativi presenti nel testo.

### STEP 2 — Core LLM-native (il cuore del progetto)
**Scope:** `schemas/`, `status.py` (nuovo), `commit.py` (nuovo), `cli.py`, `repository.py`, `RUNBOOK.md`.
- Chunk ID v2 (`chunk_chNNN_MMMM`), `chapter_id` = `chNNN`; hash capitolo nei chunk e in STATUS.
- `ingest` v2: layout §3 (niente placeholder md di analisi; STATUS inizializzato; `parts_total` calcolato per capitolo).
- `chapter`, `status`, `commit-chapter`, `commit-synthesis`, `render`, `pack`, `validate` v2 come da §4–5.
- `RUNBOOK.md` v1, scritto per l'LLM esecutore. Struttura: (0) setup ambiente `pip install -e .`; (1) `ingest`; (2) **checkpoint struttura**: confronta `status`/elenco capitoli con l'indice del libro, correggi con override se serve (rimando a STEP 4 per l'override; in v1 solo verifica e segnalazione); (3) loop capitoli: `status` → `chapter NNN --part i/k` (lettura integrale, rolling summary tra le parti) → scrivi `card.json` → `commit-chapter` → se rifiutato, leggi l'errore e correggi; (4) `commit-synthesis`; (5) `verify` (da STEP 5); (6) `pack`; (7) consegna ZIP. Regola esplicita: *se la sessione sta per esaurirsi, esegui `pack` comunque: lo ZIP parziale riprende da STATUS in una sessione nuova.*
**Accettazione:** end-to-end su `examples/sample_book.md` con card di test: ingest → 3 commit-chapter → commit-synthesis → pack produce ZIP con MANIFEST `complete`; commit con chunk_id inesistente → exit ≠0 con messaggio che indica l'id; anchor assente → idem; coverage 2/3 → rifiutato; re-ingest dello stesso testo → chunk ID identici (test di stabilità).

### STEP 3 — Stemming italiano
**Scope:** `indexer.py`.
- Dipendenza `snowballstemmer` (pure Python). Colonne FTS aggiuntive `text_stem`, `summary_stem` popolate a indicizzazione; query: token sanitizzati → match su colonne originali OR stem dei token su colonne stemmate.
- Parametrico su `language` dal config; lingue non supportate → comportamento attuale (no-stem), senza errori.
**Accettazione:** su sample, `interpretazioni` trova il chunk con "interpretazione"; `perché` e `perche` equivalenti; ranking: il match esatto non peggiora rispetto a STEP 1.

### STEP 4 — Estrazione robusta
**Scope:** `converters.py`, `structure.py`, nuovo `chapters.override.yaml`.
- **PDF:** de-sillabazione (`parola-\n parola` → ricomposta se entrambe minuscole); rimozione testatine/piè di pagina (righe corte ripetute ≥4 volte a inizio/fine pagina) e numeri di pagina isolati; `pages_map.json` (offset carattere → n. pagina) costruita PRIMA di rimuovere i marker; `page_start/page_end` popolati nei chunk dalla mappa (chiude il dead code v0.4).
- **HTML/EPUB:** `<table>` → tabella Markdown (non più scartata); note: `<sup>` contenente `<a>` (o `<a>` con classe nota) → estratto in `canonical/notes/` con marcatore inline `[n.X]`; `<sup>` senza link **conservato** come `^contenuto` (gli esponenti `10²` sopravvivono — test dedicato).
- **`split_chapters` v2:** la fusione automatica si applica SOLO ai divisori (segmento <200 char e senza paragrafo di corpo); ogni fusione e ogni drop da `FRONTBACK_RE` vengono loggati in STATUS.log e processing_log. `chapters.override.yaml` (azioni: `merge`, `split_at`, `rename`, `drop`, `undrop`) applicabile con `ingest --override` o `booktwin restructure <dir> --override file`. Il RUNBOOK aggiorna il checkpoint struttura (STEP 2 punto 2): l'LLM confronta con l'indice del libro e scrive l'override se serve.
**Accettazione:** sample_book → **3 capitoli** (il cap. 3 non viene più inghiottito); fixture HTML con tabella → tabella nel md; fixture `10<sup>2</sup>` → `10^2` conservato; fixture nota `<sup><a>12</a></sup>` → testo pulito + nota in notes/; fixture PDF sintetica (reportlab nei test) con sillabazione e testatina → ricomposta e rimossa; drop di un capitolo "Indice" → presente nel log.

### STEP 5 — Author model + verify v2
**Scope:** `commit.py`, `verify.py` (nuovo), `RUNBOOK.md`.
- `commit-author-model` come da §5.4; render in `author_model.md` con sezioni [testo]/[inferenza].
- `verify`: (a) deterministico — tutti i chunk_ids citati in capitoli/synthesis/author_model esistono; tutte le anchors trovate (normalizzate); exit ≠0 altrimenti; (b) genera `verify_report.md` con esito + la sezione "spot-check" che il RUNBOOK fa eseguire all'LLM: campiona 2 claim per capitolo, rileggi i chunk citati, conferma o segnala — l'esito si appende al report.
- Il `pack` rifiuta status `complete` se author_model o verify mancano (può comunque produrre `partial`).
**Accettazione:** twin senza author model → `pack` lo dichiara partial; anchor corrotta a mano → `verify` FAIL con indicazione di claim e chunk; report generato.

### STEP 6 — Consumo (dialogo)
**Scope:** `repository.py` (render START_DIALOGUE), `knowledge/index.md`, `mcp_server.py`.
- `START_DIALOGUE.md` generato a pack/render: identità (simulazione testualmente vincolata, formula con nome autore), gerarchia fonti (`knowledge/` > `canonical/` > `analysis/` > `author_model.md`), disciplina [testo]/[inferenza]/[speculazione] con obbligo di chunk_id, regola "posizioni del libro, non opinioni attuali della persona", istruzioni duali: *con* esecuzione codice (`booktwin search/context`) e *senza* (usa `knowledge/index.md` + chunks.jsonl + capitoli). Persona alternative (esegeta, critico, socratico) in appendice dello stesso file.
- `knowledge/index.md`: generato da synthesis+schede — concetti→capitoli→chunk di riferimento; è la mappa per LLM senza sandbox.
- MCP adattato al layout v2 (tool invariati nello spirito; `prompt` = START_DIALOGUE). Test MCP adattati.
**Accettazione:** `validate` passa su twin completo v2; MCP tools rispondono sul nuovo layout; START_DIALOGUE contiene formula, gerarchia, tre livelli, istruzioni duali (test su stringhe chiave).

**GATE fase 1 (manuale, fuori da CC):** rigenerare end-to-end il Book Twin di *Irriducibile* in una sessione Claude reale seguendo il RUNBOOK. Atteso: ~17 capitoli, zero stub, verify OK. Solo dopo questo gate si parte con la fase 2.

---

## 7. STEP di implementazione — fase 2 (Author Twin)

**Principio: composizione, non fusione.** I Book Twin restano immutabili in `books/`; il layer autore aggiunge solo conoscenza cross-libro, con provenienza sempre esplicita. ID namespaced: `slug_libro:chunk_chNNN_MMMM`.

```text
author_twin_<slug>/
  AUTHOR_START_DIALOGUE.md
  author.config.yaml         # nome, libri: [{slug, title, year, manifest_hash}], ordine cronologico
  STATUS.json
  books/<anno>_<slug>/       # Book Twin completi, intoccati
  author_knowledge/
    concept_map.jsonl  trajectories.jsonl  tensions.jsonl
    invariants.md
  author_model.md            # v2 diacronico
```

### STEP 7 — Struttura e ingest autore
**Scope:** `author.py` (nuovo), CLI `author init`, `author add-book`.
- `author init <dir> --name "Federico Faggin"`; `author add-book <zip|dir>`: verifica MANIFEST (status complete, engine compatibile), copia in `books/`, registra in config con anno (da config del libro o `--year`), rifiuta duplicati per hash.
**Accettazione:** due twin di test → config corretto e ordinato per anno; stesso libro due volte → rifiutato; twin partial → rifiutato con messaggio.

### STEP 8 — Cross-analysis (AUTHOR_RUNBOOK + commit)
**Scope:** `schemas/` autore, `author.py`, `AUTHOR_RUNBOOK.md`.
- Schemi:
  - `concept_map` row: `{concept_canonical, per_book: [{book, term, definition, chunk_ids}] (≥2 libri), nota_evoluzione?}` — la nota è [inferenza];
  - `trajectories` row: `{topic, stages: [{book, year, position, chunk_ids}] ordinati per anno, direzione}`;
  - `tensions` row: `{topic, grade: "esplicita"|"implicita", a: {book, position, chunk_ids}, b: {book, position, chunk_ids}, nota}` — **doppia evidenza obbligatoria; lista vuota legale** (meglio vuoto che fabbricato; il runbook lo dice esplicitamente all'LLM);
  - `author_model` v2: invarianti / variabili per opera / traiettoria, ogni voce con riferimenti namespaced.
- `author commit-cross --kind concept_map|trajectories|tensions|model --file …`: valida che ogni chunk_id namespaced esista nel twin corrispondente. Cache per coppia di libri (hash dei due manifest): `add-book` di un libro N+1 invalida solo le coppie che lo coinvolgono.
- `AUTHOR_RUNBOOK.md`: lavora su schede e claims dei twin (non sui testi integrali), in ordine: concept map → traiettorie → tensioni → model; per le tensioni: prima cercare ritrattazioni/riprese esplicite (grade esplicita), poi confronti inferiti, sempre marcati.
**Accettazione:** commit con chunk_id inesistente nel libro B → rifiutato col riferimento esatto; tension con evidenza da un solo libro → rifiutata; tensions vuoto → accettato; cache: ricommit senza modifiche ai libri → no-op dichiarato.

### STEP 9 — Dialogo autore (retrieval federato + pack)
**Scope:** `author.py`, `indexer.py` (federazione), `AUTHOR_START_DIALOGUE.md`, `author pack`, MCP.
- `author search "query" [-k 8]`: esegue la ricerca per libro, **quota minima per libro** (round-robin: almeno ⌈k/N⌉ risultati ciascuno se disponibili) prima della fusione RRF globale — evita che il libro più lungo domini.
- `author context "domanda"`: come sopra, con header `[slug:chunk_id | libro (anno) | capitolo]`.
- `AUTHOR_START_DIALOGUE.md`: due modalità — **"Autore oggi"** (default: posizione più matura con accesso alla propria storia, citazioni datate per opera) e **"Autore di [libro]"** (snapshot esegetico vincolato a un'opera). Regola: ogni posizione espressa è datata (da quale opera proviene). Le domande su evoluzioni/contraddizioni si ancorano a `trajectories`/`tensions`, mai improvvisate.
- `author pack` → ZIP con manifest multi-libro. MCP: `booktwin-mcp --author <dir>` espone search/context federati + resources per libro (estensione minima del server esistente).
**Accettazione:** con 2 libri di lunghezza molto sbilanciata e k=8, entrambi rappresentati nei risultati (test con fixture); context riporta libro+anno; pack valido; modalità e regola di datazione presenti in AUTHOR_START_DIALOGUE (test su stringhe chiave).

---

## 8. Metodo di lavoro e Definition of Done

**Per ogni STEP:**
1. Implementare solo lo scope dello step. Nessuna feature non richiesta, nessun file fuori scope.
2. Test: nuovi per i requisiti dello step + suite esistente. `pytest` verde.
3. Aggiornare `PROGRESS.md`: step, file toccati, **Decisioni** (ogni ambiguità risolta va scritta qui), risultati test.
4. Aggiornare `CHANGELOG.md`.
5. Commit atomico: `STEP N: <titolo breve>`.
6. Fermarsi e riassumere in ≤10 righe.

**Ambiguità:** scegliere la soluzione più semplice coerente con §1, documentarla in PROGRESS sotto "Decisioni", procedere. Non chiedere conferma per dettagli implementativi; chiedere solo se una scelta contraddice una decisione vincolante di §1.

**Rischi noti (non bloccanti):**
- Limiti di sessione dell'LLM esecutore su libri lunghi → mitigato da STATUS + zip partial ripristinabile (è un requisito, non una speranza: testato in STEP 2).
- Variabilità dei layout note negli EPUB → euristiche documentate + override; l'estrazione note è best-effort dichiarato nel log.

---

## 9. Estensioni future (fuori scope, nessuna predisposizione ora)

- **Document twin leggeri** (interviste, saggi, lectiones) con peso ridotto nel corpus autore.
- Extra `[headless]` per batch via API.
- Export study guide / flashcard generati dal runbook.
- OCR per PDF scansionati.

---

## Appendice A — Prompt kickoff per Claude Code

```text
Leggi PROGETTO.md per intero: è la fonte di verità. Se esiste PROGRESS.md, leggi anche quello per capire lo stato.

Contesto: questo repo è book-twin-engine v0.4.0. Lo trasformiamo in v0.5.0 secondo PROGETTO.md (architettura LLM-native: l'engine diventa toolkit deterministico + RUNBOOK; l'analisi la fa l'LLM esecutore in sandbox).

Metodo vincolante:
- Un solo STEP per volta, nell'ordine di PROGETTO.md §6–7.
- Per ogni step: implementa lo scope, scrivi/aggiorna i test, esegui pytest, aggiorna PROGRESS.md (file toccati + sezione "Decisioni" per ogni ambiguità risolta) e CHANGELOG.md, poi commit atomico "STEP N: <titolo>".
- Non toccare file fuori dallo scope dello step. Nessuna feature non richiesta.
- Ambiguità: scegli la soluzione più semplice coerente con PROGETTO.md §1, documentala in PROGRESS.md, procedi. Fermati a chiedere solo se la scelta contraddirebbe una decisione vincolante di §1.
- A fine step: fermati e riporta in ≤10 righe cosa hai fatto, i risultati dei test e i criteri di accettazione verificati.

Esegui STEP 0.
```

## Appendice B — Template prompt per gli step successivi

```text
Leggi PROGRESS.md. Esegui STEP <N> di PROGETTO.md. Stesse regole del kickoff: scope chiuso, test, PROGRESS aggiornato, commit atomico, report ≤10 righe con i criteri di accettazione verificati.
```

In caso di correzioni a uno step già committato:

```text
Leggi PROGRESS.md. Fix mirato su STEP <N>: <descrizione del problema, 1-3 righe>. Solo i file di quello step. Test di regressione incluso. Commit "STEP N fix: <titolo>".
```
