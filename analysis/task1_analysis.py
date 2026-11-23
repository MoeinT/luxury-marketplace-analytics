#!/usr/bin/env python3
"""Reproduce the order GMV close-drift and event-history analysis from dbt seeds."""

import csv
import math
import statistics
from collections import defaultdict
from datetime import datetime
from decimal import Decimal
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "dbt" / "seeds"
CENT = Decimal("0.01")
OPERATIONAL_STATUSES = {
    "paid",
    "received_at_authentication",
    "authenticated",
    "shipped_to_buyer",
    "delivered",
    "completed",
}


def read_csv(name):
    with (DATA / name).open(newline="", encoding="utf-8-sig") as file:
        return list(csv.DictReader(file))


def money(value):
    return Decimal(value).quantize(CENT)


def pct(numerator, denominator):
    return (numerator / denominator * 100) if denominator else Decimal(0)


def quantile(values, fraction):
    return sorted(values)[max(0, math.ceil(fraction * len(values)) - 1)]


def main():
    order_rows = read_csv("orders.csv")
    event_rows = read_csv("order_status_events.csv")
    item_rows = read_csv("items.csv")
    fx_rows = read_csv("fx_rates.csv")
    finance_rows = read_csv("finance_monthly_gmv.csv")

    fx_rates = {
        (rate["rate_date"], rate["currency"]): Decimal(rate["rate_to_eur"])
        for rate in fx_rows
    }
    orders = {}
    for row in order_rows:
        row["created_dt"] = datetime.fromisoformat(row["created_at"])
        row["updated_dt"] = datetime.fromisoformat(row["updated_at"])
        row["month"] = row["created_at"][:7]
        row["item_price_eur"] = (
            Decimal(row["item_price"])
            * fx_rates[(row["created_at"][:10], row["currency"])]
        )
        orders[row["order_id"]] = row

    # event_id is the logical key; keep its first observed copy for replay.
    by_event_id = defaultdict(list)
    for row in event_rows:
        by_event_id[row["event_id"]].append(row)

    event_payload_conflicts = sum(
        len({(row["order_id"], row["status"], row["event_ts"]) for row in copies}) > 1
        for copies in by_event_id.values()
    )
    events = []
    for copies in by_event_id.values():
        event = min(copies, key=lambda row: row["ingested_at"]).copy()
        event["event_dt"] = datetime.fromisoformat(event["event_ts"])
        event["ingested_dt"] = datetime.fromisoformat(event["ingested_at"])
        events.append(event)

    events_by_order = defaultdict(list)
    for event in events:
        events_by_order[event["order_id"]].append(event)
    for history in events_by_order.values():
        history.sort(key=lambda event: (event["event_dt"], event["event_id"]))

    print("TASK 1 — DATA QUALITY")
    print(
        f"orders: {len(order_rows):,} rows, "
        f"{len(orders):,} distinct order_id"
    )
    item_ids = {row["item_id"] for row in item_rows}
    print(
        f"items: {len(item_rows):,} rows, {len(item_ids):,} distinct item_id; "
        f"orders with an unmatched item_id: "
        f"{sum(row['item_id'] not in item_ids for row in order_rows):,}"
    )
    fx_keys = [(row["rate_date"], row["currency"]) for row in fx_rows]
    print(
        f"FX: {len(fx_rows):,} rows, {len(set(fx_keys)):,} distinct "
        f"(rate_date, currency); orders missing an order-date FX rate: "
        f"{sum((row['created_at'][:10], row['currency']) not in fx_rates for row in order_rows):,}"
    )
    print(
        f"events: {len(event_rows):,} rows, {len(events):,} distinct event_id; "
        f"{len(event_rows) - len(events):,} duplicate deliveries, "
        f"{event_payload_conflicts} conflicting event_id payloads"
    )
    event_order_ids = set(events_by_order)
    print(
        f"event order coverage: {len(event_order_ids):,}/{len(orders):,} "
        f"({pct(Decimal(len(event_order_ids)), Decimal(len(orders))):.2f}%); "
        f"{len(orders) - len(event_order_ids):,} orders have no events"
    )
    mismatched = [
        order_id
        for order_id, history in events_by_order.items()
        if history[-1]["status"] != orders[order_id]["status"]
    ]
    stale = [
        order_id
        for order_id, history in events_by_order.items()
        if history[-1]["event_dt"] < orders[order_id]["updated_dt"]
    ]
    print(
        f"latest event vs orders snapshot: {len(mismatched):,} status mismatches "
        f"of {len(event_order_ids):,}; latest event predates updated_at for "
        f"{len(stale):,} orders"
    )

    ingestion_regressions = 0
    adjacent_pairs = 0
    for history in events_by_order.values():
        arrival_order = sorted(
            history, key=lambda event: (event["ingested_dt"], event["event_id"])
        )
        for earlier, later in zip(arrival_order, arrival_order[1:]):
            adjacent_pairs += 1
            ingestion_regressions += earlier["event_dt"] > later["event_dt"]
    print(
        f"event ordering: {ingestion_regressions:,}/{adjacent_pairs:,} adjacent "
        "ingestion-order pairs regress in event time"
    )

    first_arrival_lags = [
        (event["ingested_dt"] - event["event_dt"]).total_seconds() / 60
        for event in events
    ]
    print(
        "first-arrival lag (deduplicated events, minutes): "
        f"median={statistics.median(first_arrival_lags):.2f}, "
        f"p95={quantile(first_arrival_lags, 0.95):.2f}, "
        f"negative={sum(lag < 0 for lag in first_arrival_lags):,}, "
        f">24h={sum(lag > 1440 for lag in first_arrival_lags):,}"
    )

    print("\nTASK 1 — FINANCE CLOSE REPLAY")
    print(
        "Amounts are item_price only, translated at the order-date FX rate. "
        "This matches the existing model's GMV basis (shipping excluded)."
    )
    print(
        "Operational net includes paid through completed states and excludes "
        "placed, cancelled, authentication-rejected, and returned orders."
    )
    print(
        "Close status is event-time replay; current status is used only when "
        "orders.updated_at is after close. Earlier replay conflicts are reported "
        "separately."
    )
    header = (
        "month close  known/cohort  finance_eur  legacy_at_close  "
        "legacy_postclose  legacy_delta  legacy_delta_pct  "
        "net_delta  finance_vs_close"
    )
    print(header)

    net_transition_totals = defaultdict(lambda: [0, Decimal(0), []])
    legacy_transition_totals = defaultdict(lambda: [0, Decimal(0), []])
    net_snapshot_transitions = defaultdict(lambda: [0, Decimal(0), []])
    legacy_snapshot_transitions = defaultdict(lambda: [0, Decimal(0), []])
    close_replay_conflicts = {
        "legacy": [0, Decimal(0)],
        "operational_net": [0, Decimal(0)],
    }

    for finance in finance_rows:
        month = finance["month"]
        close = datetime.fromisoformat(finance["closed_on"] + " 23:59:59")
        cohort = [order for order in orders.values() if order["month"] == month]
        known_at_close = []
        for order in cohort:
            history = events_by_order.get(order["order_id"], [])
            at_close = [
                event for event in history if event["event_dt"] <= close
            ]
            if at_close:
                known_at_close.append((order, at_close[-1]["status"], history))

        # Existing logic: item GMV for every status except cancelled.
        legacy_included = lambda status: status is not None and status != "cancelled"
        # Operational net: paid/fulfilled value less any cancellation/refund.
        net_included = lambda status: status in OPERATIONAL_STATUSES
        reliable_month = bool(cohort) and len(known_at_close) / len(cohort) >= 0.9

        def endpoint_status(order, close_status):
            # updated_at marks the last backend status change; do not call an
            # event/snapshot disagreement from before close post-close drift.
            return (
                order["status"]
                if order["updated_dt"] > close
                else close_status
            )

        legacy_close = sum(
            (order["item_price_eur"] for order, status, _ in known_at_close if legacy_included(status)),
            Decimal(0),
        )
        legacy_now = sum(
            (
                order["item_price_eur"]
                for order, close_status, _ in known_at_close
                if legacy_included(endpoint_status(order, close_status))
            ),
            Decimal(0),
        )
        net_close = sum(
            (order["item_price_eur"] for order, status, _ in known_at_close if net_included(status)),
            Decimal(0),
        )
        net_now = sum(
            (
                order["item_price_eur"]
                for order, close_status, _ in known_at_close
                if net_included(endpoint_status(order, close_status))
            ),
            Decimal(0),
        )
        reported = Decimal(finance["gmv_eur"])
        count_label = f"{len(known_at_close)}/{len(cohort)}"
        print(
            f"{month} {finance['closed_on']} {count_label:>12} "
            f"{money(reported):>12} {money(legacy_close):>15} "
            f"{money(legacy_now):>11} {money(legacy_now-legacy_close):>12} "
            f"{pct(legacy_now-legacy_close, legacy_close):>16.2f}% "
            f"{money(net_now-net_close):>9} "
            f"{money(reported-legacy_close):>16}"
        )

        for order, status_at_close, history in known_at_close:
            if not reliable_month:
                continue

            current_status = order["status"]
            status_eligible_at_close = (
                legacy_included(status_at_close),
                net_included(status_at_close),
            )
            status_eligible_current = (
                legacy_included(current_status),
                net_included(current_status),
            )
            metrics = (
                ("legacy", legacy_included, legacy_snapshot_transitions),
                ("operational_net", net_included, net_snapshot_transitions),
            )
            for index, (metric, include, transitions) in enumerate(metrics):
                if status_eligible_at_close[index] == status_eligible_current[index]:
                    continue
                impact = order["item_price_eur"] * (
                    int(status_eligible_current[index])
                    - int(status_eligible_at_close[index])
                )
                if order["updated_dt"] <= close:
                    close_replay_conflicts[metric][0] += 1
                    close_replay_conflicts[metric][1] += impact
                else:
                    key = (status_at_close, current_status)
                    transitions[key][0] += 1
                    transitions[key][1] += impact
                    transitions[key][2].append(
                        (order["updated_dt"] - order["created_dt"]).total_seconds()
                        / 86400
                    )

            previous = status_at_close
            for event in (event for event in history if event["event_dt"] > close):
                current = event["status"]
                if current != previous:
                    age = (
                        event["event_dt"] - order["created_dt"]
                    ).total_seconds() / 86400
                    if legacy_included(previous) != legacy_included(current):
                        key = (previous, current)
                        legacy_transition_totals[key][0] += 1
                        legacy_transition_totals[key][1] += order["item_price_eur"] * (
                            int(legacy_included(current))
                            - int(legacy_included(previous))
                        )
                        legacy_transition_totals[key][2].append(age)
                    if net_included(previous) != net_included(current):
                        key = (previous, current)
                        net_transition_totals[key][0] += 1
                        net_transition_totals[key][1] += order["item_price_eur"] * (
                            int(net_included(current)) - int(net_included(previous))
                        )
                        net_transition_totals[key][2].append(age)
                previous = current

    comparable_months = [
        finance["month"]
        for finance in finance_rows
        if sum(
            1
            for order in orders.values()
            if order["month"] == finance["month"]
            and any(
                event["event_dt"]
                <= datetime.fromisoformat(finance["closed_on"] + " 23:59:59")
                for event in events_by_order.get(order["order_id"], [])
            )
        )
        / sum(1 for order in orders.values() if order["month"] == finance["month"])
        >= 0.9
    ]
    if comparable_months:
        close_amounts = []
        deltas = []
        for finance in finance_rows:
            month = finance["month"]
            if month not in comparable_months:
                continue
            close = datetime.fromisoformat(finance["closed_on"] + " 23:59:59")
            value_at_close = Decimal(0)
            for order in orders.values():
                if order["month"] != month:
                    continue
                history = events_by_order.get(order["order_id"], [])
                at_close = [event for event in history if event["event_dt"] <= close]
                if not at_close:
                    continue
                close_status = at_close[-1]["status"]
                if close_status != "cancelled":
                    value_at_close += order["item_price_eur"]
            value_now = Decimal(0)
            for order in orders.values():
                if order["month"] != month:
                    continue
                history = events_by_order.get(order["order_id"], [])
                at_close = [event for event in history if event["event_dt"] <= close]
                if at_close and endpoint_status(order, at_close[-1]["status"]) != "cancelled":
                    value_now += order["item_price_eur"]
            close_amounts.append(value_at_close)
            deltas.append(value_now - value_at_close)
        total_close = sum(close_amounts, Decimal(0))
        total_delta = sum(deltas, Decimal(0))
        print(
            f"\nHeadline (>=90% event-time coverage, {len(comparable_months)} months): "
            f"close-to-current legacy GMV change {money(total_delta)} EUR "
            f"on {money(total_close)} EUR ({pct(total_delta, total_close):.2f}%)."
        )

    def print_transitions(title, transitions):
        print(f"\n{title}")
        print("from -> to | orders | GMV impact EUR | median days from order | p90 days")
        for (previous, current), (count, impact, ages) in sorted(
            transitions.items(), key=lambda entry: (abs(entry[1][1]), entry[0]), reverse=True
        ):
            print(
                f"{previous} -> {current} | {count} | {money(impact)} | "
                f"{statistics.median(ages):.1f} | {quantile(ages, 0.9):.1f}"
            )

    print(
        "Pooled endpoint transitions include only months with >=90% event-time "
        "coverage; updated_at is the final order-status update timestamp."
    )
    print_transitions(
        "Post-close close-state -> current orders.csv transitions for legacy GMV",
        legacy_snapshot_transitions,
    )
    print_transitions(
        "Post-close close-state -> current orders.csv transitions for operational net",
        net_snapshot_transitions,
    )
    print(
        "\nEligibility mismatches with updated_at on/before close (excluded from "
        "post-close movement): "
        f"legacy={close_replay_conflicts['legacy'][0]} "
        f"({money(close_replay_conflicts['legacy'][1])} EUR); "
        f"operational_net={close_replay_conflicts['operational_net'][0]} "
        f"({money(close_replay_conflicts['operational_net'][1])} EUR)."
    )
    print(
        "\nEvent-sequence transitions after close (incomplete feed; these "
        "transitions need not reconcile to the current snapshot):"
    )
    print_transitions(
        "Recorded event changes that move the existing <> cancelled metric",
        legacy_transition_totals,
    )
    print_transitions(
        "Recorded event changes that move refund-adjusted operational net GMV",
        net_transition_totals,
    )

    print(
        "\nInterpretation: the close replay uses event time and the rows available "
        "in this extract. It cannot prove a complete historical close: orders "
        "without a pre-close event are excluded from the replay, status changes "
        "whose updated_at is on/before close but disagree with event state are "
        "reported separately, and late event ingestion means this is not "
        "necessarily what was visible to Finance on close day. The Finance CSV "
        "remains the immutable reported value."
    )


if __name__ == "__main__":
    main()
