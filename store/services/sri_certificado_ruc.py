from __future__ import annotations

import asyncio
import hashlib
import logging
from pathlib import Path

from django.conf import settings

from playwright.async_api import (
    async_playwright,
    TimeoutError as PlaywrightTimeoutError,
)

from ..models import Cliente
from ..models.archivo import Archivo
from .archivos.storage import data_root


logger = logging.getLogger(__name__)


SRI_LOGIN_URL = (
    "https://srienlinea.sri.gob.ec/"
    "sri-en-linea/contribuyente/perfil"
)

SRI_CERTIFICADO_URL = (
    "https://srienlinea.sri.gob.ec/"
    "sri-catastro-tributario-web-internet/"
    "pages/certificado/opciones-certificado.jsf"
    "?&contextoMPT="
    "https://srienlinea.sri.gob.ec/tuportal-internet"
    "&pathMPT=RUC"
    "&actualMPT=Certificados%20"
    "&linkMPT=%2Fsri-catastro-tributario-web-internet%2F"
    "pages%2Fcertificado%2Fopciones-certificado.jsf%3F"
    "&esFavorito=S"
)

TIMEOUT = 60_000


def _ruta_certificado(ruc: str) -> Path:
    return (
        data_root()
        / ruc
        / "documentos"
        / "ruc"
        / "certificado_ruc.pdf"
    )


def _registrar_archivo(cliente, contenido: bytes) -> None:
    relative_path = (
        f"{cliente.ruccedcli}/documentos/ruc/"
        "certificado_ruc.pdf"
    )

    Archivo.objects.update_or_create(
        cliente=cliente,
        ruta_relativa=relative_path,
        defaults={
            "nombre_fisico": "certificado_ruc.pdf",
            "nombre_original": "certificado_ruc.pdf",
            "extension": "pdf",
            "mime_type": "application/pdf",
            "tipo": "certificado_ruc",
            "tamano": len(contenido),
            "sha256": hashlib.sha256(contenido).hexdigest(),
            "activo": True,
        },
    )


async def _login(page, ruc: str, clave: str) -> bool:
    """
    IMPORTANTE:
    Para cada RUC se realiza UN SOLO intento de autenticación.
    Nunca se vuelve a escribir la clave ni se vuelve a presionar
    Ingresar si el login no termina correctamente.
    """
    await page.goto(
        SRI_LOGIN_URL,
        wait_until="domcontentloaded",
        timeout=TIMEOUT,
    )

    await page.wait_for_timeout(5_000)

    campo_ruc = None
    for selector in (
        'input[name="usuario"]',
        'input[name="ruc"]',
        'input[id*="usuario"]',
        'input[id*="ruc"]',
        'input[placeholder*="RUC"]',
        'input[placeholder*="Usuario"]',
        'input[type="text"]',
    ):
        try:
            locator = page.locator(selector)
            for i in range(await locator.count()):
                elemento = locator.nth(i)
                if await elemento.is_visible():
                    campo_ruc = elemento
                    break
            if campo_ruc:
                break
        except Exception:
            continue

    campo_clave = None
    for selector in (
        'input[type="password"]',
        'input[name="clave"]',
        'input[name="password"]',
        'input[id*="clave"]',
        'input[id*="password"]',
    ):
        try:
            locator = page.locator(selector)
            for i in range(await locator.count()):
                elemento = locator.nth(i)
                if await elemento.is_visible():
                    campo_clave = elemento
                    break
            if campo_clave:
                break
        except Exception:
            continue

    if not campo_ruc or not campo_clave:
        logger.error(
            "SRI | No se encontró formulario de login | RUC=%s | URL=%s",
            ruc,
            page.url,
        )
        return False

    await campo_ruc.fill(ruc)
    await campo_clave.fill(clave)

    boton = None
    for selector in (
        'button:has-text("Ingresar")',
        'button:has-text("INICIAR SESIÓN")',
        'button:has-text("Iniciar sesión")',
        'button:has-text("Iniciar Sesión")',
        'input[type="submit"]',
        'button[type="submit"]',
    ):
        try:
            locator = page.locator(selector)
            for i in range(await locator.count()):
                elemento = locator.nth(i)
                if await elemento.is_visible():
                    boton = elemento
                    break
            if boton:
                break
        except Exception:
            continue

    if not boton:
        logger.error(
            "SRI | No se encontró botón Ingresar | RUC=%s",
            ruc,
        )
        return False

    logger.info(
        "SRI | ÚNICO intento de login | RUC=%s",
        ruc,
    )

    try:
        await boton.click(timeout=15_000)
    except Exception:
        await boton.click(force=True, timeout=15_000)

    # Esperar hasta 30 segundos, pero SIN volver a intentar.
    for _ in range(15):
        await page.wait_for_timeout(2_000)

        if "/contribuyente/perfil" in page.url:
            logger.info(
                "SRI | Login exitoso | RUC=%s",
                ruc,
            )
            return True

        if (
            "srienlinea.sri.gob.ec" in page.url
            and "/auth/realms/" not in page.url
            and "/login-actions/" not in page.url
        ):
            logger.info(
                "SRI | Login exitoso | RUC=%s | URL=%s",
                ruc,
                page.url,
            )
            return True

    logger.error(
        "SRI | Login no completado | RUC=%s | URL=%s",
        ruc,
        page.url,
    )
    return False


async def _descargar_pdf(page, ruc: str) -> bytes | None:
    await page.goto(
        SRI_CERTIFICADO_URL,
        wait_until="domcontentloaded",
        timeout=TIMEOUT,
    )

    await page.wait_for_timeout(7_000)

    try:
        await page.wait_for_selector(
            'img[src*="/catastro/RUC.svg"]',
            state="visible",
            timeout=30_000,
        )
    except PlaywrightTimeoutError:
        logger.error(
            "SRI | No apareció RUC.svg | RUC=%s | URL=%s",
            ruc,
            page.url,
        )
        return None

    boton = page.locator(
        'a:has(img[src*="/catastro/RUC.svg"])'
    ).first

    if await boton.count() == 0:
        logger.error(
            "SRI | No se encontró botón RUC | RUC=%s",
            ruc,
        )
        return None

    # La respuesta JSF puede navegar y hacer que response.body()
    # deje de estar disponible. La descarga del navegador es el
    # método principal porque ya fue probado correctamente.
    try:
        async with page.expect_download(
            timeout=30_000
        ) as download_info:
            try:
                await boton.click(timeout=15_000)
            except Exception:
                await boton.click(
                    force=True,
                    timeout=15_000,
                )

        download = await download_info.value
        path = await download.path()

        if not path:
            return None

        contenido = Path(path).read_bytes()

        if contenido.startswith(b"%PDF"):
            logger.info(
                "SRI | PDF descargado | RUC=%s | bytes=%s",
                ruc,
                len(contenido),
            )
            return contenido

    except Exception as exc:
        logger.exception(
            "SRI | Error descargando certificado | RUC=%s | %s",
            ruc,
            exc,
        )

    return None


async def obtener_certificado_ruc(ruc: str) -> dict:
    """
    Ejecuta todo el proceso para UN solo RUC.

    Se crea un Chromium limpio para cada ejecución y se cierra
    completamente al terminar.
    """
    ruc = "".join(
        char for char in str(ruc) if char.isdigit()
    )

    if len(ruc) != 13:
        return {
            "ok": False,
            "mensaje": "RUC inválido.",
        }

    cliente = await asyncio.to_thread(
        lambda: Cliente.objects.filter(
            ruccedcli=ruc,
            activo=True,
        ).first()
    )

    if cliente is None:
        return {
            "ok": False,
            "mensaje": "El cliente no existe o está inactivo.",
        }

    clave = str(cliente.clavesri or "").strip()

    if not clave:
        return {
            "ok": False,
            "mensaje": "El cliente no tiene clave SRI registrada.",
        }

    logger.info(
        "SRI | PROCESANDO RUC=%s | CLIENTE=%s",
        ruc,
        cliente.nomclient,
    )

    async with async_playwright() as playwright:
        browser = None
        context = None

        try:
            logger.info(
                "SRI | Abriendo Chromium limpio | RUC=%s",
                ruc,
            )

            browser = await playwright.chromium.launch(
                headless=False,
            )

            context = await browser.new_context(
                accept_downloads=True,
                viewport={
                    "width": 1366,
                    "height": 768,
                },
            )

            page = await context.new_page()
            page.set_default_timeout(TIMEOUT)

            if not await _login(
                page,
                ruc,
                clave,
            ):
                return {
                    "ok": False,
                    "mensaje": (
                        "El SRI no completó el inicio de sesión. "
                        "No se realizó un segundo intento."
                    ),
                }

            contenido = await _descargar_pdf(
                page,
                ruc,
            )

            if not contenido:
                return {
                    "ok": False,
                    "mensaje": (
                        "El SRI no entregó el certificado PDF."
                    ),
                }

            destino = _ruta_certificado(ruc)
            destino.parent.mkdir(
                parents=True,
                exist_ok=True,
            )
            destino.write_bytes(contenido)

            await asyncio.to_thread(
                _registrar_archivo,
                cliente,
                contenido,
            )

            logger.info(
                "SRI | CERTIFICADO GUARDADO | RUC=%s | %s",
                ruc,
                destino,
            )

            return {
                "ok": True,
                "mensaje": "Certificado de RUC obtenido correctamente.",
                "ruta": str(destino),
            }

        except Exception as exc:
            logger.exception(
                "SRI | Error procesando RUC=%s | %s",
                ruc,
                exc,
            )
            return {
                "ok": False,
                "mensaje": str(exc),
            }

        finally:
            if context:
                try:
                    await context.close()
                except Exception:
                    pass

            if browser:
                try:
                    await browser.close()
                except Exception:
                    pass

            logger.info(
                "SRI | Chromium cerrado | RUC=%s",
                ruc,
            )


def obtener_certificado_ruc_sync(ruc: str) -> dict:
    return asyncio.run(
        obtener_certificado_ruc(ruc)
    )
