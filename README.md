# Luxury marketplace analytics — home assignment

This repository contains the reproducible analysis, a local PostgreSQL/dbt
project, the presentation, and an AI-use disclosure. The supplied assignment
data is synthetic. No employer or personal data is used.

## Run locally

Requirements: Docker with Compose. The dbt runner uses `dbt-core==1.10.0` and
`dbt-postgres==1.9.0`;
PostgreSQL runs in `postgres:16`.

From the repository root, create a local-only password file (already ignored
by Git). Then run the dbt workflow from `dbt/`:

```sh
python -c 'from pathlib import Path; import secrets; p=Path(".env"); p.write_text("POSTGRES_PASSWORD="+secrets.token_urlsafe(24)+"\n") if not p.exists() else None; p.chmod(0o600)'
cd dbt
docker compose -f ../docker-compose.yml --env-file ../.env up -d postgres
docker compose -f ../docker-compose.yml --env-file ../.env run --rm dbt
python ../analysis/task1_analysis.py
```

`dbt build` loads the five CSVs as seeds, creates the models, captures the
`orders_snapshot`, and runs data tests. The first run may take about a minute
while Docker downloads images and loads the event seed. The dbt project and
`profiles.yml` are in this directory; the seed files remain in `../data`.
`profiles.yml` reads credentials from environment variables; no database
password is committed.
The host database is available on `127.0.0.1:54329`.

Useful commands:

```sh
docker compose -f ../docker-compose.yml --env-file ../.env run --rm dbt test --profiles-dir .
docker compose -f ../docker-compose.yml --env-file ../.env exec -T postgres psql -U dbt -d luxury_analytics -P pager=off
docker compose -f ../docker-compose.yml --env-file ../.env down
```

`docker compose down` stops the service but preserves its named data volume.
The monthly Finance model is deliberately append-only; do not use
`--full-refresh` against a production close table.

## Task 1 — findings

Run [`analysis/task1_analysis.py`](analysis/task1_analysis.py) to reproduce the
numbers below. It uses standard-library Python, the supplied CSVs, order-date
FX, item price only (shipping excluded), and event-time replay. `orders.csv`
contains the current overwritten status; it cannot by itself reconstruct a
past close.

| Order month | Finance close | Orders with event state at close | Finance reported (€) | Event replay at close (€) | Replay at extract (€) | Movement after close (€) |
|---|---:|---:|---:|---:|---:|---:|
| 2026-04 | 2026-05-05 | 743 / 1,795 (41.4%) | 1,043,232.77 | 464,686.08 | 464,410.72 | -275.36 |
| 2026-05 | 2026-06-03 | 1,973 / 1,973 | 1,180,371.43 | 1,180,677.43 | 1,153,269.86 | -27,407.57 (-2.32%) |
| 2026-06 | 2026-07-03 | 1,993 / 1,993 | 1,147,103.37 | 1,149,591.50 | 1,126,683.14 | -22,908.35 (-1.99%) |
| 2026-07 | 2026-08-05 | 2,238 / 2,240 | 1,291,383.63 | 1,297,371.96 | 1,282,670.59 | -14,701.38 (-1.13%) |
| 2026-08 | 2026-09-03 | 2,304 / 2,304 | 1,349,137.69 | 1,353,472.28 | 1,321,458.79 | -32,013.49 (-2.37%) |
| 2026-09 | 2026-10-05 | 2,440 / 2,440 | 1,461,897.81 | 1,467,154.81 | 1,443,930.20 | -23,224.62 (-1.58%) |

For the five months with at least 90% event-time coverage, the existing
`item_price` / `status <> 'cancelled'` logic falls by **€120,255.40 (1.86%)**
after close, or about **€24.1k per month**. Close status is replayed from
events; the endpoint uses `orders.csv` only for statuses whose `updated_at` is
after close. Thirty-six status/GMV conflicts whose `updated_at` is on or before
close are reported separately, not misattributed to post-close drift. The April
replay is not representative because only 41.4% of its orders had an event by
close; July is missing two orders at close. The event replay is an estimate
from the later extract, not a claim about exactly what Finance could see on
close day.

The close-to-current transitions that change the existing metric are
`paid -> cancelled` (127 orders, -€79,736.67; median 27.0 days after order),
`received_at_authentication -> cancelled` (43, -€38,590.33; median 24.9 days),
and `placed -> cancelled` (3, -€1,928.40; median 20.8 days). These are
endpoint transitions from close status to current status; the event table
records a different set because it is incomplete. In the well-covered months,
254 event-sequence `delivered -> returned` transitions occur a median 18.3 days
after order and 8.4 days after delivery; all are within the 14-day return
window. Authentication rejections also remove operational net value.

The event feed cannot be treated as a complete order history:

* 71,545 event rows collapse to 70,499 event IDs (1,046 duplicate deliveries;
  no conflicting event payloads in this extract).
* 12,152 / 12,745 orders have any event (95.35%); 593 have none.
* The last event status disagrees with `orders.csv` for 387 orders; for 2,236
  orders its timestamp is older than `orders.updated_at`.
* Among adjacent events ordered by ingestion time, 1,547 / 58,347 pairs move
  backwards in event time. Deduplicated first-arrival lag has a 3.1-minute
  median, 19.1-minute p95, 2,175 events over 24 hours, and 114 negative lags.

The FX file has unique daily currency keys and covers every order-date currency
lookup; order and item IDs are unique and all order item references resolve.
These checks do not make the event feed complete.

### Metric contracts

* **Operations — live net GMV:** EUR item price (shipping shown separately) for
  orders currently in `paid`, authentication, shipping, delivery, or completed
  states; exclude `placed`, `cancelled`, `rejected_at_authentication`, and
  `returned`. Recompute hourly from current order state, including today; label
  it provisional because refunds/cancellations can still arrive. Cancellation
  rate is current cancelled orders divided by all placed orders in the same
  order-date/category/country/at-order-segment cohort. Show authentication
  rejection and return counts separately.
* **Finance — board series:** preserve the Finance-reported monthly amount and
  close date as the authoritative published figure. The close value must not
  be recomputed from today's `orders.status`. The supplied figures are within
  0.03%–0.47% of the event replay of the legacy “item price, not cancelled”
  formula for May–September, but this alone does not establish whether Finance
  nets authentication rejections or returns. Confirm item-vs-shipping,
  recognition, FX, and return policy with the Controller before changing the
  label or historical values.

The recommended future Finance contract is item-price GMV in EUR, attributed
to the originating order month and frozen at the third-business-day close.
Statuses known at close are treated according to the Controller-approved
policy; a cancellation/refund discovered after close is an approved adjustment
in the current open month, carrying the original order and month as audit
dimensions. Do not restate a published month. Keep the existing Finance series
intact through a policy cutover rather than silently converting it to the
operational definition.

## Task 2 — dbt design

`raw` holds unchanged CSV seeds. Staging normalizes types without dropping
records; intermediate models add FX, buyer-order features, and risk; marts
serve current Operations and frozen Finance. The local CSVs are a reproducible
fixture, not an hourly ingestion system.

| Model | Grain / primary key | Materialization | Production refresh | Core tests |
|---|---|---|---|---|
| `stg_orders` | one current row/order; `order_id` | view | hourly | not-null, unique, accepted status, item relationship |
| `stg_order_status_events` | one deduplicated logical event; `event_id` | view | hourly / micro-batch | not-null, unique, order relationship, duplicate-payload consistency |
| `stg_items` | one item; `item_id` | view | daily or on item updates | not-null, unique |
| `stg_fx_rates` | one currency/day; `(rate_date, currency)` | view | daily | not-null, composite uniqueness |
| `stg_finance_monthly_gmv` | one closed month; `month_start` | view | monthly at close | not-null, unique |
| `int_orders_enriched` | one order; `order_id` | view | hourly | not-null, unique, valid FX and item joins |
| `int_buyer_order_features` | one order; `order_id` | view | hourly | not-null, unique, valid segment |
| `int_order_risk` | one order; `order_id` | view | hourly | not-null, unique, first-order threshold rule |
| `dim_buyers` | one current buyer; `buyer_id` | table | hourly | not-null, unique, segment domain |
| `fct_orders` | one current-state row/order; `order_id` | table | hourly | not-null, unique, segment-at-order and risk logic |
| `mart_ops_daily_gmv` | order date × category × country × segment-at-order | table | hourly, including today | non-null dimensions, composite-grain uniqueness |
| `mart_finance_monthly_gmv` | one published close/month; `month_start` | incremental append-only table | monthly, on close | not-null, unique |
| `orders_snapshot` | one order version; `dbt_scd_id` (validity interval per order) | dbt snapshot | hourly | unique snapshot ID; non-null, ordered validity interval |

**History decision — both, with clear roles.** The hourly dbt snapshot of
`stg_orders` captures observed versions and fills gaps in the event feed; it
cannot see two status changes between runs. Keep the append-only event feed for
event timestamps and transition forensics, but deduplicate by `event_id`, order
by `event_ts`, and monitor late arrival. Do not use it as the sole source of
current state until completeness and ordering meet a source contract. A
production CDC/event contract with replay and backfill is the target; snapshots
remain the safety net.

**Close decision — freeze, then adjust forward.** `mart_finance_monthly_gmv`
appends a month once and does not update that key on later builds. The actual
adjustment ledger is not present in the assignment files, so no synthetic
adjustments are invented here. In production, approved post-close changes are
separate current-period postings with original order/month, amount, reason,
approval, and posting month. Preserve the published close row.

**Currency and netting.** `gmv_eur` is item price only, rounded to cents using
the FX rate for the order-creation date; shipping is a separate field. The
operational net definition is the live paid-through-completed eligibility
above, less cancellation/authentication rejection/return. Finance's published
metric remains Finance-owned and must be reconciled to its ledger definition;
do not equate it to the operational estimate by name alone.

Source timestamps are retained as UTC-naive timestamps, as specified for
`created_at` in the assignment; consumers must not reinterpret them as local
time.

## Task 3 — cycle repair

The original chain is `fct_orders -> int_order_risk -> dim_buyers ->
fct_orders`: the fact needs the risk and buyer models, risk needs the buyer
model, and the buyer model aggregates the fact. dbt must compile a directed
acyclic graph to determine build order, so it rejects this genuine cycle.
Replacing `ref('fct_orders')` with `analytics.marts.fct_orders` only hides the
edge from dbt. It removes dependency ordering, lineage, environment/schema
resolution, and reliable selection/build behavior; stale or missing tables can
then produce a green-looking build with incorrect results.

The refactor computes prior-order attributes in
`int_buyer_order_features`, before the fact and dimensions. `dim_buyers` is a
current-state profile. `fct_orders.buyer_segment` is explicitly the segment at
that order: `new` if no prior order, `vip` if prior submitted order GMV is at
least €5,000, otherwise `returning`. This uses only prior orders and avoids
future leakage; it does not pretend current order statuses reconstruct prior
net GMV. `buyer_segment_current` is separate and belongs to the current buyer
dimension. `is_high_risk` is evaluated at order time: first order and
item-price GMV above €1,000.

`fct_buyer_segment_is_as_of_order` compares every fact segment to the
pre-fact feature. It would fail if the fact used the current
`dim_buyers.buyer_segment_current` for its historical `buyer_segment` (3,528
orders differ from today's segment in this sample); it passes on the refactor.
The risk-rule test independently verifies the threshold and first-order rule.

## Task 4 — presentation and AI note

See [`PRESENTATION.md`](PRESENTATION.md) for a 20-minute presentation outline
with a two-minute cycle section, DAGs, options, costs, and decision-changing
evidence. [`AI_USAGE.md`](AI_USAGE.md) is the AI-use disclosure.
