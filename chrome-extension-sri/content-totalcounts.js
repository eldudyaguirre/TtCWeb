(() => {
  if (window.__ttcSRIExtensionReady) return;
  window.__ttcSRIExtensionReady = true;

  document.addEventListener("click", (event) => {
    const button = event.target.closest(".admin-passwords-sri-login");
    if (!button) return;

    const ruc = (button.dataset.ruc || "").trim();
    const clave = button.dataset.clave || "";
    const nombre = button.dataset.nombre || "cliente";
    if (!/^\d{13}$/.test(ruc) || !clave) {
      event.preventDefault();
      event.stopImmediatePropagation();
      alert("Este cliente no tiene un RUC o una clave SRI válidos.");
      return;
    }

    event.preventDefault();
    event.stopImmediatePropagation();
    chrome.runtime.sendMessage(
      { type: "TTCWEB_OPEN_SRI", ruc, clave },
      (response) => {
        if (chrome.runtime.lastError || !response?.ok) {
          alert("No se pudo abrir el SRI con la extensión. Comprueba que esté instalada y habilitada.");
          return;
        }
        alert("Se abrió el SRI para " + nombre + ". Los campos se rellenarán sin iniciar sesión automáticamente.");
      }
    );
  }, true);
})();
