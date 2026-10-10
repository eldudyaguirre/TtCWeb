const SRI_URL = "https://srienlinea.sri.gob.ec/sri-en-linea/contribuyente/perfil";

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

    chrome.tabs.create({ url: SRI_URL, active: true }, (tab) => {
      if (chrome.runtime.lastError || !tab?.id) {
        sendResponse({ ok: false, error: chrome.runtime.lastError?.message || "No se pudo crear la pestaña del SRI." });
        return;
      }

      const tabId = tab.id;
      let delivered = false;
      const deadline = Date.now() + 30000;

      const deliverWhenReady = (updatedTabId, changeInfo, updatedTab) => {
        if (updatedTabId !== tabId || delivered) return;
        const url = updatedTab?.url || "";
        if (url && !url.startsWith("https://srienlinea.sri.gob.ec/")) return;
        if (changeInfo.status !== "complete" && Date.now() < deadline) return;

        chrome.tabs.sendMessage(tabId, { type: "TTCWEB_FILL_SRI_CREDENTIALS", ruc, clave }, (response) => {
          if (chrome.runtime.lastError) {
            if (Date.now() < deadline) return;
            chrome.tabs.onUpdated.removeListener(deliverWhenReady);
            return;
          }
          delivered = true;
          chrome.tabs.onUpdated.removeListener(deliverWhenReady);
        });
      };

      chrome.tabs.onUpdated.addListener(deliverWhenReady);
      sendResponse({ ok: true });
    });
    return true;
  }
});
