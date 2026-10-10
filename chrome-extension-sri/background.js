const SRI_URL = "https://srienlinea.sri.gob.ec/sri-en-linea/contribuyente/perfil";

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message?.type === "TTCWEB_OPEN_SRI") {
    if (!sender.tab?.url || !sender.tab.url.startsWith("https://totalcounts.com.ec/totalcounts/")) {
      sendResponse({ ok: false, error: "Origen no autorizado." });
      return;
    }
    const ruc = String(message.ruc || "").trim();
    const clave = String(message.clave || "");
    if (!/^\\d{13}$/.test(ruc) || !clave) {
      sendResponse({ ok: false, error: "RUC o clave no válidos." });
      return;
    }

    // Session-only storage survives service-worker suspension without persisting credentials.
    chrome.storage.session.set({
      pendingSriCredentials: { ruc, clave, createdAt: Date.now() }
    }, () => {
      if (chrome.runtime.lastError) {
        sendResponse({ ok: false, error: "No se pudieron preparar los datos de la sesión." });
        return;
      }
      chrome.tabs.create({ url: SRI_URL, active: true }, (tab) => {
        if (chrome.runtime.lastError) {
          chrome.storage.session.remove("pendingSriCredentials");
          sendResponse({ ok: false, error: chrome.runtime.lastError.message });
          return;
        }
        sendResponse({ ok: true });
      });
    });
    return true;
  }

  if (message?.type === "TTCWEB_GET_SRI_CREDENTIALS") {
    if (!sender.tab?.url || !sender.tab.url.startsWith("https://srienlinea.sri.gob.ec/")) {
      sendResponse({ ok: false });
      return;
    }
    chrome.storage.session.get("pendingSriCredentials", (stored) => {
      const credentials = stored.pendingSriCredentials;
      if (!credentials || Date.now() - credentials.createdAt > 120000) {
        chrome.storage.session.remove("pendingSriCredentials");
        sendResponse({ ok: false });
        return;
      }
      chrome.storage.session.remove("pendingSriCredentials", () => {
        sendResponse({ ok: true, ruc: credentials.ruc, clave: credentials.clave });
      });
    });
    return true;
  }
});
