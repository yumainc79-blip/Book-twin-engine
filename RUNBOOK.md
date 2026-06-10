# RUNBOOK — Generazione di un Book Twin (engine 0.5)

> Tu, LLM esecutore con sandbox (esecuzione codice + filesystem), sei l'analista.
> L'engine è un toolkit deterministico: estrae, segmenta, indicizza, valida, impacchetta.
> L'analisi la fai tu, capitolo per capitolo, e la consegni via `booktwin commit-*`.
> Ogni commit è validato: se viene rifiutato, leggi il messaggio d'errore, correggi e riprova.

**Regola di sopravvivenza (leggila subito):** se la sessione sta per esaurirsi,
esegui `booktwin pack <dir>` comunque. Lo ZIP parziale è legale: ricaricato con
l'engine in una sessione nuova, riprende esattamente da dove era (STATUS.json).

## 0. Setup ambiente

```bash
unzip book-twin-engine.zip -d engine && cd engine   # se ricevuto come ZIP
pip install -e .
booktwin --version   # atteso: 0.5.x
```

## 1. Ingest

```bash
booktwin ingest /percorso/libro.epub --out twin_<slug>
```

Estrazione, segmentazione in capitoli, chunk con ID stabili
(`chunk_chNNN_MMMM`), indice FTS, `STATUS.json` inizializzato.

## 2. Checkpoint struttura

```bash
booktwin status twin_<slug>
```

Confronta l'elenco dei capitoli con l'indice reale del libro (lo trovi nelle
prime pagine di `canonical/book.md`). Se la segmentazione è sbagliata, scrivi
un `chapters.override.yaml` e applicalo **ORA, prima del loop capitoli**
(dopo il primo commit la ristrutturazione è bloccata per non rompere le citazioni):

```yaml
actions:
  - {action: merge, chapters: [3, 4]}        # fonde il 4 nel 3
  - {action: split_at, chapter: 2, at: "## Titolo sezione", title: "Nuovo capitolo"}
  - {action: rename, chapter: 5, title: "Titolo corretto"}
  - {action: drop, chapter: 7}               # scarta un non-capitolo
  - {action: undrop, title: "Prefazione"}    # ripristina un segmento scartato
```

```bash
booktwin restructure twin_<slug> --override chapters.override.yaml
```

**Paratesto residuo:** se tra i capitoli vedi bibliografia, indici, elenchi di
abbreviazioni, ringraziamenti e simili, scartali con `drop` via override ORA:
non vanno analizzati nel loop. Viceversa, controlla in `STATUS.json` → `log` i
drop automatici: se è stato scartato un capitolo vero (es. un capitolo
intitolato "Note sul metodo"), ripristinalo con `undrop`. L'override applicato
viene salvato nel twin: il risultato è riproducibile.

## 3. Loop capitoli

Per ogni capitolo `pending` in `booktwin status`:

1. **Leggi il capitolo INTERO.** Se ha K parti (vedi `status`):
   ```bash
   booktwin chapter twin_<slug> N --part 1/K   # poi 2/K … K/K
   ```
   Tra una parte e l'altra mantieni un rolling summary: l'analisi finale deve
   coprire tutto il capitolo, non solo l'ultima parte letta.
2. **Scrivi la scheda** `card.json` (schema in §5.2 di PROGETTO.md; lo schema
   formale è in `src/book_twin/schemas/`). Punti non negoziabili:
   - `coverage`: `{"parts_read": K, "parts_total": K}` — il commit rifiuta
     coverage incompleto;
   - ogni concetto e ogni claim cita `chunk_ids` reali del capitolo
     (li trovi in `knowledge/chunks.jsonl`);
   - i claims `tipo: "testo"` portano `anchors`: frasi di 3–8 parole copiate
     ESATTAMENTE dal chunk citato;
   - i claims `tipo: "inferenza"` citano comunque i chunk su cui si basa
     l'inferenza;
   - dove pertinente, includi almeno 1 claim `tipo: "inferenza"` per capitolo
     (le inferenze rendono il twin dialogico, non solo riassuntivo);
   - `riassunto` ≥ 300 caratteri, fedele; `tesi` distinta dal riassunto.
3. **Commit:**
   ```bash
   booktwin commit-chapter twin_<slug> N --file card.json
   ```
   Se rifiutato: il messaggio dice esattamente cosa è rotto (chunk_id
   inesistente, anchor non trovata, coverage…). Correggi la scheda e riprova.
   Non aggirare mai il commit scrivendo i file a mano.

## 4. Sintesi

Quando `status` mostra tutti i capitoli committati:

```bash
booktwin commit-synthesis twin_<slug> --file synthesis.json
```

Schema in §5.3 di PROGETTO.md: `tesi_centrale`, `formula`, `mappa`,
`argomentazione`, `concetti_globali` (con `chapter_ids` reali),
`domande_profonde`, `limiti`, `collegamenti_esterni` (speculativi, dichiarati).

## 5. Verifica

(Da STEP 5: `booktwin verify`.) Per ora: `booktwin validate twin_<slug>` deve
passare.

## 6. Render e pack

```bash
booktwin render twin_<slug>
booktwin pack twin_<slug>
```

`pack` produce `twin_<slug>.zip` con `MANIFEST.json` (`complete` o `partial`).

## 7. Consegna

Consegna lo ZIP all'utente e riporta: capitoli analizzati, eventuali
discrepanze del checkpoint struttura, esito della validazione, e se lo ZIP è
completo o parziale (e in tal caso da dove riprenderà).
