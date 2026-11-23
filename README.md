# Luxury marketplace analytics — home assignment

This repository contains the reproducible analysis, a local PostgreSQL/dbt
project, the presentation, and an AI-use disclosure. The supplied assignment
data is synthetic. No employer or personal data is used.

## Run locally

**Requirements:** Docker with Compose and Python 3. Run all commands below
from the repository root. Docker downloads PostgreSQL 16, CloudBeaver, and
the dbt image on the first run; dbt itself does not need to be installed on
your laptop.

### 1. Configure and start

Create a local database password in `.env`, then start the services:

```sh
python3 -c 'from pathlib import Path; import secrets; p=Path(".env"); p.write_text("POSTGRES_PASSWORD="+secrets.token_urlsafe(24)+"\n") if not p.exists() else None; p.chmod(0o600)'
docker compose --env-file .env up --build -d
```

`.env` is ignored by Git; keep it private. The command does not overwrite an
existing file. Keep the same password when reusing the database volume:
changing `.env` alone does not change the password already stored in
PostgreSQL.

The `postgres` and `pgadmin` services stay running. The service named
`pgadmin` actually runs **CloudBeaver**, a browser-based SQL client. `dbt` is
a one-shot service: it waits for PostgreSQL, runs `dbt build`, and exits.
That build loads the CSV seeds, creates models and the snapshot, and runs
data tests. Allow time for the first image download and build.

Check progress and the final dbt result:

```sh
docker compose --env-file .env ps -a
docker compose --env-file .env logs --tail=80 dbt
docker compose --env-file .env exec postgres pg_isready -U dbt -d luxury_analytics
```

PostgreSQL should be healthy and dbt should finish with exit code 0; check
the dbt log for its build and test summary. If needed, inspect service logs
with `docker compose --env-file .env logs --tail=80 postgres pgadmin`.

### 2. Explore the database

Open [http://localhost:8080](http://localhost:8080) for CloudBeaver. On first
use, complete the setup screen with a server name of your choice, allowed
server URL `http://localhost:8080`, and the default session lifetime. Then
create a **PostgreSQL** connection:

| Field | Value |
|---|---|
| Host | `postgres` |
| Port | `5432` |
| Database | `luxury_analytics` |
| Username | `dbt` |
| Password | `POSTGRES_PASSWORD` from your local `.env` |

Use `postgres`, not `localhost`, as the host **inside CloudBeaver**. Test
and save the connection, open a new SQL script, and run:

```sql
SELECT * FROM marts.fct_orders LIMIT 10;
SELECT * FROM marts.mart_finance_monthly_gmv ORDER BY month_start;
```

The schemas include `raw`, `staging`, `intermediate`, `marts`, and `history`.
CloudBeaver's own configuration is stored in its container and may need to be
set up again if the container is recreated. In a remote VS Code environment,
open forwarded port 8080 instead of your laptop's localhost and use the
forwarded address in CloudBeaver's allowed server URLs.

For terminal access instead, connect with `psql`:

```sh
docker compose --env-file .env exec postgres psql -U dbt -d luxury_analytics
```

Within `psql`, use `\dn` to list schemas, `\dt marts.*` to list mart tables,
and `\q` to exit. To open a shell in the PostgreSQL container instead, run
`docker compose --env-file .env exec postgres sh` and type `exit` when done.
From a host database client, use `127.0.0.1:54329`, database
`luxury_analytics`, user `dbt`, and the same password.

### 3. Develop and rerun

The SQL models and their per-model YAML documentation and generic tests are
in [`dbt/models/`](dbt/models/); singular SQL data tests are in
[`dbt/tests/`](dbt/tests/). The input CSVs are in [`dbt/seeds/`](dbt/seeds/).
The reproducible analysis reads those same files:

```sh
python3 analysis/task1_analysis.py
```

Run dbt again, or select a specific model:

```sh
# Full build: seeds, models, snapshots, and tests
docker compose --env-file .env run --rm dbt build --profiles-dir .

# Build one model and its selected tests; upstream relations must already exist
docker compose --env-file .env run --rm dbt build --select dim_buyers --profiles-dir .

# Include upstream dependencies, or run the data tests alone
docker compose --env-file .env run --rm dbt build --select +dim_buyers --profiles-dir .
docker compose --env-file .env run --rm dbt test --profiles-dir .
```

One-off `run --rm` commands print their logs directly in the terminal and
remove their temporary container. Detailed dbt logs are also written to
`dbt/logs/dbt.log`, and manifest and run results to `dbt/target/`.
The Finance model is append-only during incremental builds: avoid
`--full-refresh` against a production close table because it rebuilds frozen
values from the source.

### 4. Stop the services

```sh
docker compose --env-file .env down
```

This preserves the named PostgreSQL data volume for the next run.

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

The original chain of `ref()` dependencies is `fct_orders -> int_order_risk
-> dim_buyers -> fct_orders`: the fact needs the risk and buyer models, risk
needs the buyer model, and the buyer model aggregates the fact. dbt must
compile a directed acyclic graph to determine build order, so it rejects this
genuine cycle.
Replacing `ref('fct_orders')` with `analytics.marts.fct_orders` only hides the
edge from dbt. It removes dependency ordering, lineage, environment/schema
resolution, and reliable selection/build behavior; stale or missing tables can
then produce a green-looking build with incorrect results.

The graphs below focus on the cycle-related models. Here each arrow points
from an upstream model to a downstream consumer.

**Before: cyclic graph (not a DAG)**

```text
stg_orders     -> fct_orders, int_order_risk
fct_orders     -> dim_buyers
dim_buyers     -> fct_orders, int_order_risk
int_order_risk -> fct_orders
```

**After: acyclic graph**

```text
stg_orders, stg_items, stg_fx_rates -> int_orders_enriched
int_orders_enriched -> int_buyer_order_features, dim_buyers, fct_orders
int_buyer_order_features -> int_order_risk, fct_orders
dim_buyers, int_order_risk -> fct_orders
fct_orders -> mart_ops_daily_gmv
```

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
with a two-minute cycle section, diagrams, options, costs, and decision-changing
evidence. The diagrams there use Mermaid; the text graphs above work in any
Markdown viewer. [`AI_USAGE.md`](AI_USAGE.md) is the AI-use disclosure.
