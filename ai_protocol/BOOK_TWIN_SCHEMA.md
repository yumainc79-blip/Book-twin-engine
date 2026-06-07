# BOOK TWIN SCHEMA

Ogni libro trasformato deve avere questa struttura minima:

```text
NOME_LIBRO/
  README.md
  llms.txt
  prompt_for_ai.md
  book.config.yaml

  canonical/
    book.md
    book.json
    chapters/

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
    objections.jsonl
    applications.jsonl
    questions.jsonl
    relations.jsonl
    book_graph.json

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

  sessions/
    README.md
```

Principio:
complessità interna, semplicità esterna.

L'utente non deve scegliere troppe modalità. Il default è `Dialogo integrato`.
