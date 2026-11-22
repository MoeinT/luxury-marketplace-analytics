select
    fact.order_id,
    fact.buyer_segment,
    features.buyer_segment_at_order
from {{ ref("fct_orders") }} as fact
join {{ ref("int_buyer_order_features") }} as features
    on fact.order_id = features.order_id
where fact.buyer_segment is distinct from features.buyer_segment_at_order
