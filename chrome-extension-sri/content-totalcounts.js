(() => {
  if (window.__ttcAccessExtensionReady) return;
  window.__ttcAccessExtensionReady = true;

  async function ttcFingerprint(value, salt) {
    if (!salt || !globalThis.crypto?.subtle) return "no-disponible";
    const digest = await crypto.subtle.digest(
      "SHA-256",
      new TextEncoder().encode(salt + ":" + value)
    );
    return Array.from(new Uint8Array(digest))
      .map(byte => byte.toString(16).padStart(2, "0"))
      .join("")
      .slice(0, 16);
  }

  document.addEventListener("click", async (event) => {
    const target = event.target instanceof Element ? event.target : event.target?.parentElement;
    if (!target) return;
    const sriButton = target.closest(".admin-passwords-sri-login");
    const iessButton = target.closest(".admin-passwords-iess-login");
    const button = sriButton || iessButton;
    if (!button) return;

    event.preventDefault();
    event.stopImmediatePropagation();

    const isIESS = Boolean(iessButton);
    const usuario = (button.dataset.usuario || button.dataset.ruc || "").trim();
    const clave = button.dataset.clave || "";
    const nombre = button.dataset.nombre || "cliente";

    if (!usuario || !clave || (!isIESS && !/^\d{13}$/.test(usuario))) {
      alert("Este cliente no tiene usuario/RUC y clave válidos para este portal.");
      return;
    }

    const diagnosticSalt = Array.from(crypto.getRandomValues(new Uint8Array(16))).map(byte => byte.toString(16).padStart(2, "0")).join("");
    let sourceFingerprint = "no-disponible";
    try {
      sourceFingerprint = await ttcFingerprint(clave, diagnosticSalt);
    } catch (error) {
      console.warn("[TotalCounts SRI diagnóstico] No se pudo calcular la huella de origen.", error);
    }
    console.info("[TotalCounts SRI diagnóstico] Origen:", { longitud: clave.length, huella: sourceFingerprint });
    chrome.runtime.sendMessage({
      type: isIESS ? "TTCWEB_OPEN_IESS" : "TTCWEB_OPEN_SRI",
      usuario, ruc: usuario, clave, diagnosticSalt, sourceFingerprint,
      diagnosticOnly: false
    }, response => {
      if (chrome.runtime.lastError || !response?.ok) {
        alert("No se pudo abrir el portal. " +
          (response?.error || chrome.runtime.lastError?.message || "Revisa que la extensión esté actualizada."));
        return;
      }
      alert(isIESS
        ? "Se abrió el IESS para " + nombre + ". La extensión rellenará los datos y pulsará Ingresar."
        : "Se abrió el SRI para " + nombre + ". La extensión rellenará los datos e intentará ingresar una sola vez.");
    });
  }, true);
})();
