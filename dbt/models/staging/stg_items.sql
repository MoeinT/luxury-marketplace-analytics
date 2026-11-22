select
    trim(item_id)::text as item_id,
    lower(trim(category))::text as category,
    trim(brand)::text as brand
from {{ ref("items") }}
