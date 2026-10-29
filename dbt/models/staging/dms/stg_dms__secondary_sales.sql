{#
  Secondary sales distributor -> toko, 3 format file disatukan.
  - Hanya file versi terakhir per (distributor, tanggal bisnis): kiriman ulang menggantikan versi lama.
  - Nama kolom per distributor dari var `dms_sources` (alias kolom karena schema drift).
  - Angka format Indonesia, 3 format tanggal, UoM KRT/CTN -> CASE (konversi ke PCS di intermediate).
#}
{%- set dms = var('dms_sources') -%}

with files as (
    select
        batch_id, source_system, business_date, version, received_at, file_path,
        row_number() over (partition by source_system, business_date order by version desc) as version_rank
    from {{ source('ops', 'file_manifest') }}
    where status = 'LOADED' and source_system like 'DMS\_%'
),

latest_rows as (
    select r.*, f.business_date, f.version as file_version, f.received_at, f.file_path
    from {{ source('raw_dms', 'secondary_sales') }} r
    join files f on f.batch_id = r._batch_id and f.version_rank = 1
),

{% for dist, cfg in dms.items() %}
{%- set c = cfg.columns -%}
parsed_{{ dist | lower }} as (
    select
        distributor_code,
        trim({{ payload_field(c.invoice_no) }})                                     as invoice_no,
        {{ parse_date(payload_field(c.invoice_date), cfg.date_format) }}            as invoice_date,
        trim({{ payload_field(c.outlet_code) }})                                    as outlet_code,
        trim({{ payload_field(c.outlet_name) }})                                    as outlet_name,
        trim({{ payload_field(c.product_code) }})                                   as product_code,
        {% if c.product_name is defined %}trim({{ payload_field(c.product_name) }}){% else %}null{% endif %} as product_name,
        {{ parse_number(payload_field(c.qty), cfg.number_format) }}                 as qty,
        {% if c.uom is defined %}upper(trim({{ payload_field(c.uom) }})){% else %}'PCS'{% endif %} as uom_reported,
        {% if c.unit_price is defined -%}
        {{ parse_number(payload_field(c.unit_price), cfg.number_format) }}
            * {{ parse_number(payload_field(c.qty), cfg.number_format) }}           as gross_value,
        {%- else -%}
        {{ parse_number(payload_field(c.gross_value), cfg.number_format) }}         as gross_value,
        {%- endif %}
        {{ parse_number(payload_field(c.discount_value), cfg.number_format) }}      as discount_value,
        {{ parse_number(payload_field(c.net_value), cfg.number_format) }}           as net_value,
        business_date, file_version, received_at, file_path,
        source_row_number, _source_system, _batch_id, _ingested_at
    from latest_rows
    where distributor_code = '{{ dist }}'
){{ "," if not loop.last }}
{% endfor %}

, unioned as (
    {% for dist in dms %}
    select * from parsed_{{ dist | lower }}
    {% if not loop.last %}union all{% endif %}
    {% endfor %}
)

select
    {{ dbt_utils.generate_surrogate_key(['distributor_code', 'invoice_no', 'product_code']) }} as shipment_line_id,
    distributor_code,
    _source_system                          as source_system,
    invoice_no,
    invoice_date,
    outlet_code,
    outlet_name,
    product_code,
    product_name,
    qty,
    uom_reported,
    case uom_reported
        {% for k, v in var('uom_map').items() %}when '{{ k }}' then '{{ v }}' {% endfor %}
    end                                     as uom,
    gross_value,
    discount_value,
    net_value,
    business_date,
    file_version,
    received_at,
    (received_at at time zone 'Asia/Jakarta')::date - invoice_date as days_late,
    file_path,
    source_row_number,
    _batch_id,
    _ingested_at
from unioned
