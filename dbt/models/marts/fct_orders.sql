select
    o.order_id,
    o.buyer_id,
    o.seller_id,
    o.item_id,
    o.created_at,
    o.updated_at,
    o.status,
    o.category,
    o.brand,
    o.buyer_country,
    o.currency,
    o.item_price,
    o.shipping_fee,
    o.gmv_eur,
    o.shipping_fee_eur,
    f.buyer_segment_at_order as buyer_segment,
    b.buyer_segment_current,
    r.is_high_risk,
    case
        when o.status in (
            'paid',
            'received_at_authentication',
            'authenticated',
            'shipped_to_buyer',
            'delivered',
            'completed'
        ) then o.gmv_eur
        else 0
    end::numeric(16, 2) as net_gmv_eur_operational
from {{ ref("int_orders_enriched") }} as o
left join {{ ref("int_buyer_order_features") }} as f
    on o.order_id = f.order_id
left join {{ ref("dim_buyers") }} as b
    on o.buyer_id = b.buyer_id
left join {{ ref("int_order_risk") }} as r
    on o.order_id = r.order_id
