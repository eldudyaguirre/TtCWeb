# Extensión Chrome: TotalCounts - Ingreso SRI

Esta extensión abre el portal oficial del SRI desde el menú **Contraseñas → Acciones → Ingreso SRI** y rellena el RUC y la clave del cliente seleccionado. No pulsa **Ingresar**.

## Instalar en la laptop (una sola vez)

1. Descarga la carpeta `chrome-extension-sri` desde el repositorio de TtCWeb o copia sus archivos a una carpeta local de la laptop.
2. Abre `chrome://extensions` en Google Chrome.
3. Activa **Modo de desarrollador**.
4. Pulsa **Cargar descomprimida** y selecciona la carpeta `chrome-extension-sri`.
5. Deja la extensión habilitada y abre/recarga TtCWeb.

## Privacidad

- La extensión declara acceso únicamente a `https://totalcounts.com.ec/*` y `https://srienlinea.sri.gob.ec/*`.
- No guarda las claves en almacenamiento persistente ni las envía a un servicio externo.
- La clave se transmite desde la página autenticada de TotalCounts a la extensión y al formulario del SRI para rellenarlo.
- No inicia sesión ni pulsa botones del formulario.

## Nota

Esta es una extensión para cargar localmente en Chrome, no publicada en Chrome Web Store. Los selectores de campos del SRI pueden requerir ajustes si el portal cambia su formulario.
