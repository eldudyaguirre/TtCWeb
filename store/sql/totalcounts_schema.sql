--
-- PostgreSQL database dump
--


-- Dumped from database version 16.14
-- Dumped by pg_dump version 16.14

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: siguiente_consecutivo(text); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.siguiente_consecutivo(campo text) RETURNS integer
    LANGUAGE plpgsql
    AS $$
DECLARE
    sql_text TEXT;
    nuevo_valor INTEGER;
BEGIN

    campo := lower(campo);

    IF campo NOT IN (
        'numfactur',
        'numdetfac',
        'numfactem',
        'numncven',
        'numdetncven',
        'numdevnctem',
        'numdetnotent',
        'numnotenttem',
        'numprofor',
        'numdetprofor',
        'numprofortem',
        'numcompra',
        'numdetcom',
        'numcompraod',
        'numdetcomod',
        'numcompranv',
        'numdetcomnv',
        'numnccom',
        'numdetnccom',
        'numretenc',
        'numrettmp',
        'numdockar',
        'numctapro',
        'numctacli',
        'numcuepag',
        'numcuecob',
        'nummovban',
        'nummovcaj',
        'nummovcajchi',
        'numcomingban',
        'numcomegrban',
        'numcomingcaj',
        'numcomegrcaj',
        'numcomingcajchi',
        'numcomegrcajchi',
        'numantcli',
        'numdialisfac'
    ) THEN

        RAISE EXCEPTION
            'El campo "%" no es un consecutivo v?lido.',
            campo;

    END IF;


    sql_text := format(
        'UPDATE parametros
         SET %I = %I + 1
         RETURNING %I',
         campo,
         campo,
         campo
    );


    EXECUTE sql_text
    INTO nuevo_valor;


    RETURN nuevo_valor;

END;
$$;


--
-- Name: siguiente_parametro(character varying); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.siguiente_parametro(campo character varying) RETURNS integer
    LANGUAGE plpgsql
    AS $$
DECLARE
    sql_text TEXT;
    nuevo_valor INTEGER;
BEGIN

    campo := lower(trim(campo));

    IF campo NOT IN (
        'numfactur',
        'numdetfac',
        'numfactem',
        'numretenc',
        'numnc',
        'numcompra',
        'numdetcom',
        'numcompranv',
        'numrettmp',
        'numdockar',
        'numctapro',
        'numctacli',
        'numcuepag',
        'numcuecob',
        'numdevcom',
        'numdevven',
        'numdetcomnv',
        'nummovcaj',
        'nummovban',
        'nummovcajchi',
        'numcomingban',
        'numcomegrban',
        'numcomingcaj',
        'numcomegrcaj',
        'numcomingcajchi',
        'numcomegrcajchi',
        'numantcli',
        'numnotcre',
        'numcopfac',
        'numcopret',
        'numcopnotven',
        'numdialisfac'
    ) THEN

        RAISE EXCEPTION
            'El campo "%" no es un consecutivo v?lido.',
            campo;

    END IF;

    sql_text := format(
        'UPDATE parametros
         SET %I = COALESCE(%I, 0) + 1
         RETURNING %I',
        campo,
        campo,
        campo
    );

    EXECUTE sql_text
    INTO nuevo_valor;

    RETURN nuevo_valor;

END;
$$;


SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: aice; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.aice (
    codprodice character varying(255),
    gramoazucar character varying(255),
    nombre character varying(255),
    factura character varying(255),
    tipoidcliente character varying(255),
    idcliente character varying(255),
    tipoventaice character varying(255),
    ventaice character varying(255),
    device character varying(255),
    cantprodbajaice character varying(255),
    "año" character varying(255),
    mes character varying(255)
);


--
-- Name: anticiclient; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.anticiclient (
    numantcli bigint,
    ruccedcli character varying(13),
    fecantcli timestamp without time zone,
    valantcli double precision,
    refantcli character varying(100),
    estantcli character varying(10),
    debe double precision,
    haber double precision,
    saldo double precision,
    salantici double precision
);


--
-- Name: anulados; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.anulados (
    tipodoc character varying(255),
    establecimiento character varying(255),
    emision character varying(255),
    secini character varying(255),
    secfin character varying(255),
    autorizacion character varying(255),
    mes character varying(255),
    "año" character varying(255)
);


--
-- Name: cajas; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.cajas (
    codcaja character varying(2),
    descaja character varying(50),
    salcaja double precision,
    codcuecon character varying(30)
);


--
-- Name: cajaschicas; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.cajaschicas (
    codcaja character varying(2),
    descaja character varying(50),
    salcaja double precision,
    codcuecon character varying(30)
);


--
-- Name: chegirado; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.chegirado (
    numfactur text,
    ruccedpro character varying(13),
    numcheque text,
    fecgirche timestamp without time zone,
    feccobche timestamp without time zone,
    valor double precision,
    banco character varying(25),
    estado character varying(10),
    girado boolean NOT NULL,
    numcompro bigint,
    nummovban bigint
);


--
-- Name: cheposcli; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.cheposcli (
    numfactur character varying(25),
    ruccedcli character varying(13),
    numcheque character varying(12),
    fecgirche timestamp without time zone,
    feccobche timestamp without time zone,
    valor double precision,
    banco character varying(25),
    estado character varying(10)
);


--
-- Name: clientes; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.clientes (
    ruccedcli character varying(13),
    nomclient character varying(65),
    dirclient character varying(50),
    teldomcli character varying(20),
    teloficli character varying(20),
    telcelcli character varying(20),
    telfaxcli character varying(20),
    fecnacimi timestamp without time zone,
    edaclient bigint,
    rep_legal character varying(100),
    ocuclient character varying(50),
    antperson text,
    limcredit double precision,
    salcuenta double precision,
    salantici double precision,
    salnotcre double precision,
    fecultcom timestamp without time zone,
    fecultpag timestamp without time zone,
    numdiacre bigint,
    codcuecon character varying(30),
    porretfuebie double precision,
    porretivabie double precision,
    porretfueser double precision,
    porretivaser double precision,
    salvencid1 double precision,
    salvencid2 double precision,
    salvencid3 double precision,
    salvencid4 double precision,
    tarifa double precision,
    corelectr character varying(35),
    codcueant character varying(30),
    codcuencr character varying(30),
    diadeclaracion character varying(255),
    semensual character varying(255),
    automatizado boolean NOT NULL
);


--
-- Name: codretencion; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.codretencion (
    cod character varying(255),
    descripcion character varying(255),
    porcentaje character varying(255),
    cuentacontable bigint
);


--
-- Name: comegrbancos; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.comegrbancos (
    numcomegr bigint,
    fecha timestamp without time zone,
    beneficia character varying(80),
    valor double precision,
    concepto character varying(150),
    bancocaja character varying(50),
    cuenta character varying(30),
    cheque character varying(255),
    asientouno bigint,
    asientodos bigint,
    referencia character varying(150),
    elaborado character varying(50),
    contabilizado character varying(50),
    autorizado character varying(50),
    recibido character varying(50)
);


--
-- Name: comegrcaja; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.comegrcaja (
    numcomegr bigint,
    nummovcaj bigint,
    fecha timestamp without time zone,
    beneficia character varying(13),
    valor double precision,
    concepto character varying(150),
    bancocaja character varying(50),
    cuenta character varying(30),
    cheque character varying(10),
    asientouno bigint,
    asientodos bigint,
    referencia character varying(150),
    elaborado character varying(50),
    contabilizado character varying(50),
    autorizado character varying(50),
    recibido character varying(50)
);


--
-- Name: comegrcajachica; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.comegrcajachica (
    numcomegr bigint,
    nummovcaj bigint,
    fecha timestamp without time zone,
    beneficia character varying(13),
    valor double precision,
    concepto character varying(150),
    bancocaja character varying(50),
    cuenta character varying(30),
    cheque character varying(10),
    asientouno bigint,
    asientodos bigint,
    referencia character varying(150),
    elaborado character varying(50),
    contabilizado character varying(50),
    autorizado character varying(50),
    recibido character varying(50)
);


--
-- Name: comingbancos; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.comingbancos (
    numcoming bigint,
    fecha timestamp without time zone,
    beneficia character varying(13),
    valor double precision,
    concepto character varying(150),
    bancocaja character varying(50),
    cuenta character varying(30),
    cheque character varying(10),
    asientouno bigint,
    asientodos bigint,
    referencia character varying(150),
    elaborado character varying(50),
    contabilizado character varying(50),
    autorizado character varying(50),
    recibido character varying(50)
);


--
-- Name: comingcaja; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.comingcaja (
    numcoming bigint,
    nummovcaj bigint,
    fecha timestamp without time zone,
    beneficia character varying(13),
    valor double precision,
    concepto character varying(150),
    bancocaja character varying(50),
    cuenta character varying(30),
    cheque character varying(10),
    asientouno bigint,
    asientodos bigint,
    referencia character varying(150),
    elaborado character varying(50),
    contabilizado character varying(50),
    autorizado character varying(50),
    recibido character varying(50)
);


--
-- Name: comingcajachica; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.comingcajachica (
    numcoming bigint,
    nummovcaj bigint,
    fecha timestamp without time zone,
    beneficia character varying(13),
    valor double precision,
    concepto character varying(150),
    bancocaja character varying(50),
    cuenta character varying(30),
    cheque character varying(10),
    asientouno bigint,
    asientodos bigint,
    referencia character varying(150),
    elaborado character varying(50),
    contabilizado character varying(50),
    autorizado character varying(50),
    recibido character varying(50)
);


--
-- Name: compras; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.compras (
    numcompra bigint,
    feccompra timestamp without time zone,
    ruccedpro character varying(13),
    numfaccom character varying(25),
    subtotcom double precision,
    prcdescom double precision,
    valdescom double precision,
    prcivacom double precision,
    valivacom double precision,
    totcompra double precision,
    forpag character varying(30),
    estcompra character varying(15),
    estproces character varying(10),
    fecvencim timestamp without time zone,
    valpagini double precision,
    valsalcom double precision,
    observaci character varying(100),
    porretfuebie double precision,
    porretivabie double precision,
    porretfueser double precision,
    porretivaser double precision,
    valretfue double precision,
    valretiva double precision,
    valnetpag double precision,
    gencomret boolean NOT NULL,
    numcheque character varying(12),
    numcueban character varying(25),
    totsiniva double precision,
    totconiva double precision,
    tippagini character varying(20),
    fecregcom timestamp without time zone,
    numautori character varying(38),
    feccaduci character varying(7),
    basimpice bigint,
    porice bigint,
    valice bigint,
    tipdocume character varying(3),
    numasiuno bigint,
    numasidos bigint,
    codcaja character varying(2),
    codcajchi character varying(2),
    mes character varying(255),
    "año" character varying(255)
);


--
-- Name: comprasnue; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.comprasnue (
    numcompra character varying(255),
    codsus character varying(255),
    tipid character varying(255),
    ruccedprovee character varying(255),
    tipcom character varying(255),
    fecreg character varying(255),
    numest character varying(255),
    numptoemi character varying(255),
    numsec character varying(255),
    fecemi character varying(255),
    numaut character varying(255),
    baseimpnoobj character varying(255),
    baseimpiva0 character varying(255),
    baseimpiva12 character varying(255),
    baseexenta character varying(255),
    montoice character varying(255),
    montoiva character varying(255),
    retencioniva10 character varying(255),
    retencioniva20 character varying(255),
    retencioniva30 character varying(255),
    retencioniva70 character varying(255),
    retencioniva100 character varying(255),
    totbases character varying(255),
    codret character varying(255),
    baseimpret character varying(255),
    porret character varying(255),
    valret character varying(255),
    numestret character varying(255),
    numptoemiret character varying(255),
    numsecret character varying(255),
    numautret character varying(255),
    fecret character varying(255),
    tipopago character varying(255),
    codtipodoc character varying(255),
    numestmod character varying(255),
    numptoemimod character varying(255),
    numsecmod character varying(255),
    numautmod character varying(255),
    mes character varying(255),
    "año" character varying(255),
    nomprovee character varying(255),
    baseimpiva5 character varying(255),
    baseimpiva8 character varying(255),
    baseimpiva14 character varying(255),
    baseimpiva15 character varying(255),
    montoiva5 character varying(255),
    montoiva8 character varying(255),
    montoiva12 character varying(255),
    montoiva14 character varying(255),
    montoiva15 character varying(255)
);


--
-- Name: cuentacliente; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.cuentacliente (
    nummovcta bigint,
    ruccedcli character varying(13),
    fecmovcta timestamp without time zone,
    tipmovcta character varying(20),
    valmovcta double precision,
    refmovcta character varying(100),
    fecvencim timestamp without time zone,
    numfactur character varying(25),
    debe double precision,
    haber double precision,
    saldo double precision,
    salcuenta double precision,
    tipdocume character varying(3)
);


--
-- Name: cuentaproveedor; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.cuentaproveedor (
    nummovcta bigint,
    ruccedpro character varying(13),
    fecmovcta timestamp without time zone,
    tipmovcta character varying(20),
    valmovcta double precision,
    refmovcta character varying(100),
    fecvencim timestamp without time zone,
    debe double precision,
    haber double precision,
    saldo double precision,
    numfaccom character varying(25),
    salcuenta double precision,
    tipdoccom character varying(3),
    creadopor character varying(255)
);


--
-- Name: cuentasbancos; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.cuentasbancos (
    bancocta character varying(25),
    codcuenta character varying(30),
    titular character varying(50),
    tipcuenta character varying(1),
    fecapertu timestamp without time zone,
    feccorte timestamp without time zone,
    saldocta numeric(19,4),
    ultcheque character varying(10),
    codcuecon character varying(30)
);


--
-- Name: cuentascobrar; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.cuentascobrar (
    numcuecob bigint,
    fecinicio timestamp without time zone,
    fecvencim timestamp without time zone,
    numfactur character varying(25),
    valpagpar double precision,
    estpagcue character varying(10),
    refcuecob character varying(100),
    ruccedcli character varying(13),
    tipdocume character varying(3)
);


--
-- Name: cuentaspagar; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.cuentaspagar (
    numcuepag bigint,
    fecinicio timestamp without time zone,
    fecvencim timestamp without time zone,
    numcompra character varying(25),
    numfaccom character varying(25),
    valpagpar double precision,
    estpagcue character varying(10),
    refcuepag character varying(100),
    ruccedpro character varying(13),
    tipdoccom character varying(3)
);


--
-- Name: detallecompras; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.detallecompras (
    numdetcom character varying(25),
    numcompra bigint,
    coditeinv character varying(30),
    desiteinv character varying(100),
    cantidcom double precision,
    preitecom double precision,
    dscitecom double precision,
    totitecom double precision,
    candevolu double precision
);


--
-- Name: detallefacturas; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.detallefacturas (
    numdetfac bigint,
    numfactur character varying(25),
    coditeinv character varying(30),
    desiteinv character varying(250),
    canfactur double precision,
    preitefac double precision,
    dscitefac double precision,
    totitefac double precision,
    candevolu double precision
);


--
-- Name: detdiagentem; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.detdiagentem (
    fecha character varying(10),
    codcuenta character varying(30),
    detalle character varying(200),
    debe character varying(15),
    haber character varying(15),
    numasient bigint,
    seqasient bigint
);


--
-- Name: detdiariogeneral; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.detdiariogeneral (
    fecha character varying(10),
    codcuenta character varying(30),
    detalle character varying(200),
    debe character varying(15),
    haber character varying(15),
    numasient bigint,
    seqasient bigint
);


--
-- Name: detretenc; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.detretenc (
    numdocume character varying(20),
    ejefiscal bigint,
    basimponi double precision,
    codimpues character varying(15),
    nomimpues character varying(20),
    porretenc double precision,
    valretenc double precision
);


--
-- Name: devolucompra; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.devolucompra (
    numdevcom bigint,
    numfactur character varying(25),
    codsustento character varying(255),
    tipoidentificacion character varying(255),
    ruccedpro character varying(13),
    tipocomprob character varying(255),
    fecdevolu timestamp without time zone,
    numfaccom character varying(255),
    numestfac character varying(255),
    numemifac character varying(255),
    numsecfac character varying(255),
    numautor character varying(255),
    valdevolu double precision,
    valivadev double precision,
    tipdoc character varying(255),
    estnc character varying(255),
    ptoeminc character varying(255),
    secnc character varying(255),
    autnc character varying(255),
    coditeinv character varying(30),
    desiteinv character varying(250),
    canfactur double precision,
    totitefac double precision,
    valdescue double precision,
    candevolu double precision,
    valtotdev double precision,
    impcompro boolean NOT NULL,
    forpagdev character varying(15),
    numnc character varying(255),
    estpagdev character varying(15),
    valpagpar double precision,
    valsaldev double precision,
    fechaaplica character varying(255),
    fechadeclaracion character varying(255)
);


--
-- Name: devoluventas; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.devoluventas (
    numdevven bigint,
    fecdevolu timestamp without time zone,
    ruccedcli character varying(13),
    numfactur character varying(25),
    coditeinv character varying(30),
    desiteinv character varying(250),
    canfactur double precision,
    totitefac double precision,
    valdescue double precision,
    candevolu double precision,
    valdevolu double precision,
    valivadev double precision,
    valtotdev double precision,
    impcompro boolean NOT NULL,
    forpagdev character varying(15),
    estpagdev character varying(15),
    valpagpar double precision,
    valsaldev double precision
);


--
-- Name: facturas; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.facturas (
    numfactur character varying(25),
    numserfac character varying(11),
    ruccedcli character varying(13),
    fecfactur timestamp without time zone,
    subtotfac double precision,
    pordescue double precision,
    valdescue double precision,
    porivafac double precision,
    valivafac double precision,
    totfactur double precision,
    totbieiva double precision,
    totbiesiniva double precision,
    totseriva double precision,
    totsersiniva double precision,
    totconiva double precision,
    totsiniva double precision,
    valpagini double precision,
    valsalfac double precision,
    forpagfac character varying(30),
    estpagfac character varying(15),
    fecvencim timestamp without time zone,
    estprofac character varying(15),
    imprimfac boolean NOT NULL,
    userid character varying(50),
    observ character varying(250),
    codvended character varying(13),
    nomvended character varying(30),
    nomtarcre character varying(50),
    tippagtar character varying(15),
    plapagtar character varying(10),
    numasiuno bigint,
    numasidos bigint,
    numasitre bigint,
    retemitid boolean NOT NULL,
    autorizacion character varying(255)
);


--
-- Name: flujocaja; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.flujocaja (
    nummovcaj bigint,
    fecmovcaj timestamp without time zone,
    tipmovcaj character varying(1),
    numdocume character varying(20),
    valmovcaj double precision,
    refmovcaj character varying(200),
    userid character varying(10),
    codcajgen character varying(2),
    debe double precision,
    haber double precision,
    saldo double precision,
    numasiuno bigint,
    numasidos bigint
);


--
-- Name: flujocajachica; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.flujocajachica (
    nummovcaj bigint,
    fecmovcaj timestamp without time zone,
    tipmovcaj character varying(1),
    numdocume character varying(20),
    valmovcaj double precision,
    refmovcaj character varying(200),
    userid character varying(10),
    codcajchi character varying(2),
    reposicion boolean NOT NULL,
    debe double precision,
    haber double precision,
    saldo double precision,
    numasiuno bigint,
    numasidos bigint,
    numcompra character varying(255),
    tipdocume character varying(255)
);


--
-- Name: gastospersonales; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.gastospersonales (
    numcompra character varying(255),
    rucprovee character varying(255),
    nomprovee character varying(255),
    cantcom character varying(255),
    numfac character varying(255),
    fecfac character varying(255),
    numaut character varying(255),
    tipogasto character varying(255),
    baseimp character varying(255),
    "año" character varying(255)
);


--
-- Name: grupriact; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.grupriact (
    gruprinci character varying(20)
);


--
-- Name: gruprigas; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.gruprigas (
    gruprinci character varying(20)
);


--
-- Name: gruprimer; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.gruprimer (
    gruprinci character varying(20)
);


--
-- Name: grupriser; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.grupriser (
    gruprinci character varying(20)
);


--
-- Name: grusubgruact; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.grusubgruact (
    subgruite character varying(20),
    gruprinci character varying(20)
);


--
-- Name: grusubgrugas; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.grusubgrugas (
    subgruite character varying(20),
    gruprinci character varying(20)
);

--
-- Name: grusubgrumer; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.grusubgrumer (
    subgruite character varying(20),
    gruprinci character varying(20)
);


--
-- Name: grusubgruser; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.grusubgruser (
    subgruite character varying(20),
    gruprinci character varying(20)
);


--
-- Name: hisdetdiagen; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.hisdetdiagen (
    fecha character varying(10),
    codcuenta character varying(30),
    detalle character varying(200),
    debe character varying(15),
    haber character varying(15),
    numasient bigint,
    seqasient bigint,
    "año" character varying(4),
    mes character varying(2)
);


--
-- Name: hismaygeneral; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.hismaygeneral (
    codcuenta character varying(30),
    fecmovimi timestamp without time zone,
    numasient bigint,
    seqasient bigint,
    valmovdeb double precision,
    valmovhab double precision,
    valsalpar double precision,
    reference character varying(200),
    "año" character varying(4),
    mes character varying(2)
);


--
-- Name: hisrolgeneral; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.hisrolgeneral (
    numero bigint,
    nombres character varying(255),
    cargo character varying(255),
    salario bigint,
    dl bigint,
    estructura character varying(255),
    arecibir bigint,
    fr character varying(255),
    he character varying(255),
    xiv character varying(255),
    xiii character varying(255),
    toting character varying(255),
    ingconaporte character varying(255),
    aporte character varying(255),
    dnlprestamos character varying(255),
    fracu character varying(255),
    totegr character varying(255),
    liquido character varying(255),
    mes character varying(255),
    "año" character varying(255)
);


--
-- Name: hissaldos; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.hissaldos (
    codcuenta character varying(30),
    saliniper double precision,
    salfinper double precision,
    "año" character varying(4),
    mes character varying(2),
    tipcuenta character varying(1),
    nomcuenta character varying(70)
);


--
-- Name: hisvendedores; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.hisvendedores (
    codvended character varying(10),
    perventas character varying(7),
    nomvended character varying(30),
    valvenmes double precision,
    valvenefe double precision,
    valvencre double precision,
    valventar double precision,
    valcobros double precision
);


--
-- Name: items; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.items (
    coditem character varying(30),
    desitem character varying(250),
    canitem bigint,
    canminite bigint,
    cositem double precision,
    porutiuno double precision,
    porutidos double precision,
    porutitre double precision,
    pvpunoite double precision,
    pvpdosite double precision,
    pvptreite character varying(50),
    aplivaite boolean NOT NULL,
    pvpunoiva double precision,
    pvpdosiva double precision,
    pvptreiva double precision,
    canpvpuno double precision,
    canpvpdos double precision,
    canpvptre double precision,
    codprovee character varying(8),
    fecultcom timestamp without time zone,
    fecultvta timestamp without time zone,
    codbodega character varying(20),
    ubicacion character varying(50),
    tipitem character varying(10),
    gruprinci character varying(20),
    subgruite character varying(20),
    segsubgru character varying(20),
    iteactivo boolean NOT NULL,
    apliceite boolean NOT NULL,
    codcueinv character varying(30),
    codcueing character varying(30),
    cospromed double precision,
    poriceite double precision,
    codcuecosser character varying(30)
);


--
-- Name: kardexitems; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.kardexitems (
    numdockar bigint,
    coditeinv character varying(30),
    fecmovite timestamp without time zone,
    tipmovite character varying(1),
    canmovite double precision,
    cositemov double precision,
    pvpitemov double precision,
    valtotmov double precision,
    refmovite character varying(100),
    numdocume character varying(25),
    saldoexis double precision
);


--
-- Name: mayorgeneral; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.mayorgeneral (
    codcuenta character varying(30),
    fecmovimi timestamp without time zone,
    numasient bigint,
    seqasient bigint,
    valmovdeb double precision,
    valmovhab double precision,
    valsalpar double precision,
    reference character varying(200)
);


--
-- Name: movbancos; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.movbancos (
    codcuenta character varying(30),
    seqmovimi bigint,
    numcompro bigint,
    fecmovimi timestamp without time zone,
    tipmovimi character varying(3),
    numdocume character varying(25),
    valmovimi numeric(19,4),
    detmovimi character varying(200),
    commovimi character varying(165),
    validados character varying(10),
    nombenefi character varying(50),
    userid character varying(10),
    impdocume boolean NOT NULL,
    impcompro boolean NOT NULL,
    codcuecon character varying(30)
);


--
-- Name: ncventas; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.ncventas (
    numnc character varying(255),
    autorizacion character varying(255),
    fecnc character varying(255),
    ruccedcli character varying(255),
    nomcli character varying(255),
    tipid character varying(255),
    codcomp character varying(255),
    numemi character varying(255),
    basenoobj character varying(255),
    baseiva0 character varying(255),
    baseiva12 character varying(255),
    iva character varying(255),
    ice character varying(255),
    numfac character varying(255),
    autfac character varying(255),
    fecfac character varying(255),
    mes character varying(255),
    "año" character varying(255),
    numasiento character varying(255)
);


--
-- Name: parametros; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.parametros (
    numfactur integer,
    numserfac character varying(11),
    numautfac character varying(37),
    fecautfac timestamp without time zone,
    numdetfac integer,
    numfactem integer,
    numretenc integer,
    numserret character varying(255),
    numautret bigint,
    fecautret timestamp without time zone,
    numcomgp character varying(255),
    numnc integer,
    numsernc character varying(255),
    numautnc bigint,
    fecautnc timestamp without time zone,
    numcompra integer,
    numdetcom integer,
    combander character varying(15),
    numcompranv integer,
    combandernv character varying(15),
    numrettmp integer,
    poriva double precision,
    numdockar integer,
    numctapro integer,
    numctacli integer,
    numcuepag integer,
    numcuecob integer,
    numdevcom integer,
    numdevven integer,
    numdetcomnv integer,
    tipcontab character varying(10),
    facporlot character varying(2),
    salcajgen double precision,
    nummovcaj integer,
    salcajchi double precision,
    nummovban integer,
    nummovcajchi integer,
    numcomingban integer,
    numcomegrban integer,
    numcomingcaj integer,
    numcomegrcaj integer,
    numcomingcajchi integer,
    numcomegrcajchi integer,
    numantcli integer,
    numnotcre integer,
    numcopfac integer,
    numcopret integer,
    numcopnotven integer,
    fecultres timestamp without time zone,
    numdialisfac integer,
    nomempresa character varying(150),
    obliconta character varying(255),
    contrespec character varying(255),
    codcontrespec character varying(255),
    mesrol character varying(255),
    "añorol" character varying(255),
    notasgen text,
    asumeiess character varying(255),
    facfiselec character varying(255),
    codest character varying(3),
    ptoemi character varying(3),
    codval character varying(255),
    facemi character varying(9),
    retemi character varying(9),
    ncemi character varying(9),
    trabacti character varying(255),
    calculoice boolean NOT NULL
);


--
-- Name: parametroscontables; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.parametroscontables (
    numasient bigint,
    numasitem bigint,
    facporlot character varying(2),
    diagracie bigint,
    cuedescom character varying(30),
    cuedesven character varying(30),
    cuedevcom character varying(30),
    cuedevven character varying(30),
    comtarcre character varying(30),
    cajgenera character varying(30),
    cuecajchi character varying(30),
    cuecosven character varying(30),
    cueivacobbie character varying(30),
    cueivapagbie character varying(30),
    cueivaret character varying(30),
    cuefueret character varying(30),
    cueretiva character varying(30),
    cueretfue character varying(30),
    cueutili character varying(30),
    flglibdia character varying(10),
    cueivaret2 character varying(30),
    cueivaret3 character varying(30),
    cuefueret2 character varying(30),
    cuefueret3 character varying(30),
    cuefueret4 character varying(30),
    cueingban character varying(30),
    cuegasban character varying(30),
    ultpercon character varying(6),
    ultperiod timestamp without time zone,
    actperiod timestamp without time zone,
    cueivacobser character varying(30),
    cueivapagser character varying(30),
    cueicepagbie character varying(30),
    cueicepagser character varying(30),
    cueperinv character varying(30)
);


--
-- Name: plancuentas; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.plancuentas (
    codcuenta character varying(30),
    nomcuenta character varying(70),
    tipcuenta character varying(1),
    codcuegru character varying(30),
    codgrupri character varying(30),
    saliniper double precision,
    salfinper double precision,
    tiesubcue character varying(255)
);


--
-- Name: productosice; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.productosice (
    codprodice character varying(255),
    nombre character varying(255),
    precio double precision,
    ice double precision,
    gramoazucar character varying(255)
);


--
-- Name: retencclient; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.retencclient (
    numdocume character varying(16),
    ruccedcli character varying(13),
    fecretenc timestamp without time zone,
    numfactur character varying(15),
    basimpfuebie double precision,
    porretfuebie double precision,
    valretfuebie double precision,
    basimpivabie double precision,
    porretivabie double precision,
    valretivabie double precision,
    basimpfueser double precision,
    porretfueser double precision,
    valretfueser double precision,
    basimpivaser double precision,
    porretivaser double precision,
    valretivaser double precision,
    totretenc double precision,
    fecrecepc timestamp without time zone,
    numasiuno bigint
);


--
-- Name: retenciones; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.retenciones (
    numdocume character varying(25),
    ruccedpro character varying(13),
    fecretenc timestamp without time zone,
    numfactur character varying(110),
    totretenc double precision,
    responsab character varying(20),
    retimpres boolean NOT NULL,
    estproret character varying(10)
);


--
-- Name: retencionestmp; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.retencionestmp (
    numdocume character varying(25),
    ruccedpro character varying(13),
    fecretenc timestamp without time zone,
    numfactur character varying(25),
    basretfue double precision,
    porretfue double precision,
    valretfue double precision,
    basretiva double precision,
    porretiva double precision,
    valretiva double precision,
    numrettmp bigint,
    tipdocume character varying(3),
    codcueconfue character varying(30),
    codcueconiva character varying(30),
    autorizacion character varying(255)
);


--
-- Name: rolgeneral; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.rolgeneral (
    numero bigint,
    nombres character varying(255),
    cargo character varying(255),
    salario double precision,
    dl bigint,
    estructura character varying(255),
    arecibir double precision,
    fr double precision,
    he double precision,
    xiv double precision,
    xiii double precision,
    comisiones double precision,
    bonos double precision,
    toting double precision,
    ingconaporte double precision,
    aporte double precision,
    dnlprestamos double precision,
    fracu double precision,
    totegr double precision,
    liquido double precision,
    mes character varying(255),
    "año" character varying(255),
    estado character varying(255)
);


--
-- Name: rolgeneraldomestica; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.rolgeneraldomestica (
    numero bigint,
    nombres character varying(255),
    cargo character varying(255),
    salario double precision,
    dl bigint,
    estructura character varying(255),
    arecibir double precision,
    fr double precision,
    he double precision,
    xiv double precision,
    xiii double precision,
    comisiones double precision,
    bonos double precision,
    toting double precision,
    ingconaporte double precision,
    aporte double precision,
    dnlprestamos double precision,
    fracu double precision,
    totegr double precision,
    liquido double precision,
    mes character varying(255),
    "año" character varying(255),
    estado character varying(255)
);


--
-- Name: seguridad; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.seguridad (
    usrname character varying(10),
    nomusuari character varying(50),
    conusuari character varying(50),
    ingsalida boolean NOT NULL,
    s0100 boolean NOT NULL,
    s0101 boolean NOT NULL,
    s0102 boolean NOT NULL,
    s0103 boolean NOT NULL,
    s0104 boolean NOT NULL,
    s0105 boolean NOT NULL,
    s0106 boolean NOT NULL,
    s0107 boolean NOT NULL,
    s0108 boolean NOT NULL,
    s0109 boolean NOT NULL,
    s0110 boolean NOT NULL,
    s0111 boolean NOT NULL,
    s0112 boolean NOT NULL,
    s0200 boolean NOT NULL,
    s0201 boolean NOT NULL,
    s0202 boolean NOT NULL,
    s0203 boolean NOT NULL,
    s0204 boolean NOT NULL,
    s0205 boolean NOT NULL,
    s0206 boolean NOT NULL,
    s0207 boolean NOT NULL,
    s0208 boolean NOT NULL,
    s0209 boolean NOT NULL,
    s0210 boolean NOT NULL,
    s0211 boolean NOT NULL,
    s0212 boolean NOT NULL,
    s0213 boolean NOT NULL,
    s0214 boolean NOT NULL,
    s0215 boolean NOT NULL,
    s0216 boolean NOT NULL,
    s0217 boolean NOT NULL,
    s0218 boolean NOT NULL,
    s0219 boolean NOT NULL,
    s0220 boolean NOT NULL,
    s0221 boolean NOT NULL,
    s0222 boolean NOT NULL,
    s0223 boolean NOT NULL,
    s0300 boolean NOT NULL,
    s0301 boolean NOT NULL,
    s0302 boolean NOT NULL,
    s0303 boolean NOT NULL,
    s0304 boolean NOT NULL,
    s0305 boolean NOT NULL,
    s0306 boolean NOT NULL,
    s0307 boolean NOT NULL,
    s0308 boolean NOT NULL,
    s0309 boolean NOT NULL,
    s0310 boolean NOT NULL,
    s0311 boolean NOT NULL,
    s0312 boolean NOT NULL,
    s0313 boolean NOT NULL,
    s0314 boolean NOT NULL,
    s0315 boolean NOT NULL,
    s0316 boolean NOT NULL,
    s0317 boolean NOT NULL,
    s0318 boolean NOT NULL,
    s0319 boolean NOT NULL,
    s0320 boolean NOT NULL,
    s0400 boolean NOT NULL,
    s0401 boolean NOT NULL,
    s0402 boolean NOT NULL,
    s0403 boolean NOT NULL,
    s0404 boolean NOT NULL,
    s0405 boolean NOT NULL,
    s0406 boolean NOT NULL,
    s0407 boolean NOT NULL,
    s0500 boolean NOT NULL,
    s0501 boolean NOT NULL,
    s0502 boolean NOT NULL,
    s0503 boolean NOT NULL,
    s0504 boolean NOT NULL,
    s0505 boolean NOT NULL,
    s0506 boolean NOT NULL,
    s0507 boolean NOT NULL,
    s0508 boolean NOT NULL,
    s0509 boolean NOT NULL,
    s0510 boolean NOT NULL,
    s0511 boolean NOT NULL,
    s0512 boolean NOT NULL,
    s0513 boolean NOT NULL,
    s0514 boolean NOT NULL,
    s0600 boolean NOT NULL,
    s0601 boolean NOT NULL,
    s0602 boolean NOT NULL,
    s0603 boolean NOT NULL,
    s0604 boolean NOT NULL,
    s0605 boolean NOT NULL,
    s0700 boolean NOT NULL,
    s0701 boolean NOT NULL,
    s0702 boolean NOT NULL,
    s0703 boolean NOT NULL,
    s0800 boolean NOT NULL,
    s0801 boolean NOT NULL,
    s0802 boolean NOT NULL,
    s0803 boolean NOT NULL,
    s0804 boolean NOT NULL,
    s0900 boolean NOT NULL,
    s0901 boolean NOT NULL,
    s0902 boolean NOT NULL,
    s0903 boolean NOT NULL,
    s0904 boolean NOT NULL,
    s0905 boolean NOT NULL,
    s0906 boolean NOT NULL,
    s0907 boolean NOT NULL,
    s0908 boolean NOT NULL,
    s0909 boolean NOT NULL,
    s0910 boolean NOT NULL,
    s1000 boolean NOT NULL,
    s1001 boolean NOT NULL,
    s1002 boolean NOT NULL,
    s1003 boolean NOT NULL,
    s1004 boolean NOT NULL
);


--
-- Name: trabajadores; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.trabajadores (
    cedula character varying(10),
    nombres character varying(255),
    sexo character varying(255),
    fecnac timestamp without time zone,
    cargas bigint,
    direccion character varying(255),
    telefono character varying(255),
    activo boolean NOT NULL,
    fecentrada timestamp without time zone,
    codcomision character varying(255),
    comisionsec character varying(255),
    cargo character varying(255),
    tipojornada character varying(255),
    sueldo double precision,
    fecsalida timestamp without time zone,
    motivos character varying(255),
    fr boolean NOT NULL,
    xiv boolean NOT NULL,
    xiii boolean NOT NULL,
    notastra text,
    jn character varying(255),
    horaslab character varying(255)
);


--
-- Name: vendedores; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.vendedores (
    codvended character varying(10),
    nomvended character varying(30),
    nomusuari character varying(10),
    valvenmes double precision,
    valvenefe double precision,
    valvencre double precision,
    valventar double precision,
    valcobros double precision,
    valvenmestem double precision,
    valvenefetem double precision,
    valvencretem double precision,
    valventartem double precision,
    valcobrostem double precision
);


--
-- Name: ventas; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.ventas (
    numfactur character varying(255),
    autorizacion character varying(255),
    fecfactur character varying(255),
    ruccedcli character varying(255),
    nomcli character varying(255),
    tipid character varying(255),
    codcomp character varying(255),
    numemi character varying(255),
    basenoobj character varying(255),
    baseiva0 character varying(255),
    baseiva12 character varying(255),
    iva character varying(255),
    ice character varying(255),
    numret character varying(255),
    autret character varying(255),
    fecret character varying(255),
    retiva character varying(255),
    retrenta character varying(255),
    mes character varying(255),
    "año" character varying(255),
    numasiento character varying(255),
    baseiva5 numeric(14,2) DEFAULT 0 NOT NULL,
    baseiva8 numeric(14,2) DEFAULT 0 NOT NULL,
    baseiva14 numeric(14,2) DEFAULT 0 NOT NULL,
    baseiva15 numeric(14,2) DEFAULT 0 NOT NULL,
    iva5 numeric(14,2) DEFAULT 0 NOT NULL,
    iva8 numeric(14,2) DEFAULT 0 NOT NULL,
    iva12 numeric(14,2) DEFAULT 0 NOT NULL,
    iva14 numeric(14,2) DEFAULT 0 NOT NULL,
    iva15 numeric(14,2) DEFAULT 0 NOT NULL
);


--
-- PostgreSQL database dump complete
--

