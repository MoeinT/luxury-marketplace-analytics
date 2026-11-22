select
    order_id,
    buyer_id,
    is_first_order,
    gmv_eur,
    is_first_order and gmv_eur > 1000 as is_high_risk
from {{ ref("int_buyer_order_features") }}
