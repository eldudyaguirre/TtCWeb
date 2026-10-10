const DESTINATIONS = {
  SRI: {
    url: "https://srienlinea.sri.gob.ec/sri-en-linea/contribuyente/perfil",
    allowed: "https://srienlinea.sri.gob.ec/",
    message: "TTCWEB_FILL_SRI_CREDENTIALS"
  },
  IESS: {
    url: "https://www.iess.gob.ec/empleador-web/pages/principal.jsf",
    allowed: "https://www.iess.gob.ec/empleador-web/",
    message: "TTCWEB_FILL_IESS_CREDENTIALS"
  }
};

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  const isSRI = message?.type === "TTCWEB_OPEN_SRI";
  const isIESS = message?.type === "TTCWEB_OPEN_IESS";
  if (!isSRI && !isIESS) return;

  if (!sender.tab?.url || !sender.tab.url.startsWith("https://totalcounts.com.ec/totalcounts/")) {
    sendResponse({ ok: false, error: "Origen no autorizado." });
    return;
  }

  const kind = isSRI ? "SRI" : "IESS";
  const destination = DESTINATIONS[kind];
  const usuario = String(message.usuario || message.ruc || "").trim();
  const clave = String(message.clave || "");
  if (!usuario || !clave || (kind === "SRI" && !/^\d{13}$/.test(usuario))) {
    sendResponse({ ok: false, error: "Usuario o clave no válidos." });
    return;
  }

  chrome.tabs.create({ url: destination.url, active: true }, (tab) => {
    if (chrome.runtime.lastError || !tab?.id) {
      sendResponse({ ok: false, error: chrome.runtime.lastError?.message || "No se pudo abrir el portal." });
      return;
    }

    const tabId = tab.id;
    let delivered = false;
    const deadline = Date.now() + 30000;
    const listener = (updatedTabId, changeInfo, updatedTab) => {
      if (updatedTabId !== tabId || delivered) return;
      const url = updatedTab?.url || "";
      if (url && !url.startsWith(destination.allowed)) return;
      if (changeInfo.status !== "complete" && Date.now() < deadline) return;

      chrome.tabs.sendMessage(tabId, { type: destination.message, usuario, ruc: usuario, clave }, () => {
        if (chrome.runtime.lastError) {
          if (Date.now() >= deadline) chrome.tabs.onUpdated.removeListener(listener);
          return;
        }
        delivered = true;
        chrome.tabs.onUpdated.removeListener(listener);
      });
    };
    chrome.tabs.onUpdated.addListener(listener);
    sendResponse({ ok: true });
  });
  return true;
});
