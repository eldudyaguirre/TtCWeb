"""
Agente local para abrir el SRI en Chrome y autenticar el cliente seleccionado.
Instalar en la computadora donde se quiere ver Chrome:
    poetry run playwright install chrome
    python scripts/ingreso_sri_local.py
El agente solo escucha en localhost y acepta solicitudes desde totalcounts.com.ec.
"""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import logging
import threading
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright

HOST = "127.0.0.1"
PORT = 8765
ALLOWED_ORIGIN = "https://totalcounts.com.ec"
SRI_URL = "https://srienlinea.sri.gob.ec/sri-en-linea/contribuyente/perfil"
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
# Mantener Playwright y los navegadores vivos mientras el agente siga ejecutándose.
_BROWSER_SESSIONS = []


def open_sri(ruc: str, clave: str) -> None:
    playwright = sync_playwright().start()
    try:
        browser = playwright.chromium.launch(channel="chrome", headless=False)
    except Exception:
        playwright.stop()
        raise
    _BROWSER_SESSIONS.append((playwright, browser))
    page = browser.new_page()
    page.goto(SRI_URL, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(2500)

    user = None
    for selector in (
        'input[name="usuario"]', 'input[name="ruc"]',
        'input[id*="usuario"]', 'input[id*="ruc"]',
        'input[placeholder*="RUC"]', 'input[type="text"]',
    ):
        loc = page.locator(selector)
        for i in range(loc.count()):
            item = loc.nth(i)
            if item.is_visible():
                user = item
                break
        if user:
            break

    password = None
    for selector in (
        'input[type="password"]', 'input[name="clave"]',
        'input[name="password"]', 'input[id*="clave"]',
    ):
        loc = page.locator(selector)
        for i in range(loc.count()):
            item = loc.nth(i)
            if item.is_visible():
                password = item
                break
        if password:
            break

    if not user or not password:
        raise RuntimeError("No se encontró el formulario de acceso del SRI.")

    user.fill(ruc)
    password.fill(clave)

    submit = None
    for selector in (
        'button:has-text("Ingresar")',
        'button:has-text("Iniciar sesión")',
        'button:has-text("Iniciar Sesión")',
        'input[type="submit"]',
        'button[type="submit"]',
    ):
        loc = page.locator(selector)
        for i in range(loc.count()):
            item = loc.nth(i)
            if item.is_visible():
                submit = item
                break
        if submit:
            break

    if not submit:
        raise RuntimeError("No se encontró el botón de ingreso del SRI.")

    submit.click(timeout=15000)
    # Mantener Chrome abierto para que el usuario continúe trabajando.
    logging.info("Se envió el formulario de acceso SRI para RUC %s.", ruc)


class Handler(BaseHTTPRequestHandler):
    def _headers(self, status=200):
        self.send_response(status)
        self.send_header("Access-Control-Allow-Origin", ALLOWED_ORIGIN)
        self.send_header("Vary", "Origin")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()

    def do_OPTIONS(self):
        if self.headers.get("Origin") != ALLOWED_ORIGIN:
            self._headers(403)
            return
        self._headers(204)

    def do_POST(self):
        if self.headers.get("Origin") != ALLOWED_ORIGIN:
            self._headers(403)
            self.wfile.write(b'{"ok":false,"error":"Origen no autorizado"}')
            return
        if urlparse(self.path).path != "/ingreso-sri":
            self._headers(404)
            self.wfile.write(b'{"ok":false,"error":"Ruta no encontrada"}')
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length < 2 or length > 8192:
                raise ValueError("Solicitud inválida.")
            data = json.loads(self.rfile.read(length))
            ruc = str(data.get("ruc", "")).strip()
            clave = str(data.get("clave", "")).strip()
            if len(ruc) != 13 or not ruc.isdigit() or not clave:
                raise ValueError("RUC o clave no válidos.")
            threading.Thread(target=open_sri, args=(ruc, clave), daemon=True).start()
            self._headers(202)
            self.wfile.write(b'{"ok":true,"message":"Chrome solicitado"}')
        except Exception as exc:
            self._headers(400)
            self.wfile.write(json.dumps({"ok": False, "error": str(exc)}).encode("utf-8"))

    def log_message(self, fmt, *args):
        logging.info("localhost %s", fmt % args)


if __name__ == "__main__":
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    logging.info("Agente SRI escuchando solo en %s:%s", HOST, PORT)
    server.serve_forever()
