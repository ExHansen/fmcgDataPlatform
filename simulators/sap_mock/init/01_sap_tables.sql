-- Tiruan tabel SAP SD (ECC / S/4HANA). Nama kolom mengikuti nama field SAP (huruf kecil).
-- Tipe meniru kamus data SAP: tanggal DATS = char(8) 'YYYYMMDD' ('00000000' = kosong),
-- jam TIMS = char(6), kunci numerik disimpan dengan leading zero (konversi ALPHA).

create schema if not exists sap;
set search_path to sap;

-- ---------- Master data ----------
create table kna1 (                -- customer master (umum)
    mandt   char(3)      not null,
    kunnr   char(10)     not null,
    name1   varchar(35)  not null,
    land1   char(3)      not null,
    regio   char(3),
    ort01   varchar(35),
    stras   varchar(35),
    ktokd   char(4)      not null, -- grup akun: ZDIS = distributor
    erdat   char(8)      not null,
    primary key (mandt, kunnr)
);

create table knvv (                -- customer per sales area
    mandt   char(3)  not null,
    kunnr   char(10) not null,
    vkorg   char(4)  not null,
    vtweg   char(2)  not null,
    spart   char(2)  not null,
    kdgrp   char(2),
    erdat   char(8)  not null,
    primary key (mandt, kunnr, vkorg, vtweg, spart)
);

create table mara (                -- material master (umum)
    mandt   char(3)      not null,
    matnr   char(18)     not null,
    mtart   char(4)      not null, -- FERT = finished good
    matkl   char(9)      not null, -- material group (kategori)
    prdha   char(18),              -- product hierarchy (brand)
    meins   char(3)      not null, -- base UoM
    ean11   varchar(18),
    brgew   numeric(13,3),
    gewei   char(3),
    ersda   char(8)      not null, -- created on
    laeda   char(8)      not null, -- last changed on
    lvorm   char(1)      not null default '', -- flag hapus
    primary key (mandt, matnr)
);

create table makt (                -- deskripsi material
    mandt   char(3)     not null,
    matnr   char(18)    not null,
    spras   char(1)     not null,
    maktx   varchar(40) not null,
    primary key (mandt, matnr, spras)
);

create table marm (                -- konversi satuan
    mandt   char(3)  not null,
    matnr   char(18) not null,
    meinh   char(3)  not null,
    umrez   numeric(5,0) not null, -- pembilang
    umren   numeric(5,0) not null, -- penyebut
    ean11   varchar(18),
    primary key (mandt, matnr, meinh)
);

create table t023t (               -- teks material group
    mandt   char(3)     not null,
    spras   char(1)     not null,
    matkl   char(9)     not null,
    wgbez   varchar(20) not null,
    wgbez60 varchar(60),
    primary key (mandt, spras, matkl)
);

create table t179t (               -- teks product hierarchy
    mandt   char(3)     not null,
    spras   char(1)     not null,
    prodh   char(18)    not null,
    vtext   varchar(40) not null,
    primary key (mandt, spras, prodh)
);

-- ---------- Sales order ----------
create table vbak (
    mandt   char(3)  not null,
    vbeln   char(10) not null,
    auart   char(4)  not null,       -- ZOR = standard order
    audat   char(8)  not null,       -- tanggal dokumen
    erdat   char(8)  not null,
    erzet   char(6)  not null,
    aedat   char(8)  not null default '00000000',
    vkorg   char(4)  not null,
    vtweg   char(2)  not null,
    spart   char(2)  not null,
    kunnr   char(10) not null,       -- sold-to
    bstnk   varchar(20),             -- no. PO customer
    netwr   numeric(15,2) not null,
    waerk   char(5)  not null,
    primary key (mandt, vbeln)
);

create table vbap (
    mandt   char(3)  not null,
    vbeln   char(10) not null,
    posnr   char(6)  not null,
    matnr   char(18) not null,
    arktx   varchar(40),
    kwmeng  numeric(15,3) not null,  -- qty order (sales UoM)
    vrkme   char(3)  not null,       -- sales UoM
    meins   char(3)  not null,       -- base UoM
    umvkz   numeric(5,0) not null,   -- faktor konversi sales->base (pembilang)
    umvkn   numeric(5,0) not null,
    netwr   numeric(15,2) not null,
    waerk   char(5)  not null,
    werks   char(4)  not null,
    abgru   char(2)  not null default '',  -- alasan reject
    erdat   char(8)  not null,
    aedat   char(8)  not null default '00000000',
    primary key (mandt, vbeln, posnr)
);

create table vbep (                -- schedule line
    mandt   char(3)  not null,
    vbeln   char(10) not null,
    posnr   char(6)  not null,
    etenr   char(4)  not null,
    edatu   char(8)  not null,
    wmeng   numeric(15,3) not null,  -- qty diminta
    bmeng   numeric(15,3) not null,  -- qty dikonfirmasi
    primary key (mandt, vbeln, posnr, etenr)
);

-- ---------- Delivery ----------
create table likp (
    mandt     char(3)  not null,
    vbeln     char(10) not null,
    lfart     char(4)  not null,     -- LF = outbound delivery
    erdat     char(8)  not null,
    erzet     char(6)  not null,
    aedat     char(8)  not null default '00000000',
    vstel     char(4)  not null,
    kunnr     char(10) not null,     -- ship-to
    lfdat     char(8)  not null,     -- tanggal kirim rencana
    wadat     char(8)  not null,     -- goods issue rencana
    wadat_ist char(8)  not null default '00000000', -- goods issue aktual
    primary key (mandt, vbeln)
);

create table lips (
    mandt   char(3)  not null,
    vbeln   char(10) not null,
    posnr   char(6)  not null,
    matnr   char(18) not null,
    lfimg   numeric(13,3) not null,  -- qty dikirim (sales UoM)
    vrkme   char(3)  not null,
    meins   char(3)  not null,
    umvkz   numeric(5,0) not null,
    umvkn   numeric(5,0) not null,
    werks   char(4)  not null,
    vgbel   char(10) not null,       -- ref sales order
    vgpos   char(6)  not null,
    erdat   char(8)  not null,
    primary key (mandt, vbeln, posnr)
);

-- ---------- Billing ----------
create table vbrk (
    mandt   char(3)  not null,
    vbeln   char(10) not null,
    fkart   char(4)  not null,       -- F2 = invoice, S1 = pembatalan invoice
    fkdat   char(8)  not null,
    erdat   char(8)  not null,
    erzet   char(6)  not null,
    aedat   char(8)  not null default '00000000',
    vkorg   char(4)  not null,
    vtweg   char(2)  not null,
    kunag   char(10) not null,       -- sold-to
    kunrg   char(10) not null,       -- payer
    netwr   numeric(15,2) not null,
    waerk   char(5)  not null,
    fksto   char(1)  not null default '',   -- 'X' = sudah dibatalkan
    sfakn   char(10) not null default '',   -- dokumen yang dibatalkan (untuk S1)
    primary key (mandt, vbeln)
);

create table vbrp (
    mandt   char(3)  not null,
    vbeln   char(10) not null,
    posnr   char(6)  not null,
    matnr   char(18) not null,
    arktx   varchar(40),
    fkimg   numeric(13,3) not null,  -- qty ditagih (sales UoM)
    vrkme   char(3)  not null,
    meins   char(3)  not null,
    umvkz   numeric(5,0) not null,
    umvkn   numeric(5,0) not null,
    netwr   numeric(15,2) not null,
    aubel   char(10) not null,       -- ref sales order
    aupos   char(6)  not null,
    vgbel   char(10) not null,       -- ref delivery
    vgpos   char(6)  not null,
    werks   char(4)  not null,
    erdat   char(8)  not null,
    primary key (mandt, vbeln, posnr)
);

-- ---------- Document flow ----------
create table vbfa (
    mandt   char(3)  not null,
    vbelv   char(10) not null,       -- dokumen asal
    posnv   char(6)  not null,
    vbeln   char(10) not null,       -- dokumen tujuan
    posnn   char(6)  not null,
    vbtyp_n char(1)  not null,       -- J = delivery, M = invoice, N = pembatalan invoice
    rfmng   numeric(15,3) not null,
    erdat   char(8)  not null,
    primary key (mandt, vbelv, posnv, vbeln, posnn)
);

-- Index untuk ekstraksi incremental berbasis tanggal (meniru index sekunder SAP)
create index vbak_erdat_aedat on vbak (erdat, aedat);
create index likp_erdat_aedat on likp (erdat, aedat);
create index vbrk_erdat_aedat on vbrk (erdat, aedat);
