select dbt_scd_id
from {{ ref("orders_snapshot") }}
group by dbt_scd_id
having count(*) > 1
