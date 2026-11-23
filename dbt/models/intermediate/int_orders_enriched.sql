select
    o.order_id,
    o.buyer_id,
    o.seller_id,
    o.item_id,
    o.created_at,
    o.status,
    o.updated_at,
    o.item_price,
    o.shipping_fee,
    o.currency,
    o.buyer_country,
    i.category,
    i.brand,
    fx.rate_to_eur,
    round(o.item_price * fx.rate_to_eur, 2)::numeric(16, 2) as gmv_eur,
    round(o.shipping_fee * fx.rate_to_eur, 2)::numeric(16, 2)
        as shipping_fee_eur
from {{ ref("stg_orders") }} as o
left join {{ ref("stg_items") }} as i
    on o.item_id = i.item_id
left join {{ ref("stg_fx_rates") }} as fx
    on o.created_at::date = fx.rate_date
    and o.currency = fx.currency
