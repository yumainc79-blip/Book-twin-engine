# DRIVE OUTPUT STRUCTURE

Struttura consigliata su Google Drive:

```text
Book Twins/
  _catalog/
    catalog.md
    catalog.json

  books/
    autore_titolo/
      README.md
      llms.txt
      prompt_for_ai.md
      canonical/
      analysis/
      knowledge/
      author_model/
      dialogue/
      reader_reflection/
      personas/
      prompts/
      sessions/
      exports/
      logs/

  _templates/
  exports/
```

Per ogni libro:
1. crea una cartella con slug `autore_titolo`;
2. inserisci tutti i file del Book Twin;
3. se possibile, crea una sottocartella privata `source/` per il file originale posseduto dall'utente;
4. aggiorna `_catalog/catalog.md` e `_catalog/catalog.json`.
