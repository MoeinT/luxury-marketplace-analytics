select event_id
from {{ ref("order_status_events") }}
group by event_id
having count(
    distinct (order_id, status, event_ts)
) > 1
