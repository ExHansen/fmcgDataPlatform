{# Tanggal SAP (DATS 'YYYYMMDD'); '00000000' / kosong = null. #}
{% macro sap_date(column) -%}
    case when nullif(nullif(trim({{ column }}), ''), '00000000') is null then null
         else to_date({{ column }}, 'YYYYMMDD') end
{%- endmacro %}

{# Hapus leading zero kunci SAP (konversi ALPHA balik) agar bisa dicocokkan dengan sistem lain. #}
{% macro strip_zeros(column) -%}
    nullif(ltrim(trim({{ column }}), '0'), '')
{%- endmacro %}

{# Angka teks -> numeric. 'id' = format Indonesia (titik ribuan, koma desimal). #}
{% macro parse_number(column, number_format='plain') -%}
    {%- if number_format == 'id' -%}
    nullif(replace(replace(trim({{ column }}), '.', ''), ',', '.'), '')::numeric
    {%- else -%}
    nullif(trim({{ column }}), '')::numeric
    {%- endif -%}
{%- endmacro %}

{% macro parse_date(column, date_format) -%}
    {%- if date_format == 'excel_iso' -%}
    left(trim({{ column }}), 10)::date
    {%- else -%}
    to_date(trim({{ column }}), '{{ date_format }}')
    {%- endif -%}
{%- endmacro %}

{# Normalisasi nama untuk pencocokan: huruf besar, tanpa tanda baca, spasi tunggal. #}
{% macro normalize_name(column) -%}
    trim(regexp_replace(regexp_replace(upper({{ column }}), '[^A-Z0-9 ]', ' ', 'g'), '\s+', ' ', 'g'))
{%- endmacro %}

{# Nilai pertama yang ada dari beberapa nama kolom alternatif di payload jsonb. #}
{% macro payload_field(aliases, payload='payload') -%}
    {%- if aliases | length == 1 -%}
    {{ payload }} ->> '{{ aliases[0] }}'
    {%- else -%}
    coalesce({% for a in aliases %}{{ payload }} ->> '{{ a }}'{{ ", " if not loop.last }}{% endfor %})
    {%- endif -%}
{%- endmacro %}

{# Versi terbaru per kunci dari tabel raw append-only (raw_sap = log perubahan). #}
{% macro latest_version(relation, keys) -%}
    select * from (
        select *, row_number() over (partition by {{ keys | join(', ') }}
                                     order by _ingested_at desc, _record_hash) as _version_rank
        from {{ relation }}
    ) ranked
    where _version_rank = 1
{%- endmacro %}
