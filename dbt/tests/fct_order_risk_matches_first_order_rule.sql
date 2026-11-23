select
    fact.order_id,
    fact.is_high_risk,
    features.is_first_order,
    features.gmv_eur
from {{ ref("fct_orders") }} as fact
join {{ ref("int_buyer_order_features") }} as features
    on fact.order_id = features.order_id
where fact.is_high_risk is distinct from (
    features.is_first_order and features.gmv_eur > 1000
)
