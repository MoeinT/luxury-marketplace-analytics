select
    created_at::date as order_date,
    category,
    buyer_country,
    buyer_segment,
    count(*) as orders,
    count(*) filter (where status = 'cancelled') as cancelled_orders,
    count(*) filter (
        where status = 'rejected_at_authentication'
    ) as authentication_rejections,
    count(*) filter (where status = 'returned') as returned_orders,
    round(
        count(*) filter (where status = 'cancelled')::numeric
        / nullif(count(*), 0),
        4
    ) as cancellation_rate,
    sum(net_gmv_eur_operational)::numeric(18, 2)
        as net_gmv_eur_operational,
    sum(gmv_eur) filter (where status = 'cancelled')::numeric(18, 2)
        as cancelled_gmv_eur
from {{ ref("fct_orders") }}
group by 1, 2, 3, 4
