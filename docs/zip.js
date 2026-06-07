window.BookTwinZip = (() => {
  let current = null;

  function normalizePath(path) {
    return String(path || "")
      .replaceAll("\\", "/")
      .replace(/^\/+/, "")
      .replace(/\/+/g, "/")
      .trim();
  }

  function isJunk(path) {
    return path.startsWith("__MACOSX/") || path === "__MACOSX" || path.endsWith("/.DS_Store") || path === ".DS_Store";
  }

  function detectRoot(paths) {
    const roots = new Set(paths.map(p => p.split("/")[0]).filter(Boolean));
    return roots.size === 1 ? Array.from(roots)[0] : null;
  }

  function guessFolderName(fileName, root) {
    return sanitizeName(root || fileName.replace(/\.zip$/i, ""));
  }

  function sanitizeName(name) {
    return String(name || "book_twin")
      .trim()
      .replace(/[\\/:*?"<>|#%{}^~[\]`]/g, "_")
      .replace(/\s+/g, "_")
      .replace(/_+/g, "_")
      .replace(/^_+|_+$/g, "")
      .slice(0, 120) || "book_twin";
  }

  async function readZip(file) {
    const zip = await JSZip.loadAsync(file);
    const entries = [];

    zip.forEach((relativePath, entry) => {
      const path = normalizePath(relativePath);
      if (!path || isJunk(path) || entry.dir) return;
      entries.push({ path, entry });
    });

    if (!entries.length) throw new Error("Lo ZIP non contiene file validi.");

    const root = detectRoot(entries.map(e => e.path));
    const cleanEntries = entries.map(item => {
      let rel = item.path;
      if (root && rel.startsWith(root + "/")) rel = rel.slice(root.length + 1);
      return { path: rel, entry: item.entry };
    }).filter(item => item.path);

    current = {
      fileName: file.name,
      root,
      folderName: guessFolderName(file.name, root),
      entries: cleanEntries
    };

    return current;
  }

  async function getBlob(entry) {
    return await entry.async("blob");
  }

  return {
    readZip,
    getBlob,
    sanitizeName,
    get current() { return current; }
  };
})();
