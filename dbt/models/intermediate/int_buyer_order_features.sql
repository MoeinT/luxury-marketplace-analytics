with order_history as (
    select
        order_id,
        buyer_id,
        created_at,
        gmv_eur,
        count(*) over (
            partition by buyer_id
            order by created_at, order_id
            rows between unbounded preceding and 1 preceding
        ) as prior_order_count,
        coalesce(
            sum(gmv_eur) over (
                partition by buyer_id
                order by created_at, order_id
                rows between unbounded preceding and 1 preceding
            ),
            0
        )::numeric(16, 2) as prior_submitted_gmv_eur
    from {{ ref("int_orders_enriched") }}
)

select
    order_id,
    buyer_id,
    created_at,
    gmv_eur,
    prior_order_count,
    prior_submitted_gmv_eur,
    case
        when prior_order_count = 0 then 'new'
        when prior_submitted_gmv_eur >= 5000 then 'vip'
        else 'returning'
    end as buyer_segment_at_order,
    prior_order_count = 0 as is_first_order
from order_history
