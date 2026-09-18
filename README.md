# TotalCounts Web

Portal web de TotalCounts.

## Objetivo

La plataforma tendrá dos áreas principales:

- **Portal de clientes:** acceso autenticado para consultar y descargar reportes de ventas, gastos, retenciones y roles de pago.
- **Administración interna:** gestión de clientes, empresas, usuarios, bases de datos y procesos de alimentación de información.

A futuro se incorporará un proceso automatizado para consultar información del SRI, procesar los comprobantes y alimentar PostgreSQL.

## Desarrollo

Proyecto Django ejecutado con Python 3.12 y Poetry.

## Datos sensibles

Las credenciales y variables de entorno se mantienen fuera del repositorio mediante el archivo `.env`.
