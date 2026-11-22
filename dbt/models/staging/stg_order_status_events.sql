with ranked_events as (
    select
        trim(event_id)::text as event_id,
        trim(order_id)::text as order_id,
        lower(trim(status))::text as status,
        event_ts::timestamp as event_ts,
        ingested_at::timestamp as ingested_at,
        row_number() over (
            partition by trim(event_id)
            order by ingested_at, order_id, event_ts, status
        ) as delivery_rank
    from {{ ref("order_status_events") }}
)

select
    event_id,
    order_id,
    status,
    event_ts,
    ingested_at
from ranked_events
where delivery_rank = 1
