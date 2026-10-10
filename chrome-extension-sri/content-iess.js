(() => {
  if (window.__ttcIESSListenerReady) return;
  window.__ttcIESSListenerReady = true;

  const visible = el => el instanceof HTMLInputElement &&
    el.getClientRects().length > 0 && !el.disabled && el.type !== "hidden";

  function setValue(el, value) {
    const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")?.set;
    if (setter) setter.call(el, value); else el.value = value;
    el.dispatchEvent(new Event("input", { bubbles: true }));
    el.dispatchEvent(new Event("change", { bubbles: true }));
  }

  function fill(credentials) {
    const inputs = Array.from(document.querySelectorAll("input")).filter(visible);
    const password = inputs.find(el => el.type === "password");
    if (!password) return false;
    const user = inputs.find(el => el !== password &&
      /cedula|c[eé]dula|usuario|identificaci/i.test(
        [el.name, el.id, el.placeholder, el.getAttribute("aria-label"), el.parentElement?.innerText]
          .filter(Boolean).join(" ")
      )) || inputs.find(el => el !== password &&
        ["text", "tel", "number"].includes((el.type || "").toLowerCase()));
    if (!user) return false;

    setValue(user, credentials.usuario);
    setValue(password, credentials.clave);
    if (user.value !== credentials.usuario || password.value !== credentials.clave) return false;

    document.documentElement.dataset.ttcIessFillStatus = "filled";
    setTimeout(() => {
      if (!visible(user) || !visible(password) ||
          user.value !== credentials.usuario || password.value !== credentials.clave) {
        document.documentElement.dataset.ttcIessFillStatus = "verification-failed";
        return;
      }
      const submit = Array.from(document.querySelectorAll("button,input[type='submit'],input[type='button']"))
        .filter(el => el.getClientRects().length && !el.disabled)
        .find(el => /ingresar|aceptar|entrar/i.test(
          (el.innerText || el.value || el.getAttribute("aria-label") || "").trim()
        ));
      if (submit) {
        document.documentElement.dataset.ttcIessFillStatus = "submitting";
        submit.click();
      } else if (user.form || password.form) {
        document.documentElement.dataset.ttcIessFillStatus = "submitting";
        (user.form || password.form).requestSubmit();
      } else {
        document.documentElement.dataset.ttcIessFillStatus = "submit-not-found";
      }
    }, 400);
    return true;
  }

  chrome.runtime.onMessage.addListener(message => {
    if (message?.type !== "TTCWEB_FILL_IESS_CREDENTIALS") return;
    const credentials = { usuario: String(message.usuario || ""), clave: String(message.clave || "") };
    document.documentElement.dataset.ttcIessFillStatus = "credentials-received";
    let attempts = 0;
    const timer = setInterval(() => {
      if (fill(credentials)) clearInterval(timer);
      else if (++attempts >= 45) {
        clearInterval(timer);
        document.documentElement.dataset.ttcIessFillStatus = "fields-not-found";
      }
    }, 500);
  });
})();
