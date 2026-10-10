(() => {
  if (window.__ttcAccessExtensionReady) return;
  window.__ttcAccessExtensionReady = true;

  document.addEventListener("click", (event) => {
    const sriButton = event.target.closest(".admin-passwords-sri-login");
    const iessButton = event.target.closest(".admin-passwords-iess-login");
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

    chrome.runtime.sendMessage({
      type: isIESS ? "TTCWEB_OPEN_IESS" : "TTCWEB_OPEN_SRI",
      usuario,
      ruc: usuario,
      clave
    }, response => {
      if (chrome.runtime.lastError || !response?.ok) {
        alert("No se pudo abrir el portal. " +
          (response?.error || chrome.runtime.lastError?.message || "Revisa que la extensión esté actualizada."));
        return;
      }
      alert(isIESS
        ? "Se abrió el IESS para " + nombre + ". La extensión rellenará los datos y pulsará Ingresar."
        : "Se abrió el SRI para " + nombre + ". La extensión rellenará los datos y pulsará Ingresar.");
    });
  }, true);
})();
