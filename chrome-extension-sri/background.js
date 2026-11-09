  async function ttcFingerprint(value, salt) {
    if (!salt || !globalThis.crypto?.subtle) return "no-disponible";
    const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(salt + ":" + value));
    return Array.from(new Uint8Array(digest)).map(byte => byte.toString(16).padStart(2, "0")).join("").slice(0, 16);
  }

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

  if (!sender.tab?.url || !(/^https:\/\/(?:www\.)?totalcounts\.com\.ec\/totalcounts\//).test(sender.tab.url)) {
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
    let deliveryInProgress = false;
    const deadline = Date.now() + 30000;
    const attemptId = crypto.randomUUID();
    let backgroundFingerprint = "";
    ttcFingerprint(clave, message.diagnosticSalt).then(value => {
      backgroundFingerprint = value;
      console.info("[TotalCounts SRI diagnóstico] Background:", {
        longitud: clave.length,
        huella: backgroundFingerprint,
        coincideOrigen: backgroundFingerprint === message.sourceFingerprint
      });
    }).catch(() => {});

    // El content script se inyecta en document_idle. Reintentar evita perder
    // el primer mensaje si la pestaña termina de cargar antes de estar listo.
    const deliveryTimer = setInterval(() => {
      if (delivered || deliveryInProgress) return;
      if (Date.now() >= deadline) {
        clearInterval(deliveryTimer);
        return;
      }
      deliveryInProgress = true;
      chrome.tabs.get(tabId, currentTab => {
        if (chrome.runtime.lastError || !currentTab?.url?.startsWith(destination.allowed)) {
          deliveryInProgress = false;
          return;
        }
        if (currentTab.status !== "complete") {
          deliveryInProgress = false;
          return;
        }
        chrome.tabs.sendMessage(tabId, {
          type: destination.message, usuario, ruc: usuario, clave, attemptId,
          diagnosticSalt: message.diagnosticSalt,
          sourceFingerprint: message.sourceFingerprint,
          backgroundFingerprint
        }, () => {
          if (chrome.runtime.lastError) {
            deliveryInProgress = false;
            return;
          }
          delivered = true;
          clearInterval(deliveryTimer);
        });
      });
    }, 500);
    sendResponse({ ok: true });
  });
  return true;
});
