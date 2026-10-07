from io import BytesIO

from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from .admin_views import admin_required
from .models import Cliente
from .views import _cliente_db


@admin_required
def admin_trabajadores_pdf(request, ruc):
    """Genera el PDF del listado de trabajadores activos del cliente seleccionado."""
    cliente = get_object_or_404(Cliente, pk=ruc)

    sql = """
        SELECT
            ROW_NUMBER() OVER (ORDER BY nombres, cedula) AS numero,
            TRIM(cedula::text) AS cedula,
            TRIM(nombres::text) AS trabajador,
            TRIM(COALESCE(cargo::text, '')) AS cargo,
            TRIM(COALESCE(tipojornada::text, '')) AS tipojornada,
            fecentrada,
            sueldo
        FROM trabajadores
        WHERE activo = TRUE
          AND COALESCE(TRIM(comisionsec::text), '') <> 'SERVICIO DOMESTICO'
        ORDER BY nombres, cedula
    """

    try:
        with _cliente_db(cliente).cursor() as cursor:
            cursor.execute(sql)
            filas = cursor.fetchall()
    except Exception as exc:
        return HttpResponse(
            f'Error consultando trabajadores: {type(exc).__name__}: {exc}',
            status=500,
            content_type='text/plain; charset=utf-8',
        )

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        leftMargin=25,
        rightMargin=25,
        topMargin=25,
        bottomMargin=25,
    )

    styles = getSampleStyleSheet()
    titulo = ParagraphStyle(
        'AdminTrabajadoresPDFTitulo',
        parent=styles['Title'],
        fontName='Helvetica-Bold',
        fontSize=14,
        leading=16,
        alignment=TA_CENTER,
        spaceAfter=4,
    )
    cabecera = ParagraphStyle(
        'AdminTrabajadoresPDFCabecera',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=9,
        leading=11,
        alignment=TA_CENTER,
    )
    tabla = ParagraphStyle(
        'AdminTrabajadoresPDFTabla',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=7,
        leading=9,
    )
    encabezado = ParagraphStyle(
        'AdminTrabajadoresPDFEncabezado',
        parent=tabla,
        fontName='Helvetica-Bold',
        textColor=colors.white,
        alignment=TA_CENTER,
    )

    elements = [
        Paragraph('LISTADO DE TRABAJADORES', titulo),
        Paragraph('TRABAJADORES ACTIVOS', cabecera),
        Paragraph(
            f'{cliente.nomclient} | RUC. {cliente.ruccedcli}',
            cabecera,
        ),
        Spacer(1, 12),
    ]

    encabezados = [
        'N°', 'CÉDULA', 'TRABAJADOR', 'CARGO',
        'TIPO JORNADA', 'FECHA ENTRADA', 'SUELDO',
    ]
    data = [[Paragraph(label, encabezado) for label in encabezados]]

    for row in filas:
        data.append([
            Paragraph(str(row[0]), tabla),
            Paragraph(str(row[1] or ''), tabla),
            Paragraph(str(row[2] or ''), tabla),
            Paragraph(str(row[3] or ''), tabla),
            Paragraph(str(row[4] or ''), tabla),
            Paragraph(row[5].strftime('%d/%m/%Y') if row[5] else '', tabla),
            Paragraph(f'{float(row[6] or 0):.2f}', tabla),
        ])

    table = Table(
        data,
        repeatRows=1,
        colWidths=[35, 85, 180, 115, 100, 90, 75],
    )
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#21333e')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('GRID', (0, 0), (-1, -1), .3, colors.HexColor('#d8e0e3')),
        ('ALIGN', (0, 0), (1, -1), 'CENTER'),
        ('ALIGN', (2, 1), (4, -1), 'LEFT'),
        ('ALIGN', (5, 1), (6, -1), 'RIGHT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#eef5f5')),
    ]))

    elements.append(table)
    elements.append(Spacer(1, 8))
    elements.append(
        Paragraph(
            f'Total de trabajadores activos: {len(filas)}',
            tabla,
        )
    )

    doc.build(elements)

    response = HttpResponse(
        buffer.getvalue(),
        content_type='application/pdf',
    )
    response['Content-Disposition'] = (
        f'attachment; filename="listado_trabajadores_{cliente.ruccedcli}.pdf"'
    )
    return response
