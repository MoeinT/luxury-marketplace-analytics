select
    rate_date,
    currency
from {{ ref("fx_rates") }}
group by rate_date, currency
having count(*) > 1
