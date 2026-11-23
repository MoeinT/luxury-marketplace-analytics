select
    to_date(month || '-01', 'YYYY-MM-DD') as month_start,
    gmv_eur::numeric(16, 2) as reported_gmv_eur,
    closed_on::date as closed_on
from {{ ref("finance_monthly_gmv") }}
