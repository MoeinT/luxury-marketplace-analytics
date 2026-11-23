with buyer_totals as (
    select
        buyer_id,
        min(created_at) as first_order_at,
        count(*) as lifetime_orders,
        sum(
            case
                when status not in (
                    'cancelled',
                    'rejected_at_authentication',
                    'returned'
                ) then gmv_eur
                else 0
            end
        )::numeric(16, 2) as lifetime_net_gmv_eur
    from {{ ref("int_orders_enriched") }}
    group by buyer_id
)

select
    buyer_id,
    first_order_at,
    lifetime_orders,
    lifetime_net_gmv_eur,
    case
        when lifetime_orders = 1 then 'new'
        when lifetime_net_gmv_eur >= 5000 then 'vip'
        else 'returning'
    end as buyer_segment_current
from buyer_totals
