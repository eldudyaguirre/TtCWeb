const SRI_URL = "https://srienlinea.sri.gob.ec/sri-en-linea/contribuyente/perfil";
let pendingCredentials = null;

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message?.type === "TTCWEB_OPEN_SRI") {
    if (!sender.tab?.url || !sender.tab.url.startsWith("https://totalcounts.com.ec/totalcounts/")) {
      sendResponse({ ok: false, error: "Origen no autorizado." });
      return;
    }
    const ruc = String(message.ruc || "").trim();
    const clave = String(message.clave || "");
    if (!/^\d{13}$/.test(ruc) || !clave) {
      sendResponse({ ok: false, error: "RUC o clave no válidos." });
      return;
    }
    pendingCredentials = { ruc, clave, createdAt: Date.now() };
    chrome.tabs.create({ url: SRI_URL, active: true }, (tab) => {
      if (chrome.runtime.lastError) {
        pendingCredentials = null;
        sendResponse({ ok: false, error: chrome.runtime.lastError.message });
        return;
      }
      sendResponse({ ok: true });
    });
    return true;
  }
  if (message?.type === "TTCWEB_GET_SRI_CREDENTIALS") {
    if (!sender.tab?.url || !sender.tab.url.startsWith("https://srienlinea.sri.gob.ec/")) {
      sendResponse({ ok: false });
      return;
    }
    if (!pendingCredentials || Date.now() - pendingCredentials.createdAt > 60000) {
      pendingCredentials = null;
      sendResponse({ ok: false });
      return;
    }
    const credentials = pendingCredentials;
    pendingCredentials = null;
    sendResponse({ ok: true, ruc: credentials.ruc, clave: credentials.clave });
  }
});
