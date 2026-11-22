select
    trim(order_id)::text as order_id,
    trim(buyer_id)::text as buyer_id,
    trim(seller_id)::text as seller_id,
    trim(item_id)::text as item_id,
    created_at::timestamp as created_at,
    lower(trim(status))::text as status,
    updated_at::timestamp as updated_at,
    item_price::numeric(12, 2) as item_price,
    shipping_fee::numeric(12, 2) as shipping_fee,
    upper(trim(currency))::text as currency,
    upper(trim(buyer_country))::text as buyer_country
from {{ ref("orders") }}
