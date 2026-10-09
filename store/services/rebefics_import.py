"""Importación conservadora de anexos APS/REBEFICS XML anteriores."""
from datetime import datetime
from decimal import Decimal, InvalidOperation
import json
import xml.etree.ElementTree as ET


MAX_APS_XML_BYTES = 20 * 1024 * 1024


def _tag(element):
    return element.tag.rsplit("}", 1)[-1]


def _text(parent, name, default=""):
    if parent is None:
        return default
    for child in list(parent):
        if _tag(child) == name:
            value = (child.text or "").strip()
            return value if value else default
    return default


def _yes(value):
    return str(value or "").strip().upper() in {"SI", "SÍ", "YES", "1", "TRUE"}


def _decimal(value):
    try:
        result = Decimal(str(value or "0").replace(",", "."))
        return result if result.is_finite() and Decimal("0") <= result <= Decimal("100") else Decimal("0")
    except (InvalidOperation, ValueError):
        return Decimal("0")


def _date(value):
    value = str(value or "").strip()
    if not value or value.upper() == "NA":
        return ""
    for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt).date().isoformat()
        except ValueError:
            continue
    return ""


def parse_aps_xml(content, expected_ruc):
    """Parsea APS y devuelve filas consolidadas por identificación más advertencias."""
    if not content:
        raise ValueError("El archivo XML está vacío.")
    if len(content) > MAX_APS_XML_BYTES:
        raise ValueError("El XML supera el límite de 20 MB.")
    try:
        root = ET.fromstring(content)
    except ET.ParseError as exc:
        raise ValueError(f"El archivo no contiene XML válido: {exc}") from exc
    if _tag(root) != "aps":
        raise ValueError("El XML no tiene la estructura APS esperada.")

    informante = _text(root, "IdInformante")
    if not informante or informante != str(expected_ruc).strip():
        raise ValueError(
            f"El RUC del informante ({informante or 'no indicado'}) no coincide "
            f"con el cliente seleccionado ({expected_ruc})."
        )

    anio = _text(root, "Anio")
    agrupados = {}
    advertencias = []
    accionistas_node = next((e for e in list(root) if _tag(e) == "accionistas"), None)
    beneficiarios_node = next((e for e in list(root) if _tag(e) == "beneficiarios"), None)

    for nodo in list(accionistas_node or []):
        if _tag(nodo) != "accionista":
            continue
        ident = _text(nodo, "numeroIdentificacion")
        if not ident or ident.upper() == "NA":
            advertencias.append("Se omitió un accionista sin identificación.")
            continue
        fila = agrupados.setdefault(ident, {
            "identificacion": ident, "origenes": [], "roles_xml": [],
            "porcentajes": [], "beneficiario": False, "raw_accionistas": [],
            "raw_beneficiario": {},
        })
        fila["origenes"].append("accionista")
        fila["roles_xml"].append(_text(nodo, "tipoRelacionadoSociedad", "NA"))
        fila["porcentajes"].append(_decimal(_text(
            next((e for e in list(nodo) if _tag(e) == "infoParticipacionAccionaria"), None),
            "porcentajeParticipacion", "0"
        )))
        fila["beneficiario"] = fila["beneficiario"] or _yes(_text(nodo, "esBeneficiarioFinal"))
        fila["raw_accionistas"].append({
            "tipoRelacionadoSociedad": _text(next((e for e in list(nodo) if _tag(e) == "infoParticipacionAccionaria"), None), "tipoRelacionadoSociedad", "NA"),
            "porcentajeParticipacion": _text(next((e for e in list(nodo) if _tag(e) == "infoParticipacionAccionaria"), None), "porcentajeParticipacion", "0"),
            "parteRelacionadaInformante": _text(next((e for e in list(nodo) if _tag(e) == "infoParticipacionAccionaria"), None), "parteRelacionadaInformante", "NA"),
            "esBeneficiarioFinal": _text(nodo, "esBeneficiarioFinal", "NO"),
        })
        # Los datos de identificación/nombre del primer nodo se usan como base.
        if "tipoSujeto" not in fila:
            fila.update({
                "tipoSujeto": _text(nodo, "tipoSujeto", "01"),
                "tipoIdentificacion": _text(nodo, "tipoIdentificacion", "C"),
                "primerNombre": _text(nodo, "primerNombre"),
                "segundoNombre": _text(nodo, "segundoNombre"),
                "primerApellido": _text(nodo, "primerApellido"),
                "segundoApellido": _text(nodo, "segundoApellido"),
                "nombresRazonSocial": _text(nodo, "nombresRazonSocial"),
                "tipoRegimenFiscal": _text(nodo, "tipoRegimenFiscal"),
                "paisResidenciaFiscal": _text(next((e for e in list(nodo) if _tag(e) == "ubicacionResidenciaFiscal"), None), "paisResidenciaFiscal"),
                "tipoSociedadExt": _text(nodo, "tipoSociedadExt"),
                "figuraJuridicaExt": _text(nodo, "figuraJuridicaExt"),
                "figuraJuridicaOtroExt": _text(nodo, "figuraJuridicaOtroExt"),
                "esSociedadPublicaExt": _text(nodo, "esSociedadPublicaExt"),
                "Menor10porc": _text(nodo, "Menor10porc"),
                "porcentajeAccionarioNoBolsaExt": _text(nodo, "porcentajeAccionarioNoBolsaExt"),
                "porcentajeAccionarioBolsaExt": _text(nodo, "porcentajeAccionarioBolsaExt"),
            })

    for nodo in list(beneficiarios_node or []):
        if _tag(nodo) != "beneficiario":
            continue
        ident = _text(nodo, "numeroIdentificacion")
        if not ident or ident.upper() == "NA":
            advertencias.append("Se omitió un beneficiario sin identificación.")
            continue
        fila = agrupados.setdefault(ident, {
            "identificacion": ident, "origenes": [], "roles_xml": [],
            "porcentajes": [], "beneficiario": False, "raw_accionistas": [],
            "raw_beneficiario": {},
        })
        fila["origenes"].append("beneficiario")
        fila["beneficiario"] = True
        fila["porcentajes"].append(_decimal(_text(nodo, "porcentajePropiedad", "0")))
        fila["raw_beneficiario"] = {
            name: _text(nodo, name, "NA")
            for name in (
                "fechaNacimiento", "porPropiedad", "porcentajePropiedad",
                "porOtrosMotivos", "porOtrosRelacionados", "porAdministracion",
                "nacionalidadUno", "nacionalidadDos", "nacionalidadTres",
                "residenciaFiscal", "jurisdiccion", "provincia", "ciudad",
                "canton", "parroquia", "calle", "numero", "interseccion",
                "codigoPostal", "referencia",
            )
        }
        # Beneficiario puede traer datos más completos que el nodo accionista.
        for field in ("primerNombre", "segundoNombre", "primerApellido", "segundoApellido"):
            value = _text(nodo, field)
            if value:
                fila[field] = value
        for field in ("fechaNacimiento", "calle", "numero", "interseccion", "codigoPostal", "referencia", "ciudad"):
            value = _text(nodo, field)
            if value and value.upper() != "NA":
                fila["beneficiario_" + field] = value
        if not fila.get("tipoIdentificacion"):
            fila["tipoIdentificacion"] = _text(nodo, "tipoIdentificacion", "C")

    rows = []
    for ident, item in agrupados.items():
        nombre_social = item.get("nombresRazonSocial", "")
        if nombre_social.upper() == "NA":
            nombre_social = ""
        if not any((item.get("primerNombre"), item.get("primerApellido"), nombre_social)):
            advertencias.append(f"{ident}: no se encontró nombre ni razón social.")
        tipo_sujeto_xml = item.get("tipoSujeto", "01")
        tipo_ident_xml = item.get("tipoIdentificacion", "C")
        tipo_sujeto = {"01": "PN", "02": "PJ", "03": "EJ"}.get(tipo_sujeto_xml, "PN")
        tipo_ident = {"C": "CEDULA", "R": "RUC", "P": "PASAPORTE", "E": "EXTERIOR"}.get(tipo_ident_xml, "OTRO")
        fecha = _date(item.get("beneficiario_fechaNacimiento", ""))
        # Si el mismo sujeto figura varias veces, no se suman porcentajes repetidos.
        porcentaje = max(item["porcentajes"], default=Decimal("0"))
        raw = {
            "importado_de": "APS",
            "anio_anexo": anio,
            "identificacionInformantePadre": informante,
            "roles_xml": sorted(set(item["roles_xml"])),
            "origenes": sorted(set(item["origenes"])),
            "participaciones_xml": item["raw_accionistas"],
            "datos_beneficiario_xml": item["raw_beneficiario"],
        }
        direccion = item.get("beneficiario_calle", "")
        interseccion = item.get("beneficiario_interseccion", "")
        observaciones = "Importado del anexo APS " + (anio or "sin año") + ". Datos originales: " + json.dumps(raw, ensure_ascii=False)
        rows.append({
            "identificacion": ident,
            "tipo_sujeto": tipo_sujeto,
            "tipo_identificacion": tipo_ident,
            "primer_nombre": item.get("primerNombre", ""),
            "segundo_nombre": item.get("segundoNombre", ""),
            "primer_apellido": item.get("primerApellido", ""),
            "segundo_apellido": item.get("segundoApellido", ""),
            "razon_social": nombre_social,
            "fecha_nacimiento": fecha,
            "nacionalidad": item.get("beneficiario_nacionalidadUno", ""),
            "pais_residencia_fiscal": item.get("beneficiario_residenciaFiscal") or item.get("paisResidenciaFiscal", ""),
            "tipo_regimen_fiscal": item.get("tipoRegimenFiscal", ""),
            "sujeto_extranjero_tipo": item.get("tipoSociedadExt", ""),
            "figura_juridica": item.get("figuraJuridicaExt", ""),
            "otra_figura_juridica": item.get("figuraJuridicaOtroExt", ""),
            "es_sujeto_extranjero": item.get("esSociedadPublicaExt", "").upper() == "SI",
            "ultimo_nivel_cadena": False,
            "tipo_relacion_sujeto": "ACCIONISTA" if "accionista" in item["origenes"] else "SOCIO",
            "porcentaje_participacion": str(porcentaje),
            "porcentaje_participacion_efectiva": str(porcentaje),
            "es_beneficiario_final": item["beneficiario"],
            "beneficiario_por_propiedad": _yes(item.get("beneficiario_porPropiedad", "")),
            "beneficiario_por_control": False,
            "beneficiario_por_administracion": False,
            "estado_jurisdiccion": item.get("beneficiario_provincia", ""),
            "ciudad": item.get("beneficiario_ciudad", ""),
            "calle": direccion,
            "interseccion": interseccion,
            "numero_domicilio": item.get("beneficiario_numero", ""),
            "codigo_postal": item.get("beneficiario_codigoPostal", ""),
            "referencia_direccion": item.get("beneficiario_referencia", ""),
            "observaciones": observaciones,
            "roles_xml": ", ".join(sorted(set(item["roles_xml"]))) or "—",
            "origen": "Accionista y beneficiario" if len(set(item["origenes"])) > 1 else ("Beneficiario" if item["origenes"][0] == "beneficiario" else "Accionista"),
            "anio_anexo": anio,
        })
    rows.sort(key=lambda row: (row["primer_apellido"], row["primer_nombre"], row["razon_social"], row["identificacion"]))
    return {"ruc": informante, "anio": anio, "rows": rows, "advertencias": advertencias}
