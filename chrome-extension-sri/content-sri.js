(() => {
  if (window.__ttcSRIFillListenerReady) return;
  window.__ttcSRIFillListenerReady = true;

  let credentials = null;
  let attempts = 0;
  const maxAttempts = 45;

  function visible(el) {
    return el instanceof HTMLInputElement && el.getClientRects().length > 0 &&
      !el.disabled && el.type !== "hidden";
  }

  function findUserInput() {
    const candidates = Array.from(document.querySelectorAll("input")).filter(visible);
    const password = candidates.find(el => el.type === "password");
    if (!password) return null;
    const explicit = candidates.find(el => el !== password &&
      /ruc|pasaporte|usuario|identificaci/i.test(
        [el.name, el.id, el.placeholder, el.getAttribute("aria-label"), el.parentElement?.innerText]
          .filter(Boolean).join(" ")
      ));
    if (explicit) return explicit;
    return candidates.find(el => el !== password &&
      ["text", "tel", "number"].includes((el.type || "").toLowerCase())) || null;
  }

  function findSubmitButton() {
    const elements = Array.from(document.querySelectorAll("button, input[type='submit'], input[type='button']"))
      .filter(el => el.getClientRects().length > 0 && !el.disabled);
    return elements.find(el => {
      const text = (el.innerText || el.value || el.getAttribute("aria-label") || "").trim();
      return /^ingresar$/i.test(text);
    }) || null;
  }

  function setNativeValue(input, value) {
    const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")?.set;
    if (setter) setter.call(input, value);
    else input.value = value;
    input.dispatchEvent(new Event("input", { bubbles: true }));
    input.dispatchEvent(new Event("change", { bubbles: true }));
  }

  function attemptFill() {
    if (!credentials) return;
    attempts += 1;
    const user = findUserInput();
    const password = Array.from(document.querySelectorAll('input[type="password"]')).find(visible);

    if (user && password) {
      setNativeValue(user, credentials.ruc);
      setNativeValue(password, credentials.clave);

      if (user.value === credentials.ruc && password.value === credentials.clave) {
        document.documentElement.dataset.ttcSriFillStatus = "filled";
        // Give the SRI page a moment to process input/change events before clicking.
        setTimeout(() => {
          const currentUser = findUserInput();
          const currentPassword = Array.from(document.querySelectorAll('input[type="password"]')).find(visible);
          const submit = findSubmitButton();

          if (!currentUser || !currentPassword ||
              currentUser.value !== credentials.ruc ||
              currentPassword.value !== credentials.clave) {
            document.documentElement.dataset.ttcSriFillStatus = "verification-failed";
            console.warn("[TotalCounts SRI] No se envió el formulario: los campos cambiaron antes del envío.");
            return;
          }
          if (!submit) {
            document.documentElement.dataset.ttcSriFillStatus = "submit-not-found";
            console.warn("[TotalCounts SRI] Campos rellenados, pero no se encontró el botón Ingresar.");
            return;
          }

          document.documentElement.dataset.ttcSriFillStatus = "submitting";
          submit.click();
        }, 400);
        return;
      }
    }

    if (attempts < maxAttempts) setTimeout(attemptFill, 500);
    else {
      document.documentElement.dataset.ttcSriFillStatus = "fields-not-found";
      console.warn("[TotalCounts SRI] No se localizaron los campos de acceso.");
    }
  }

  chrome.runtime.onMessage.addListener((message) => {
    if (message?.type !== "TTCWEB_FILL_SRI_CREDENTIALS") return;
    credentials = { ruc: String(message.ruc || ""), clave: String(message.clave || "") };
    if (!/^\d{13}$/.test(credentials.ruc) || !credentials.clave) {
      document.documentElement.dataset.ttcSriFillStatus = "invalid-credentials";
      return;
    }
    document.documentElement.dataset.ttcSriFillStatus = "credentials-received";
    attemptFill();
  });
})();
