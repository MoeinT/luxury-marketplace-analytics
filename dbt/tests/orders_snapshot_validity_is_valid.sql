select order_id
from {{ ref("orders_snapshot") }}
where dbt_valid_from is null
   or (dbt_valid_to is not null and dbt_valid_to <= dbt_valid_from)
