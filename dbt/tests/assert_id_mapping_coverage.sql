{# Gagal jika ada sumber dengan cakupan mapping (berdasar nilai penjualan) di bawah ambang. #}
select *
from {{ ref('id_mapping_coverage') }}
where pct_value_mapped < threshold_pct
