(() => {
  let attempts = 0;
  const maxAttempts = 30;

  function locateVisible(selectors) {
    for (const selector of selectors) {
      for (const element of document.querySelectorAll(selector)) {
        if (element instanceof HTMLInputElement && element.offsetParent !== null) return element;
      }
    }
    return null;
  }

  function fillCredentials(credentials) {
    const user = locateVisible([
      'input[name="usuario"]', 'input[name="ruc"]',
      'input[id*="usuario"]', 'input[id*="ruc"]',
      'input[placeholder*="RUC"]', 'input[type="text"]'
    ]);
    const password = locateVisible([
      'input[type="password"]', 'input[name="clave"]',
      'input[name="password"]', 'input[id*="clave"]'
    ]);

    if (!user || !password) {
      if (++attempts < maxAttempts) setTimeout(() => fillCredentials(credentials), 1000);
      return;
    }

    const setValue = (input, value) => {
      const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value").set;
      setter.call(input, value);
      input.dispatchEvent(new Event("input", { bubbles: true }));
      input.dispatchEvent(new Event("change", { bubbles: true }));
    };

    setValue(user, credentials.ruc);
    setValue(password, credentials.clave);
    // Intencionalmente no se hace clic en Ingresar ni se envía el formulario.
  }

  chrome.runtime.sendMessage({ type: "TTCWEB_GET_SRI_CREDENTIALS" }, (response) => {
    if (chrome.runtime.lastError || !response?.ok) return;
    fillCredentials(response);
  });
})();
