(() => {
  if (window.__ttcSRIFillListenerReady) return;
  window.__ttcSRIFillListenerReady = true;

  const SESSION_LOCK_KEY = "ttcSriAutomaticLoginAttempted";
  const SESSION_RESULT_KEY = "ttcSriAutomaticLoginResult";
  let credentials = null;
  let attempts = 0;
  let fillLoopStarted = false;
  let submissionScheduled = false;
  let loginSubmitted = false;
  let authMonitorTimer = null;
  let authObserver = null;
  const maxAttempts = 45;

  function sessionGet(key) {
    try { return sessionStorage.getItem(key); } catch (_) { return null; }
  }

  function sessionSet(key, value) {
    try { sessionStorage.setItem(key, value); } catch (error) {
      console.warn("[TotalCounts SRI] No se pudo guardar el bloqueo de seguridad de la pestaña.", error);
    }
  }

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

  function findCredentialError() {
    const candidates = Array.from(document.querySelectorAll(
      ".ui-messages-error, .ui-message-error, .ui-growl-message, .alert-danger, [role='alert'], .mensajeError, #mensajeError"
    ));
    const texts = candidates.map(el => (el.innerText || el.textContent || "").trim()).filter(Boolean);
    const bodyText = (document.body?.innerText || "").slice(0, 12000);
    const combined = texts.join(" | ") + " | " + bodyText;
    const patterns = [
      /usuario\\s*(?:o|y)\\s*(?:clave|contraseñ[ao])\\s*(?:es|son)?\\s*(?:incorrect[ao]s?|inv[aá]lid[ao]s?)/i,
      /(?:clave|contraseñ[ao])\\s*(?:incorrect[ao]|inv[aá]lid[ao])/i,
      /(?:credenciales|datos de acceso)\\s*(?:son|est[aá]n)?\\s*(?:incorrect[ao]s?|inv[aá]lid[ao]s?)/i,
      /usuario\\s*(?:incorrect[ao]|inv[aá]lid[ao])/i,
      /no se pudo iniciar sesi[oó]n/i,
      /ha excedido.{0,60}intentos|cuenta.{0,60}bloquead[ao]/i
    ];
    return patterns.some(pattern => pattern.test(combined))
      ? (texts.find(text => patterns.some(pattern => pattern.test(text))) || "El SRI rechazó las credenciales o bloqueó el acceso.")
      : "";
  }

  function showCredentialError(message) {
    credentials = null;
    loginSubmitted = true;
    if (authMonitorTimer) clearInterval(authMonitorTimer);
    if (authObserver) authObserver.disconnect();
    sessionSet(SESSION_RESULT_KEY, "rejected");
    document.documentElement.dataset.ttcSriFillStatus = "invalid-credentials";
    let notice = document.getElementById("ttcSriOneAttemptWarning");
    if (!notice) {
      notice = document.createElement("div");
      notice.id = "ttcSriOneAttemptWarning";
      notice.setAttribute("role", "alert");
      notice.style.cssText = [
        "position:fixed", "z-index:2147483647", "top:12px", "left:50%",
        "transform:translateX(-50%)", "max-width:min(720px,calc(100vw - 24px))",
        "padding:13px 18px", "border:1px solid #b42318", "border-radius:9px",
        "background:#fff5f4", "color:#8f1d16", "box-shadow:0 8px 28px rgba(0,0,0,.22)",
        "font:600 13px/1.5 Arial,sans-serif", "text-align:center"
      ].join(";");
      document.documentElement.appendChild(notice);
    }
    notice.textContent = "TotalCounts: el SRI rechazó el acceso. Se detuvo el inicio automático después de este único intento. Verifica la clave registrada antes de volver a intentarlo.";
    console.warn("[TotalCounts SRI] Acceso rechazado. No se realizarán más intentos en esta pestaña.", message);
  }

  function monitorCredentialResult() {
    const check = () => {
      const errorText = findCredentialError();
      if (errorText) showCredentialError(errorText);
    };
    check();
    if (document.body && !authObserver) {
      authObserver = new MutationObserver(check);
      authObserver.observe(document.body, { childList: true, subtree: true, characterData: true });
    }
    if (!authMonitorTimer && sessionGet(SESSION_RESULT_KEY) !== "rejected") {
      let checks = 0;
      authMonitorTimer = setInterval(() => {
        check();
        checks += 1;
        if (checks >= 60 || sessionGet(SESSION_RESULT_KEY) === "rejected") {
          clearInterval(authMonitorTimer);
          authMonitorTimer = null;
          if (authObserver) authObserver.disconnect();
          authObserver = null;
        }
      }, 500);
    }
  }

  // La sesión de pestaña sobrevive a recargas del portal. Así, un rechazo
  // de clave no vuelve a disparar el envío si el SRI recarga el formulario.
  if (sessionGet(SESSION_LOCK_KEY)) {
    loginSubmitted = true;
    document.documentElement.dataset.ttcSriFillStatus =
      sessionGet(SESSION_RESULT_KEY) === "rejected" ? "invalid-credentials" : "attempt-already-submitted";
    const waitForBody = setInterval(() => {
      if (!document.body) return;
      clearInterval(waitForBody);
      monitorCredentialResult();
      const errorText = findCredentialError();
      if (errorText) showCredentialError(errorText);
    }, 200);
    setTimeout(() => clearInterval(waitForBody), 10000);
  }

  function attemptFill() {
    if (!credentials || submissionScheduled || loginSubmitted) return;
    attempts += 1;
    const user = findUserInput();
    const password = Array.from(document.querySelectorAll('input[type="password"]')).find(visible);

    if (user && password) {
      setNativeValue(user, credentials.ruc);
      setNativeValue(password, credentials.clave);

      if (user.value === credentials.ruc && password.value === credentials.clave) {
        document.documentElement.dataset.ttcSriFillStatus = "filled";
        if (submissionScheduled || loginSubmitted) return;
        submissionScheduled = true;
        setTimeout(() => {
          if (loginSubmitted || sessionGet(SESSION_LOCK_KEY)) return;
          const currentUser = findUserInput();
          const currentPassword = Array.from(document.querySelectorAll('input[type="password"]')).find(visible);
          const submit = findSubmitButton();

          if (!currentUser || !currentPassword ||
              currentUser.value !== credentials.ruc ||
              currentPassword.value !== credentials.clave) {
            submissionScheduled = false;
            document.documentElement.dataset.ttcSriFillStatus = "verification-failed";
            console.warn("[TotalCounts SRI] No se envió el formulario: los campos cambiaron antes del envío.");
            return;
          }
          if (!submit) {
            submissionScheduled = false;
            document.documentElement.dataset.ttcSriFillStatus = "submit-not-found";
            console.warn("[TotalCounts SRI] Campos rellenados, pero no se encontró el botón Ingresar.");
            return;
          }

          // Bloqueo persistente antes del clic: máximo un envío automático
          // por pestaña, incluso si el portal rechaza la clave y se recarga.
          sessionSet(SESSION_LOCK_KEY, String(Date.now()));
          sessionSet(SESSION_RESULT_KEY, "submitted");
          loginSubmitted = true;
          credentials = null;
          document.documentElement.dataset.ttcSriFillStatus = "submitting";
          monitorCredentialResult();
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
    if (fillLoopStarted || submissionScheduled || loginSubmitted || sessionGet(SESSION_LOCK_KEY)) return;
    credentials = { ruc: String(message.ruc || ""), clave: String(message.clave || "") };
    if (!/^\\d{13}$/.test(credentials.ruc) || !credentials.clave) {
      document.documentElement.dataset.ttcSriFillStatus = "invalid-credentials";
      return;
    }
    fillLoopStarted = true;
    document.documentElement.dataset.ttcSriFillStatus = "credentials-received";
    attemptFill();
  });
})();
