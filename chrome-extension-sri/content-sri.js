(() => {
  if (window.__ttcSRIFillStarted) return;
  window.__ttcSRIFillStarted = true;

  let credentials = null;
  let attempts = 0;
  const maxAttempts = 45;

  function visible(el) {
    return el instanceof HTMLInputElement &&
      el.getClientRects().length > 0 &&
      !el.disabled &&
      el.type !== "hidden";
  }

  function findUserInput() {
    const candidates = Array.from(document.querySelectorAll("input")).filter(visible);
    // SRI login page commonly has two text-like inputs: RUC/CI/passport and optional additional ID.
    const password = candidates.find(el => el.type === "password");
    if (!password) return null;

    const explicit = candidates.find(el =>
      el !== password &&
      /ruc|pasaporte|usuario|identificaci/i.test(
        [el.name, el.id, el.placeholder, el.getAttribute("aria-label"), el.parentElement?.innerText]
          .filter(Boolean).join(" ")
      )
    );
    if (explicit) return explicit;

    const textInputs = candidates.filter(el =>
      el !== password && ["text", "tel", "number"].includes((el.type || "").toLowerCase())
    );
    return textInputs[0] || null;
  }

  function setNativeValue(input, value) {
    const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")?.set;
    if (setter) setter.call(input, value);
    else input.value = value;
    input.dispatchEvent(new Event("input", { bubbles: true }));
    input.dispatchEvent(new Event("change", { bubbles: true }));
    input.dispatchEvent(new Event("blur", { bubbles: true }));
  }

  function attemptFill() {
    if (!credentials) return;
    attempts += 1;

    const user = findUserInput();
    const password = Array.from(document.querySelectorAll('input[type="password"]')).find(visible);

    if (user && password) {
      setNativeValue(user, credentials.ruc);
      setNativeValue(password, credentials.clave);

      // Verify the values were accepted by the visible inputs.
      if (user.value === credentials.ruc && password.value === credentials.clave) {
        document.documentElement.dataset.ttcSriFillStatus = "filled";
        return;
      }
    }

    if (attempts < maxAttempts) {
      setTimeout(attemptFill, 500);
    } else {
      document.documentElement.dataset.ttcSriFillStatus = "fields-not-found";
      console.warn("[TotalCounts SRI] No se pudieron localizar o rellenar los campos del formulario.");
    }
  }

  chrome.runtime.sendMessage({ type: "TTCWEB_GET_SRI_CREDENTIALS" }, response => {
    if (chrome.runtime.lastError || !response?.ok) {
      document.documentElement.dataset.ttcSriFillStatus = "credentials-unavailable";
      return;
    }
    credentials = { ruc: String(response.ruc || ""), clave: String(response.clave || "") };
    attemptFill();
  });
})();
