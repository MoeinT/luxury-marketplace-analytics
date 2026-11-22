{{
    config(
        materialized="incremental",
        unique_key="month_start",
        incremental_strategy="append"
    )
}}

select
    month_start,
    reported_gmv_eur,
    closed_on
from {{ ref("stg_finance_monthly_gmv") }} as source
{% if is_incremental() %}
where not exists (
    select 1
    from {{ this }} as frozen
    where frozen.month_start = source.month_start
)
{% endif %}
