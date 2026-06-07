window.BookTwinDrive = (() => {
  const SCOPE = "https://www.googleapis.com/auth/drive.file";
  let tokenClient = null;
  let accessToken = null;

  function config() {
    return window.BOOK_TWIN_CONFIG || {};
  }

  function init() {
    const clientId = config().googleClientId;
    if (!clientId || clientId.includes("PASTE_YOUR")) {
      throw new Error("Configura googleClientId in docs/config.js.");
    }
    tokenClient = google.accounts.oauth2.initTokenClient({
      client_id: clientId,
      scope: SCOPE,
      callback: tokenResponse => {
        if (tokenResponse.error) throw new Error(tokenResponse.error);
        accessToken = tokenResponse.access_token;
        window.dispatchEvent(new CustomEvent("booktwin-auth", { detail: { ok: true } }));
      }
    });
  }

  function login() {
    if (!tokenClient) init();
    tokenClient.requestAccessToken({ prompt: "consent" });
  }

  function ensureAuth() {
    if (!accessToken) throw new Error("Accedi prima con Google.");
  }

  async function api(path, options = {}) {
    ensureAuth();
    const res = await fetch("https://www.googleapis.com/drive/v3" + path, {
      ...options,
      headers: {
        Authorization: "Bearer " + accessToken,
        ...(options.headers || {})
      }
    });
    const text = await res.text();
    const data = text ? JSON.parse(text) : {};
    if (!res.ok) throw new Error(data.error?.message || res.statusText);
    return data;
  }

  async function findFolder(name, parentId) {
    const escaped = name.replaceAll("'", "\\'");
    const q = [
      "mimeType='application/vnd.google-apps.folder'",
      "trashed=false",
      "name='" + escaped + "'",
      parentId ? "'" + parentId + "' in parents" : "'root' in parents"
    ].join(" and ");

    const data = await api("/files?q=" + encodeURIComponent(q) + "&fields=files(id,name)");
    return data.files?.[0] || null;
  }

  async function createFolder(name, parentId) {
    const body = {
      name,
      mimeType: "application/vnd.google-apps.folder",
      parents: parentId ? [parentId] : undefined
    };
    return await api("/files?fields=id,name,webViewLink", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body)
    });
  }

  async function getOrCreateFolder(name, parentId) {
    return await findFolder(name, parentId) || await createFolder(name, parentId);
  }

  async function uploadFile(name, parentId, blob) {
    ensureAuth();
    const metadata = { name, parents: [parentId] };
    const form = new FormData();
    form.append("metadata", new Blob([JSON.stringify(metadata)], { type: "application/json" }));
    form.append("file", blob);

    const res = await fetch("https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart&fields=id,name,webViewLink", {
      method: "POST",
      headers: { Authorization: "Bearer " + accessToken },
      body: form
    });

    const data = await res.json();
    if (!res.ok) throw new Error(data.error?.message || res.statusText);
    return data;
  }

  return {
    login,
    getOrCreateFolder,
    uploadFile,
    get accessToken() { return accessToken; }
  };
})();
