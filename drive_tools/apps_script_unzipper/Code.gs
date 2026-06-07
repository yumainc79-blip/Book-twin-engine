/**
 * Book Twin Drive Unzipper
 *
 * Web app Google Apps Script per estrarre uno ZIP caricato su Google Drive
 * dentro:
 *
 *   Book Twins/books/NOME_CARTELLA/
 *
 * Uso:
 * 1. Carica lo ZIP su Google Drive.
 * 2. Copia il link dello ZIP.
 * 3. Apri questa Web App.
 * 4. Incolla il link.
 * 5. Premi "Estrai ZIP".
 *
 * Deploy consigliato:
 * - Execute as: Me
 * - Who has access: Only myself
 */

const DEFAULT_LIBRARY_ROOT = "Book Twins";
const DEFAULT_BOOKS_FOLDER = "books";
const DEFAULT_INBOX_FOLDER = "_inbox_zip";

/**
 * Entry point della Web App.
 */
function doGet() {
  return HtmlService
    .createHtmlOutput(renderPage_())
    .setTitle("Book Twin Drive Unzipper")
    .setXFrameOptionsMode(HtmlService.XFrameOptionsMode.ALLOWALL);
}

/**
 * Funzione chiamata dal frontend.
 */
function unzipBookTwinZip(zipUrlOrId, optionalOutputName) {
  if (!zipUrlOrId || String(zipUrlOrId).trim() === "") {
    throw new Error("Inserisci il link o l'ID del file ZIP su Google Drive.");
  }

  const fileId = extractDriveFileId_(zipUrlOrId);
  const zipFile = DriveApp.getFileById(fileId);
  const zipName = zipFile.getName();

  if (!zipName.toLowerCase().endsWith(".zip")) {
    throw new Error("Il file selezionato non sembra essere uno ZIP: " + zipName);
  }

  const rootFolder = getOrCreateFolder_(DriveApp.getRootFolder(), DEFAULT_LIBRARY_ROOT);
  const booksFolder = getOrCreateFolder_(rootFolder, DEFAULT_BOOKS_FOLDER);

  const zipBlob = zipFile.getBlob();
  const blobs = Utilities.unzip(zipBlob);

  if (!blobs || blobs.length === 0) {
    throw new Error("Lo ZIP non contiene file estraibili.");
  }

  const normalizedEntries = blobs
    .map(function(blob) {
      return {
        blob: blob,
        path: normalizeZipPath_(blob.getName())
      };
    })
    .filter(function(entry) {
      return entry.path && !entry.path.endsWith("/");
    });

  if (normalizedEntries.length === 0) {
    throw new Error("Lo ZIP contiene solo cartelle vuote o percorsi non validi.");
  }

  const detectedRoot = detectSingleRootFolder_(normalizedEntries.map(function(e) {
    return e.path;
  }));

  const outputName = sanitizeName_(
    optionalOutputName ||
    detectedRoot ||
    zipName.replace(/\.zip$/i, "")
  );

  const outputFolder = createUniqueFolder_(booksFolder, outputName);

  let createdFiles = 0;
  let skippedFiles = 0;
  const errors = [];

  normalizedEntries.forEach(function(entry) {
    try {
      let relativePath = entry.path;

      if (detectedRoot && relativePath.indexOf(detectedRoot + "/") === 0) {
        relativePath = relativePath.substring(detectedRoot.length + 1);
      }

      if (!relativePath || relativePath.trim() === "") {
        skippedFiles++;
        return;
      }

      createFileFromPath_(outputFolder, relativePath, entry.blob);
      createdFiles++;
    } catch (err) {
      skippedFiles++;
      errors.push({
        path: entry.path,
        error: String(err && err.message ? err.message : err)
      });
    }
  });

  const readme = [
    "# Book Twin upload",
    "",
    "Cartella creata automaticamente da Book Twin Drive Unzipper.",
    "",
    "- ZIP originale: `" + zipName + "`",
    "- File creati: " + createdFiles,
    "- File saltati: " + skippedFiles,
    "- Data: " + new Date().toISOString(),
    "",
    "Se presente, apri `prompt_for_ai.md` per dialogare con il Book Twin."
  ].join("\n");

  outputFolder.createFile("UPLOAD_LOG.md", readme, MimeType.PLAIN_TEXT);

  return {
    ok: true,
    zipName: zipName,
    outputFolderName: outputFolder.getName(),
    outputFolderUrl: outputFolder.getUrl(),
    createdFiles: createdFiles,
    skippedFiles: skippedFiles,
    errors: errors
  };
}

/**
 * Estrae l'ID da link Drive o accetta direttamente l'ID.
 */
function extractDriveFileId_(input) {
  const value = String(input).trim();

  const patterns = [
    /\/file\/d\/([a-zA-Z0-9_-]+)/,
    /[?&]id=([a-zA-Z0-9_-]+)/,
    /\/open\?id=([a-zA-Z0-9_-]+)/,
    /^([a-zA-Z0-9_-]{20,})$/
  ];

  for (let i = 0; i < patterns.length; i++) {
    const match = value.match(patterns[i]);
    if (match && match[1]) {
      return match[1];
    }
  }

  throw new Error("Non riesco a trovare l'ID del file Drive nel link inserito.");
}

/**
 * Normalizza i percorsi interni dello ZIP.
 */
function normalizeZipPath_(path) {
  if (!path) return "";

  let normalized = String(path)
    .replace(/\\/g, "/")
    .replace(/^\/+/, "")
    .replace(/\/+/g, "/")
    .trim();

  normalized = normalized
    .split("/")
    .filter(function(part) {
      return part !== "" && part !== "." && part !== "..";
    })
    .join("/");

  return normalized;
}

/**
 * Se tutti i file stanno dentro una sola cartella root, la rileva.
 */
function detectSingleRootFolder_(paths) {
  const roots = {};

  paths.forEach(function(path) {
    const first = path.split("/")[0];
    if (first) roots[first] = true;
  });

  const keys = Object.keys(roots);

  if (keys.length === 1) {
    return keys[0];
  }

  return null;
}

/**
 * Crea un file rispettando un percorso relativo tipo:
 * canonical/chapters/001.md
 */
function createFileFromPath_(baseFolder, relativePath, blob) {
  const parts = relativePath.split("/").filter(Boolean);

  if (parts.length === 0) {
    return;
  }

  const fileName = sanitizeFileName_(parts.pop());
  let folder = baseFolder;

  parts.forEach(function(part) {
    folder = getOrCreateFolder_(folder, sanitizeName_(part));
  });

  const finalBlob = blob.copyBlob();
  finalBlob.setName(fileName);
  folder.createFile(finalBlob);
}

/**
 * Recupera o crea una sottocartella.
 */
function getOrCreateFolder_(parent, name) {
  const safeName = sanitizeName_(name);
  const folders = parent.getFoldersByName(safeName);

  if (folders.hasNext()) {
    return folders.next();
  }

  return parent.createFolder(safeName);
}

/**
 * Crea una cartella evitando conflitti:
 * nome
 * nome_2
 * nome_3
 */
function createUniqueFolder_(parent, baseName) {
  const safeBase = sanitizeName_(baseName || "book_twin");
  let name = safeBase;
  let counter = 2;

  while (parent.getFoldersByName(name).hasNext()) {
    name = safeBase + "_" + counter;
    counter++;
  }

  return parent.createFolder(name);
}

/**
 * Sanitizza nomi cartelle.
 */
function sanitizeName_(name) {
  return String(name || "untitled")
    .trim()
    .replace(/[\\/:*?"<>|#%{}^~[\]`]/g, "_")
    .replace(/\s+/g, "_")
    .replace(/_+/g, "_")
    .replace(/^_+|_+$/g, "")
    .substring(0, 120) || "untitled";
}

/**
 * Sanitizza nomi file preservando estensioni.
 */
function sanitizeFileName_(name) {
  return String(name || "file")
    .trim()
    .replace(/[\\/:*?"<>|#%{}^~[\]`]/g, "_")
    .replace(/\s+/g, "_")
    .replace(/_+/g, "_")
    .replace(/^_+|_+$/g, "")
    .substring(0, 180) || "file";
}

/**
 * HTML della Web App.
 */
function renderPage_() {
  return `
<!doctype html>
<html lang="it">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Book Twin Drive Unzipper</title>
  <style>
    :root {
      font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: #f3f4f6;
      color: #111827;
    }

    body {
      margin: 0;
      padding: 24px;
    }

    .wrap {
      max-width: 760px;
      margin: 0 auto;
    }

    .card {
      background: white;
      border: 1px solid #e5e7eb;
      border-radius: 20px;
      padding: 24px;
      box-shadow: 0 16px 35px rgba(15, 23, 42, 0.08);
    }

    h1 {
      margin-top: 0;
      font-size: 2rem;
    }

    p {
      line-height: 1.5;
    }

    label {
      display: block;
      margin-top: 18px;
      margin-bottom: 8px;
      font-weight: 700;
    }

    input {
      width: 100%;
      padding: 13px 14px;
      border: 1px solid #d1d5db;
      border-radius: 12px;
      font: inherit;
      box-sizing: border-box;
    }

    button {
      width: 100%;
      margin-top: 20px;
      padding: 14px 18px;
      border: 0;
      border-radius: 12px;
      background: #111827;
      color: white;
      font-weight: 800;
      font: inherit;
      cursor: pointer;
    }

    button:disabled {
      opacity: 0.6;
      cursor: wait;
    }

    pre {
      white-space: pre-wrap;
      word-wrap: break-word;
      background: #0f172a;
      color: #e5e7eb;
      padding: 16px;
      border-radius: 14px;
      overflow: auto;
      min-height: 120px;
    }

    .muted {
      color: #6b7280;
    }

    .ok {
      color: #166534;
      font-weight: 800;
    }

    .error {
      color: #991b1b;
      font-weight: 800;
    }

    .steps {
      padding-left: 20px;
    }

    a {
      color: #2563eb;
      font-weight: 700;
    }
  </style>
</head>
<body>
  <div class="wrap">
    <div class="card">
      <h1>Book Twin Drive Unzipper</h1>

      <p>
        Incolla il link dello ZIP caricato su Google Drive.
        Lo script lo estrarrà in:
      </p>

      <p><strong>Book Twins / books / nome_libro</strong></p>

      <ol class="steps">
        <li>Scarica lo ZIP dalla chat.</li>
        <li>Caricalo su Google Drive.</li>
        <li>Copia il link del file ZIP.</li>
        <li>Incollalo qui e premi <strong>Estrai ZIP</strong>.</li>
      </ol>

      <label for="zipUrl">Link o ID file ZIP Google Drive</label>
      <input id="zipUrl" type="text" placeholder="https://drive.google.com/file/d/.../view">

      <label for="outputName">Nome cartella finale opzionale</label>
      <input id="outputName" type="text" placeholder="es. daniel_kahneman_pensieri_lenti_e_veloci">

      <button id="runBtn" onclick="runUnzip()">Estrai ZIP</button>

      <h2>Risultato</h2>
      <pre id="result">In attesa...</pre>

      <p class="muted">
        Nota: al primo uso Google chiederà autorizzazione per accedere a Drive.
        È normale.
      </p>
    </div>
  </div>

  <script>
    function runUnzip() {
      const zipUrl = document.getElementById("zipUrl").value.trim();
      const outputName = document.getElementById("outputName").value.trim();
      const result = document.getElementById("result");
      const btn = document.getElementById("runBtn");

      if (!zipUrl) {
        result.textContent = "Inserisci il link o ID dello ZIP.";
        return;
      }

      btn.disabled = true;
      result.textContent = "Estrazione in corso...";

      google.script.run
        .withSuccessHandler(function(res) {
          btn.disabled = false;

          let message = "";
          message += "OK: ZIP estratto.\\n\\n";
          message += "ZIP: " + res.zipName + "\\n";
          message += "Cartella: " + res.outputFolderName + "\\n";
          message += "File creati: " + res.createdFiles + "\\n";
          message += "File saltati: " + res.skippedFiles + "\\n\\n";
          message += "Apri cartella Drive:\\n" + res.outputFolderUrl + "\\n";

          if (res.errors && res.errors.length) {
            message += "\\nErrori:\\n";
            res.errors.forEach(function(e) {
              message += "- " + e.path + ": " + e.error + "\\n";
            });
          }

          result.innerHTML =
            '<span class="ok">Estrazione completata.</span>\\n\\n' +
            escapeHtml(message) +
            '\\n<a href="' + res.outputFolderUrl + '" target="_blank">Apri cartella Book Twin</a>';
        })
        .withFailureHandler(function(err) {
          btn.disabled = false;
          result.innerHTML =
            '<span class="error">Errore.</span>\\n\\n' +
            escapeHtml(err.message || String(err));
        })
        .unzipBookTwinZip(zipUrl, outputName);
    }

    function escapeHtml(value) {
      return String(value)
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");
    }
  </script>
</body>
</html>
`;
}
