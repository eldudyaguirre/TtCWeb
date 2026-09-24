        'TOTAL\nLÍQUIDO\nA\nRECIBIR', 'FIRMA',
    ]

    # Dos filas de cabecera, como en el documento de referencia.
    top = ['N°', 'NOMBRES', 'CARGO', 'SALARIO\nMÍNIMO\nSECTORIAL',
           'N°\nDÍAS\nTRAB.', 'SALARIO\nA\nRECIBIR',
           'I N G R E S O S', '', '', '', '', '', '',
           'E G R E S O S', '', '', '', 'FIRMA']
    second = ['', '', '', '', '', '', 'FONDO\nDE\nRESERVA',
              'HORAS\nEXTRAS', 'DÉCIMO\nXIV', 'DÉCIMO\nXIII',
              'COMISIONES\nY/O\nBONOS', 'TOTAL\nINGRESOS',
              'INGRESOS\nCON\nAPORTE\nIESS', 'APORTE\nIESS\n9.45%',
              'DÍAS NO\nLABORADOS\nPRÉSTAMOS\nANTICIPOS',
              'ACUMULACIÓN\nFONDOS DE\nRESERVA', 'TOTAL\nEGRESOS',
              'TOTAL\nLÍQUIDO\nA\nRECIBIR', 'FIRMA']

    top_cells = [
        Paragraph(x.replace('\n', '<br/>'), encabezado_grupo)
        for x in top[:-1]
    ]
    # FIRMA se renderiza como Paragraph independiente en la primera fila
    # para garantizar que el encabezado sea visible en el PDF.
    top_cells.append(Paragraph('FIRMA', firma_encabezado))
    second_cells = [
        Paragraph(x.replace('\n', '<br/>'), encabezado) if x else ''
        for x in second
    ]
    second_cells[-1] = ''

    data = [top_cells, second_cells]

    def money(value):
        if value is None or value == '':
            return ''
        try:
            return f'{float(value):,.2f}'
        except (TypeError, ValueError):
            return str(value)

    for row in filas:
        # rolgeneral: numero, nombres, cargo, salario, dl, arecibir, fr, he,
        # xiv, xiii, comisiones, bonos, toting, ingconaporte, aporte,
        # dnlprestamos, fracu, totegr, liquido
        valores = [
            str(row[0] or ''),
            str(row[1] or ''),
            str(row[2] or ''),
            money(row[3]),
            str(row[4] if row[4] is not None else ''),
            money(row[5]),
            money(row[6]),
            money(row[7]),
            money(row[8]),
            money(row[9]),
            money((row[10] or 0) + (row[11] or 0)),
            money(row[12]),
            money(row[13]),
            money(row[14]),
            money(row[15]),
            money(row[16]),
            money(row[17]),
            money(row[18]),
            '',
        ]
        data.append([
            Paragraph(valor, dato_centro if i in (0, 4) else dato_derecha if i >= 3 else dato)
            for i, valor in enumerate(valores)
        ])

    col_widths = [16, 78, 45, 40, 27, 40, 36, 32, 32, 32, 40, 36, 40, 36, 47, 39, 36, 40, 100]

    table = Table(
        data,
        colWidths=col_widths,
        repeatRows=2,
        hAlign='LEFT',
    )

    style = [
        ('GRID', (0, 0), (-1, -1), 0.55, colors.black),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('SPAN', (6, 0), (12, 0)),
        ('SPAN', (13, 0), (17, 0)),
        ('SPAN', (0, 0), (0, 1)),
        ('SPAN', (1, 0), (1, 1)),
        ('SPAN', (2, 0), (2, 1)),
        ('SPAN', (3, 0), (3, 1)),
        ('SPAN', (4, 0), (4, 1)),
        ('SPAN', (5, 0), (5, 1)),
        # FIRMA no se combina verticalmente: el texto queda en la celda
        # superior para garantizar que ReportLab lo renderice.
        ('FONTNAME', (18, 0), (18, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (18, 0), (18, 0), 7.5),
        ('TEXTCOLOR', (18, 0), (18, 0), colors.black),
        ('ALIGN', (18, 0), (18, 0), 'CENTER'),