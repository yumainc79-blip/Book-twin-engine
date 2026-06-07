let selectedZip = null;

const $ = id => document.getElementById(id);

function log(message) {
  $("log").textContent += "\n" + message;
}

function setLog(message) {
  $("log").textContent = message;
}

function sanitizeFileName(path) {
  const parts = path.split("/");
  return parts[parts.length - 1] || "file";
}

async function inspectZip() {
  const file = $("zipInput").files[0];
  if (!file) {
    $("preview").textContent = "Seleziona prima uno ZIP.";
    return;
  }

  try {
    selectedZip = await BookTwinZip.readZip(file);
    $("folderName").value = $("folderName").value || selectedZip.folderName;

    const sample = selectedZip.entries.slice(0, 80).map(e => "- " + e.path).join("\n");
    $("preview").textContent =
      "ZIP: " + selectedZip.fileName + "\n" +
      "Root interna: " + (selectedZip.root || "(nessuna)") + "\n" +
      "File validi: " + selectedZip.entries.length + "\n\n" +
      sample + (selectedZip.entries.length > 80 ? "\n..." : "");

    $("uploadBtn").disabled = false;
  } catch (err) {
    $("preview").textContent = "Errore: " + err.message;
    $("uploadBtn").disabled = true;
  }
}

async function uploadToDrive() {
  if (!selectedZip) return;

  const finalFolderName = BookTwinZip.sanitizeName($("folderName").value || selectedZip.folderName);
  setLog("Creo cartelle su Drive...");

  try {
    const cfg = window.BOOK_TWIN_CONFIG;
    const root = await BookTwinDrive.getOrCreateFolder(cfg.driveRootFolder || "Book Twin");
    const books = await BookTwinDrive.getOrCreateFolder(cfg.booksFolder || "books", root.id);
    const bookFolder = await BookTwinDrive.getOrCreateFolder(finalFolderName, books.id);

    const folderCache = new Map();
    folderCache.set("", bookFolder.id);

    for (let i = 0; i < selectedZip.entries.length; i++) {
      const item = selectedZip.entries[i];
      const parts = item.path.split("/");
      const fileName = parts.pop();
      const dirPath = parts.join("/");

      let parentId = folderCache.get(dirPath);
      if (!parentId) {
        let currentPath = "";
        let currentParent = bookFolder.id;
        for (const part of parts) {
          currentPath = currentPath ? currentPath + "/" + part : part;
          if (!folderCache.has(currentPath)) {
            const folder = await BookTwinDrive.getOrCreateFolder(part, currentParent);
            folderCache.set(currentPath, folder.id);
          }
          currentParent = folderCache.get(currentPath);
        }
        parentId = currentParent;
      }

      const blob = await BookTwinZip.getBlob(item.entry);
      await BookTwinDrive.uploadFile(fileName, parentId, blob);
      log("[" + (i + 1) + "/" + selectedZip.entries.length + "] " + item.path);
    }

    const uploadLog = new Blob([
      "# Upload Book Twin\n\n",
      "- ZIP: `" + selectedZip.fileName + "`\n",
      "- Cartella: `" + finalFolderName + "`\n",
      "- File caricati: " + selectedZip.entries.length + "\n",
      "- Data: " + new Date().toISOString() + "\n"
    ], { type: "text/markdown" });

    await BookTwinDrive.uploadFile("UPLOAD_LOG.md", bookFolder.id, uploadLog);
    log("\nCompletato. Cartella Drive: https://drive.google.com/drive/folders/" + bookFolder.id);
  } catch (err) {
    log("\nERRORE: " + err.message);
  }
}

function setup() {
  $("loginBtn").addEventListener("click", () => {
    try {
      BookTwinDrive.login();
    } catch (err) {
      $("authStatus").textContent = err.message;
    }
  });

  window.addEventListener("booktwin-auth", () => {
    $("authStatus").textContent = "Connesso a Google Drive.";
  });

  $("inspectBtn").addEventListener("click", inspectZip);
  $("uploadBtn").addEventListener("click", uploadToDrive);

  if ("serviceWorker" in navigator) {
    navigator.serviceWorker.register("./sw.js").catch(() => {});
  }
}

setup();
