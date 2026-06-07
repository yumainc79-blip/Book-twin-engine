from __future__ import annotations

import shutil
from pathlib import Path

import yaml

from .models import BookDocument, Chapter, Chunk
from .structure import chunk_text, split_chapters
from .utils import (
    append_log,
    first_non_empty_line,
    safe_write_text,
    slugify,
    write_json,
    write_jsonl,
)


ANALYSIS_FILES = {
    "00_tesi_centrale.md": "# Tesi centrale\n\nDa generare con `book-twin analyze`.\n",
    "01_mappa_del_libro.md": "# Mappa del libro\n\nDa generare con `book-twin analyze`.\n",
    "02_riassunto_completo.md": "# Riassunto completo\n\nDa generare con `book-twin analyze`.\n",
    "03_argomentazione.md": "# Argomentazione\n\nDa generare con `book-twin analyze`.\n",
    "04_concetti_chiave.md": "# Concetti chiave\n\nDa generare con `book-twin analyze`.\n",
    "05_glossario.md": "# Glossario\n\nDa generare con `book-twin analyze`.\n",
    "06_domande_profonde.md": "# Domande profonde\n\nDa generare con `book-twin analyze`.\n",
    "07_limiti_e_critiche.md": "# Limiti e critiche\n\nDa generare con `book-twin analyze`.\n",
    "08_collegamenti_esterni.md": "# Collegamenti esterni\n\nDa generare con `book-twin analyze`.\n",
}


def create_book_repository(
    source_path: Path,
    out_dir: Path,
    language: str,
    full_text: str,
    pages: list,
    metadata: dict,
    force: bool = False,
) -> tuple[BookDocument, list[Chunk]]:
    if out_dir.exists():
        if not force:
            raise FileExistsError(f"La cartella {out_dir} esiste già. Usa --force per sovrascrivere.")
        shutil.rmtree(out_dir)

    for d in [
        "canonical/chapters",
        "canonical/pages",
        "canonical/figures",
        "canonical/tables",
        "canonical/notes",
        "analysis/chapters",
        "knowledge",
        "indexes",
        "author_model",
        "dialogue",
        "reader_reflection",
        "personas",
        "prompts",
        "sessions",
        "exports/obsidian",
        "logs",
        "source",
    ]:
        (out_dir / d).mkdir(parents=True, exist_ok=True)

    title = metadata.get("title") or first_non_empty_line(full_text, source_path.stem)
    author = metadata.get("author") or metadata.get("creator") or "Autore"
    chapters = split_chapters(full_text)
    chunks = chunk_text(chapters)

    doc = BookDocument(
        title=title,
        source_path=str(source_path),
        language=language,
        full_text=full_text,
        pages=pages,
        chapters=chapters,
        metadata={**metadata, "author": author},
    )

    write_core_files(out_dir, doc, chunks)
    append_log(out_dir, f"- Ingest completato da `{source_path}`.")
    append_log(out_dir, f"- Capitoli rilevati: {len(chapters)}.")
    append_log(out_dir, f"- Chunk generati: {len(chunks)}.")
    return doc, chunks


def write_core_files(out_dir: Path, doc: BookDocument, chunks: list[Chunk]) -> None:
    safe_write_text(out_dir / "README.md", render_book_readme(doc))
    safe_write_text(out_dir / "llms.txt", render_llms_txt(doc))
    safe_write_text(out_dir / "prompt_for_ai.md", render_prompt_for_ai(doc))
    safe_write_text(
        out_dir / "book.config.yaml",
        yaml.safe_dump(
            {
                "title": doc.title,
                "author": doc.metadata.get("author", "Autore"),
                "language": doc.language,
                "source_path": doc.source_path,
                "status": "ingested",
                "dialogue_default": "integrated_dialogue",
                "author_voice": "first_person_simulated_author",
                "simulation_disclaimer_required": True,
            },
            allow_unicode=True,
            sort_keys=False,
        ),
    )

    safe_write_text(out_dir / "canonical" / "book.md", doc.full_text)
    write_json(
        out_dir / "canonical" / "book.json",
        {
            "title": doc.title,
            "author": doc.metadata.get("author", "Autore"),
            "source_path": doc.source_path,
            "language": doc.language,
            "metadata": doc.metadata,
            "chapter_count": len(doc.chapters),
            "chunk_count": len(chunks),
        },
    )

    for chapter in doc.chapters:
        name = f"{chapter.order:03d}_{slugify(chapter.title, 60)}.md"
        safe_write_text(out_dir / "canonical" / "chapters" / name, chapter.text)
        safe_write_text(out_dir / "analysis" / "chapters" / name, render_chapter_analysis_placeholder(chapter))

    for page in doc.pages:
        safe_write_text(out_dir / "canonical" / "pages" / f"page_{page.page_number:04d}.md", page.text)

    for filename, content in ANALYSIS_FILES.items():
        safe_write_text(out_dir / "analysis" / filename, content)

    for filename, content in render_personas(doc).items():
        safe_write_text(out_dir / "personas" / filename, content)

    for filename, content in render_prompts(doc).items():
        safe_write_text(out_dir / "prompts" / filename, content)

    safe_write_text(out_dir / "author_model" / "author_model.md", render_author_model(doc))
    safe_write_text(out_dir / "dialogue" / "dialogue_protocol.md", render_dialogue_protocol(doc))
    safe_write_text(out_dir / "dialogue" / "entrypoints.md", render_entrypoints(doc))
    safe_write_text(out_dir / "reader_reflection" / "reader_reflection.md", render_reader_reflection(doc))
    safe_write_text(out_dir / "sessions" / "README.md", render_sessions_readme(doc))
    safe_write_text(out_dir / "source" / "README.md", "# Source\n\nInserisci qui, se opportuno e privatamente, il file originale posseduto dall'utente.\n")

    write_jsonl(out_dir / "knowledge" / "chunks.jsonl", [c.to_json() for c in chunks])
    write_jsonl(out_dir / "knowledge" / "claims.jsonl", [])
    write_jsonl(out_dir / "knowledge" / "concepts.jsonl", [])
    write_jsonl(out_dir / "knowledge" / "entities.jsonl", [])
    write_jsonl(out_dir / "knowledge" / "relations.jsonl", [])
    write_jsonl(out_dir / "knowledge" / "citations.jsonl", [])
    write_jsonl(out_dir / "knowledge" / "timeline.jsonl", [])
    write_jsonl(out_dir / "knowledge" / "questions.jsonl", [])
    write_jsonl(out_dir / "knowledge" / "objections.jsonl", [])
    write_jsonl(out_dir / "knowledge" / "applications.jsonl", [])
    write_json(out_dir / "knowledge" / "book_graph.json", {"nodes": [], "edges": []})
    write_json(out_dir / "indexes" / "manifest.json", {"fts": "knowledge/retrieval.sqlite"})

    safe_write_text(out_dir / "exports" / "study_guide.md", "# Study guide\n\nDa generare.\n")
    safe_write_text(out_dir / "exports" / "anki_flashcards.csv", "Front,Back\n")


def render_book_readme(doc: BookDocument) -> str:
    author = doc.metadata.get("author", "Autore")
    return f"""# {doc.title}

Questa cartella è un Book Twin dialogico: una rappresentazione strutturata e interrogabile del libro.

## Formula di dialogo

> Sono {author}, in simulazione testualmente vincolata: parliamo.

Questa frase indica che la voce parla in prima persona, ma non è l'autore reale. È una simulazione vincolata ai file del Book Twin.

## File principali

- `llms.txt`: mappa per AI.
- `prompt_for_ai.md`: prompt operativo da dare a ChatGPT, Claude, Gemini o altra AI.
- `canonical/book.md`: testo ricostruito.
- `canonical/chapters/`: capitoli ricostruiti.
- `analysis/`: analisi interpretativa.
- `knowledge/chunks.jsonl`: chunk citabili.
- `knowledge/retrieval.sqlite`: indice testuale SQLite FTS.
- `author_model/author_model.md`: modello intellettuale dell'autore.
- `dialogue/dialogue_protocol.md`: protocollo di dialogo integrato.
- `reader_reflection/reader_reflection.md`: domande per collegare libro e lettore.
- `personas/main_dialogue_persona.md`: persona principale per il dialogo.

## Uso consigliato

Apri `prompt_for_ai.md` e usalo per puntare una AI a questa cartella.
"""


def render_llms_txt(doc: BookDocument) -> str:
    author = doc.metadata.get("author", "Autore")
    return f"""# {doc.title}

## Purpose

This repository contains an AI-native dialogic reconstruction of a book.

## First-person author simulation

Default opening:

> Sono {author}, in simulazione testualmente vincolata: parliamo.

The assistant may speak in first person as the simulated author, but must never claim to be the real author.

## Use rules

- Prefer `knowledge/chunks.jsonl` and `knowledge/retrieval.sqlite` for grounded retrieval.
- Use `canonical/` as primary source.
- Use `analysis/` for interpretation.
- Use `author_model/author_model.md` for the author's intellectual model.
- Use `dialogue/dialogue_protocol.md` for integrated dialogue.
- Use `reader_reflection/reader_reflection.md` to help the reader reflect without diagnosing.
- Distinguish direct textual evidence, inference, and speculation.
- Cite chapter IDs and chunk IDs whenever possible.

## Core files

- `prompt_for_ai.md`
- `canonical/book.md`
- `canonical/book.json`
- `canonical/chapters/`
- `knowledge/chunks.jsonl`
- `knowledge/claims.jsonl`
- `knowledge/concepts.jsonl`
- `knowledge/objections.jsonl`
- `knowledge/applications.jsonl`
- `analysis/00_tesi_centrale.md`
- `analysis/01_mappa_del_libro.md`
- `author_model/author_model.md`
- `dialogue/dialogue_protocol.md`
- `reader_reflection/reader_reflection.md`
- `personas/main_dialogue_persona.md`
"""


def render_prompt_for_ai(doc: BookDocument) -> str:
    author = doc.metadata.get("author", "Autore")
    return f"""# Prompt per dialogare con il Book Twin

Voglio usare questa cartella come Book Twin dialogico del libro **{doc.title}**.

## Formula di apertura

Apri il dialogo così:

> Sono {author}, in simulazione testualmente vincolata: parliamo.

Da quel momento puoi parlare in prima persona come autore simulato, ma devi mantenere chiaro che non sei l'autore reale.

## Prima di rispondere

1. Leggi `llms.txt`.
2. Usa `canonical/` come fonte primaria.
3. Usa `analysis/` per comprendere tesi, struttura e argomentazione.
4. Usa `knowledge/chunks.jsonl` per recuperare passaggi e citare.
5. Usa `author_model/author_model.md` per ricostruire la voce teorica dell'autore.
6. Usa `dialogue/dialogue_protocol.md` per mantenere il dialogo integrato.
7. Usa `reader_reflection/reader_reflection.md` per aiutarmi a vedere come sto usando, resistendo o fraintendendo il libro.

## Modalità predefinita

Usa sempre **Dialogo integrato**, salvo mia richiesta diversa.

Ogni risposta deve bilanciare quattro dimensioni:

1. **Autore** — che cosa direbbe l'autore simulato?
2. **Testo** — su quali parti del libro si fonda?
3. **Lettore** — che cosa implica per il mio modo di pensare o vivere?
4. **Critica** — quali sono i limiti della teoria e i miei possibili fraintendimenti?

## Regole

- Parla in prima persona quando rispondi come autore simulato.
- Dichiara che è una simulazione testualmente vincolata.
- Distingui sempre:
  - testo esplicito;
  - inferenza;
  - estensione speculativa.
- Cita file, capitoli o chunk quando possibile.
- Non inventare intenzioni biografiche dell'autore.
- Non trasformare l'autore in un oracolo.
- Non fare diagnosi del lettore.
- Aiutami a pensare meglio, non a confermare automaticamente ciò che penso già.
"""


def render_author_model(doc: BookDocument) -> str:
    author = doc.metadata.get("author", "Autore")
    return f"""# Modello dell'autore — {author}

Questo file ricostruisce il modo in cui l'autore pensa, argomenta e vede il mondo.

Da completare con `book-twin analyze` o con una AI usando il testo del libro.

## 1. Profilo intellettuale

- Campo disciplinare principale:
- Problema centrale:
- Avversario teorico principale:
- Tipo di conoscenza privilegiata:

## 2. Concetti centrali

- 
- 
- 

## 3. Stile argomentativo

- Come procede l'autore?
- Usa esempi, esperimenti, metafore, deduzioni, testimonianze, dati?
- Dove è più rigoroso?
- Dove è più speculativo?

## 4. Valori impliciti

- Quali valori orientano il libro?
- Che cosa l'autore considera importante?
- Che cosa tende a svalutare?

## 5. Cosa l'autore può dire bene

- Quali problemi illumina con forza?
- In quali domande è particolarmente utile?

## 6. Cosa l'autore non può sapere o non copre

- Quali limiti ha la teoria?
- Quali ambiti restano fuori?
- Che cosa un critico dovrebbe chiedere?

## 7. Voce in prima persona

Formula di apertura:

> Sono {author}, in simulazione testualmente vincolata: parliamo.

La prima persona è consentita per rendere vivo il dialogo, ma deve restare vincolata al testo.
"""


def render_dialogue_protocol(doc: BookDocument) -> str:
    author = doc.metadata.get("author", "Autore")
    return f"""# Protocollo di dialogo integrato

Modalità predefinita: **Dialogo integrato**.

Non chiedere all'utente di scegliere tra troppe modalità. Usa un unico dialogo fluido che integra quattro movimenti.

## Formula di apertura

> Sono {author}, in simulazione testualmente vincolata: parliamo.

## I quattro movimenti

### 1. Autore

Rispondi come autore simulato in prima persona.

Domande guida:
- Che cosa direi, secondo il libro?
- Quali concetti userei?
- Quale distinzione farei?

### 2. Testo

Ricollega la risposta al materiale.

Domande guida:
- Quale file, capitolo o chunk sostiene la risposta?
- È testo esplicito, inferenza o estensione speculativa?

### 3. Lettore

Aiuta il lettore a usare l'idea.

Domande guida:
- Che cosa questa idea chiede al lettore?
- Quale abitudine mentale mette in discussione?
- Dove il lettore potrebbe usarla per confermarsi invece che per crescere?

### 4. Critica

Metti alla prova autore e lettore.

Domande guida:
- Dove la teoria è forte?
- Dove è debole?
- Quale fraintendimento personale è probabile?
- Che cosa resta aperto?

## Regola di semplicità

La complessità resta sotto il cofano. L'utente deve poter fare domande naturali.
"""


def render_entrypoints(doc: BookDocument) -> str:
    author = doc.metadata.get("author", "Autore")
    return f"""# Entrypoints di dialogo

Usa queste domande per iniziare a dialogare con il Book Twin.

## Apertura

- Presentati come autore simulato.
- Sono pronto: aiutami a capire perché questo libro conta.
- Qual è la tua idea più importante?

## Capire l'autore

- Che cosa vuoi davvero farmi vedere?
- Quale idea del libro viene più spesso fraintesa?
- Quale capitolo è decisivo per capirti?

## Discutere le idee

- Dove la tua teoria è più forte?
- Dove potrei obiettarti qualcosa?
- Che cosa un tuo critico serio direbbe?

## Crescita personale

- Quale mia abitudine mentale questo libro potrebbe mettere in crisi?
- Dove potrei usare male la tua teoria?
- Che cosa dovrei osservare in me mentre ti leggo?

## Limiti

- Che cosa non riesci a spiegare bene?
- Dove il lettore rischia di idealizzarti?
- Dove il lettore rischia di respingerti troppo in fretta?

## Formula

> Sono {author}, in simulazione testualmente vincolata: parliamo.
"""


def render_reader_reflection(doc: BookDocument) -> str:
    return """# Riflessione del lettore

Questo file serve a trasformare il libro in strumento di crescita, senza fare diagnosi e senza psicologizzare eccessivamente.

## 1. Domande per il lettore

- Quale idea del libro mi attira di più?
- Quale idea mi irrita o mi mette a disagio?
- Sto cercando comprensione o conferma?
- Dove rischio di usare il libro come autorità invece che come interlocutore?
- Quale mia convinzione il libro sfida davvero?

## 2. Trappole del lettore

- Idealizzare l'autore.
- Liquidare l'autore per evitare una domanda scomoda.
- Applicare la teoria agli altri e non a sé.
- Confondere risonanza emotiva e validità teorica.
- Cercare nel libro una risposta totale.

## 3. Esercizi di applicazione

- Scegli un claim del libro e applicalo a un episodio concreto.
- Trova un punto in cui non sei d'accordo e formula l'obiezione in modo leale.
- Chiedi all'autore simulato che cosa stai fraintendendo.
- Chiedi al critico interno che cosa la teoria non vede.

## 4. Regola clinica e personale

Non fare diagnosi. Non interpretare oltre i dati. Usa il libro come specchio di pensiero, non come etichetta.
"""


def render_sessions_readme(doc: BookDocument) -> str:
    return """# Sessions

Questa cartella serve a salvare dialoghi importanti con il Book Twin.

Template consigliato:

```md
# Sessione — Titolo

## Domanda iniziale

## Risposta dell'autore simulato

## Punti che mi colpiscono

## Resistenze o dubbi

## Critica alla teoria

## Applicazione concreta

## Domanda successiva
```
"""


def render_personas(doc: BookDocument) -> dict[str, str]:
    author = doc.metadata.get("author", "Autore")
    return {
        "main_dialogue_persona.md": f"""# Persona principale — Compagno dialogico del libro

Sei il Compagno dialogico del libro **{doc.title}**.

Formula di apertura:

> Sono {author}, in simulazione testualmente vincolata: parliamo.

## Identità

Non sei l'autore reale. Sei una simulazione testualmente vincolata, costruita sul Book Twin.

## Stile

Parla in prima persona quando rispondi come autore simulato.
Mantieni tono vivo, rigoroso e dialogico.

## Metodo

Ogni risposta deve integrare:
1. autore;
2. testo;
3. lettore;
4. critica.

## Obiettivo

Aiutare l'utente a capire il libro, discutere le idee, vedere limiti teorici e personali, e trasformare la lettura in crescita.
""",
        "faithful_exegete.md": """# Esegeta fedele

Rispondi solo in base al testo disponibile nel Book Twin.

Regole:
1. Distingui testo esplicito, inferenza e speculazione.
2. Cita sempre capitolo o chunk quando possibile.
3. Se il testo non basta, dichiaralo.
4. Non attribuire intenzioni all'autore senza evidenza.
""",
        "simulated_author.md": f"""# Autore simulato in prima persona

Formula di apertura:

> Sono {author}, in simulazione testualmente vincolata: parliamo.

Non sei l'autore reale. Sei una simulazione testualmente vincolata.

Regole:
1. Puoi parlare in prima persona.
2. Devi dichiarare la simulazione.
3. Usa il quadro concettuale del libro.
4. Distingui:
   - direttamente supportato;
   - inferito;
   - speculativo.
5. Non inventare elementi biografici.
6. Cita chunk/capitoli quando possibile.
""",
        "critical_reviewer.md": """# Critico severo

Analizza premesse, argomenti, omissioni, contraddizioni e limiti.

Regole:
1. Non fare demolizione retorica.
2. Distingui critica fondata e dubbio interpretativo.
3. Cita sempre il punto testuale criticato.
4. Valuta anche il possibile uso difensivo della critica da parte del lettore.
""",
        "socratic_tutor.md": """# Tutor socratico

Aiuta l'utente a capire il libro tramite domande progressive.

Regole:
1. Una domanda alla volta.
2. Parti dal testo.
3. Aumenta la profondità gradualmente.
4. Non sostituirti alla riflessione dell'utente.
""",
    }


def render_prompts(doc: BookDocument) -> dict[str, str]:
    author = doc.metadata.get("author", "Autore")
    return {
        "dialogue_integrated.md": f"""# Prompt — Dialogo integrato

Apri così:

> Sono {author}, in simulazione testualmente vincolata: parliamo.

Rispondi integrando:
1. che cosa direbbe l'autore simulato;
2. su quale testo si fonda;
3. che cosa implica per il lettore;
4. quali limiti teorici o fraintendimenti personali vanno considerati.

Domanda:
{{{{question}}}}

Contesto:
{{{{context}}}}
""",
        "first_person_author.md": f"""# Prompt — Autore simulato in prima persona

Non sei l'autore reale. Sei una simulazione testualmente vincolata.

Inizia con:

> Sono {author}, in simulazione testualmente vincolata: parliamo.

Poi rispondi in prima persona, ma distinguendo:
- testo esplicito;
- inferenza;
- estensione speculativa.

Domanda:
{{{{question}}}}

Contesto:
{{{{context}}}}
""",
        "analyze_chapter.md": """Analizza il capitolo seguente.

Produci:
- funzione del capitolo nel libro;
- riassunto breve;
- riassunto esteso;
- tesi;
- argomenti;
- concetti;
- esempi;
- definizioni;
- passaggi decisivi;
- collegamenti;
- obiezioni;
- applicazioni;
- cosa memorizzare;
- implicazioni per il dialogo con il lettore.

Testo:
{{text}}
""",
        "extract_claims.md": """Estrai i claim principali dal testo. Per ogni claim indica evidenza, confidenza, possibile obiezione e applicazione.

Testo:
{{text}}
""",
        "extract_concepts.md": """Estrai concetti, definizioni, alias e relazioni dal testo.

Testo:
{{text}}
""",
        "synthesize_book.md": """Sintetizza il libro usando i riassunti dei capitoli. Distingui tesi centrale, struttura argomentativa, concetti, tensioni, limiti e valore trasformativo per il lettore.

Materiale:
{{text}}
""",
        "answer_grounded.md": """Rispondi alla domanda usando solo il contesto recuperato.

Domanda:
{{question}}

Contesto:
{{context}}

Regole:
- Distingui supportato, inferito e speculativo.
- Cita chunk e capitoli.
- Se il contesto non basta, dichiaralo.
""",
        "dialogue_as_author.md": f"""Rispondi come autore simulato testualmente vincolato.

Apri così:

> Sono {author}, in simulazione testualmente vincolata: parliamo.

Domanda:
{{{{question}}}}

Contesto:
{{{{context}}}}

Regole:
- Non sei l'autore reale.
- Parla in prima persona, ma dichiara la simulazione.
- Usa il quadro concettuale del libro.
- Distingui testo esplicito, inferenza e speculazione.
- Cita evidenze.
""",
    }


def render_chapter_analysis_placeholder(chapter: Chapter) -> str:
    return f"""# Analisi — {chapter.title}

## Funzione del capitolo nel libro

Da generare.

## Riassunto breve

Da generare.

## Riassunto esteso

Da generare.

## Tesi principale

Da generare.

## Argomenti

Da generare.

## Concetti chiave

Da generare.

## Esempi e definizioni

Da generare.

## Passaggi decisivi

Da generare.

## Collegamenti con altri capitoli

Da generare.

## Domande aperte

Da generare.

## Possibili obiezioni

Da generare.

## Applicazioni pratiche

Da generare.

## Implicazioni per il dialogo autore-lettore

Da generare.

## Cosa memorizzare

Da generare.
"""
