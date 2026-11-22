select
    order_date,
    category,
    buyer_country,
    buyer_segment
from {{ ref("mart_ops_daily_gmv") }}
group by order_date, category, buyer_country, buyer_segment
having count(*) > 1
