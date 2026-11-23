select
    rate_date::date as rate_date,
    upper(trim(currency))::text as currency,
    rate_to_eur::numeric(12, 4) as rate_to_eur
from {{ ref("fx_rates") }}
