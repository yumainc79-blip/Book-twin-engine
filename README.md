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
-