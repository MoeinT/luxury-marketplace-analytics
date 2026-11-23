{% snapshot orders_snapshot %}

{{
    config(
        target_schema="history",
        unique_key="order_id",
        strategy="timestamp",
        updated_at="updated_at",
        invalidate_hard_deletes=True
    )
}}

select
    order_id,
    buyer_id,
    seller_id,
    item_id,
    created_at,
    status,
    updated_at,
    item_price,
    shipping_fee,
    currency,
    buyer_country
from {{ ref("stg_orders") }}

{% endsnapshot %}
