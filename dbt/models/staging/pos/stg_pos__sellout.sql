{#
  Sell-out POS per retailer x toko x artikel x tanggal.
  - Hanya file versi terakhir per (retailer, minggu).
  - EAN dipad kembali ke 13 digit (Excel menghapus leading zero).
  - Baris identik dalam satu file = kiriman dobel -> dibuang.
  - Retur (qty negatif) dipisah lewat is_return; harga tidak wajar ditandai is_price_outlier.
#}
with files as (
    select
        batch_id, source_system, business_date, version, received_at,
        row_number() over (partition by source_system, business_date order by version desc) as version_rank
    from {{ source('ops', 'file_manifest') }}
    where status = 'LOADED' and source_system like 'POS\_%'
),

parsed as (
    select
        r.retailer_code,
        trim(r.payload ->> 'STORE_CODE')                    as store_code,
        trim(r.payload ->> 'STORE_NAME')                    as store_name,
        trim(r.payload ->> 'ARTICLE_CODE')                  as article_code,
        trim(r.payload ->> 'EAN')                           as ean_reported,
        lpad(trim(r.payload ->> 'EAN'), 13, '0')            as ean,
        trim(r.payload ->> 'DESCRIPTION')                   as article_description,
        (r.payload ->> 'SALES_DATE')::date                  as sales_date,
        (r.payload ->> 'QTY')::numeric                      as qty,
        {{ parse_number("r.payload ->> 'GROSS_SALES'") }}   as gross_sales,
        {{ parse_number("r.payload ->> 'DISCOUNT'") }}      as discount,
        {{ parse_number("r.payload ->> 'NET_SALES'") }}     as net_sales,
        f.business_date                                     as week_start_date,
        f.version                                           as file_version,
        f.received_at,
        r.source_row_number,
        r._source_system                                    as source_system,
        r._batch_id,
        r._ingested_at
    from {{ source('raw_pos', 'sellout') }} r
    join files f on f.batch_id = r._batch_id and f.version_rank = 1
),

deduped as (
    select *,
        row_number() over (
            partition by retailer_code, store_code, article_code, sales_date, qty, net_sales, _batch_id
            order by source_row_number) as duplicate_rank
    from parsed
),

article_price as (
    select retailer_code, article_code, percentile_cont(0.5) within group (order by net_sales / qty) as median_unit_price
    from parsed
    where qty > 0
    group by 1, 2
)

select
    {{ dbt_utils.generate_surrogate_key(['d.retailer_code', 'd.store_code', 'd.article_code', 'd.sales_date', 'd.qty < 0']) }}
                                                as sellout_line_id,
    d.retailer_code,
    d.source_system,
    d.store_code,
    d.store_name,
    d.article_code,
    d.ean_reported,
    d.ean,
    d.ean_reported <> d.ean                     as is_ean_repaired,
    d.article_description,
    d.sales_date,
    d.qty,
    d.qty < 0                                   as is_return,
    d.gross_sales,
    d.discount,
    d.net_sales,
    d.net_sales / nullif(d.qty, 0)              as unit_net_price,
    abs(d.net_sales / nullif(d.qty, 0)) > {{ var('pos_price_outlier_factor') }} * p.median_unit_price
                                                as is_price_outlier,
    d.week_start_date,
    d.file_version,
    d.received_at,
    d._batch_id,
    d._ingested_at
from deduped d
left join article_price p using (retailer_code, article_code)
where d.duplicate_rank = 1
