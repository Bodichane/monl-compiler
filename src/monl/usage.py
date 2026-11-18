"""An honest reading of the AI providers' consumption log.

Prices do not live in monl: the operator supplies them. This module
therefore only checks the table's shape, aggregates the events and
computes costs when the price and the required counters are present.
Images are billed per request and deliberately have no token counter."""

import json
import math
import os
from decimal import Decimal, InvalidOperation

USAGE_FILENAME = ".monl_ai_usage.jsonl"
PRICES_ENVIRONMENT = "MONL_USAGE_PRICES"


class UsagePriceError(ValueError):
    """Price table missing or unusable."""


def _decimal(value, label):
    if isinstance(value, bool) or value is None:
        raise UsagePriceError(f"invalid rate for {label}")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise UsagePriceError(f"invalid rate for {label}") from exc
    if not result.is_finite() or result < 0:
        raise UsagePriceError(f"invalid rate for {label}")
    return result


def _tarif_du_modele(provider, model, rates):
    """One model's rates, checked then converted. Extracted from
    `_load_prices` (complexity ceiling); same checks, same messages."""
    if not isinstance(model, str) or not isinstance(rates, dict):
        raise UsagePriceError("each model must contain a rate object")
    input_rate = rates.get("input_per_million_tokens")
    output_rate = rates.get("output_per_million_tokens")
    request_rate = rates.get("per_request")
    if ((input_rate is None or output_rate is None)
            and request_rate is None):
        raise UsagePriceError(
            f"incomplete rates for {provider}/{model}: "
            "declare both token rates or per_request")
    return {
        "input": (_decimal(input_rate, f"{provider}/{model} input")
                  if input_rate is not None else None),
        "output": (_decimal(output_rate, f"{provider}/{model} output")
                   if output_rate is not None else None),
        "request": (_decimal(request_rate, f"{provider}/{model} per_request")
                    if request_rate is not None else None),
    }


def _load_prices(path):
    if not path:
        return {"currency": None, "prices": {}, "path": None}
    try:
        with open(path, encoding="utf-8") as fh:
            document = json.load(fh)
    except OSError as exc:
        raise UsagePriceError(f"price table is unreadable: {path} — {exc}") from exc
    except json.JSONDecodeError as exc:
        raise UsagePriceError(f"price table contains invalid JSON: {path}") from exc

    if not isinstance(document, dict):
        raise UsagePriceError("price table must be a JSON object")
    currency = document.get("currency")
    if currency is not None and (not isinstance(currency, str) or not currency.strip()):
        raise UsagePriceError("currency must be a non-empty string")
    declared = document.get("prices", document)
    if not isinstance(declared, dict):
        raise UsagePriceError("prices must be a provider-to-model object")

    prices = {}
    for provider, models in declared.items():
        if provider == "currency":
            continue
        if not isinstance(provider, str) or not isinstance(models, dict):
            raise UsagePriceError("each provider must contain a model object")
        prices[provider] = {}
        for model, rates in models.items():
            prices[provider][model] = _tarif_du_modele(provider, model, rates)
    return {"currency": currency.strip() if isinstance(currency, str) else None,
            "prices": prices, "path": os.path.abspath(path)}


def _json_number(value):
    if value is None:
        return None
    if isinstance(value, Decimal):
        return float(value)
    return value


def _counter(event, name):
    value = event.get(name)
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value >= 0 else None
    if isinstance(value, float) and math.isfinite(value) and value >= 0:
        return value
    return None


def _sum_counter(events, name):
    values = [_counter(event, name) for event in events]
    present = [value for value in values if value is not None]
    if not present:
        return (0, True) if not events else (None, False)
    return sum(present), len(present) == len(events)


def _token_events(events):
    return [event for event in events if event.get("billing_unit") != "request"]


def _request_events(events):
    return [event for event in events if event.get("billing_unit") == "request"]


def _unique(values):
    return list(dict.fromkeys(value for value in values if value is not None))


def _price_label(provider, model):
    return f"{provider or 'unknown provider'}/{model or 'unknown model'}"


def _cout_d_un_evenement(event, price_table):
    """(cost, missing price label or None, missing counter) of an event.
    Extracted from `_aggregate` (complexity ceiling): an event without a price
    or without a counter costs zero and SAYS so, never silently."""
    provider = event.get("provider")
    model = event.get("model")
    rates = price_table["prices"].get(provider, {}).get(model)
    if rates is None:
        return Decimal("0"), _price_label(provider, model), False
    if event.get("billing_unit") == "request":
        request_value = _counter(event, "requests")
        if rates.get("request") is None:
            return Decimal("0"), _price_label(provider, model), False
        if request_value is None:
            return Decimal("0"), None, True
        return Decimal(str(request_value)) * rates["request"], None, False
    input_value = _counter(event, "input_tokens")
    output_value = _counter(event, "output_tokens")
    if (input_value is None or output_value is None
            or rates.get("input") is None or rates.get("output") is None):
        return Decimal("0"), None, True
    return (
        Decimal(str(input_value)) * rates["input"] / Decimal("1000000")
        + Decimal(str(output_value)) * rates["output"] / Decimal("1000000")
    ), None, False


def _aggregate(events, price_table):
    token_events = _token_events(events)
    request_events = _request_events(events)
    if token_events:
        input_tokens, input_complete = _sum_counter(token_events, "input_tokens")
        output_tokens, output_complete = _sum_counter(token_events, "output_tokens")
    else:
        input_tokens, input_complete = None, True
        output_tokens, output_complete = None, True
    if request_events:
        requests, requests_complete = _sum_counter(request_events, "requests")
    else:
        requests, requests_complete = None, True
    duration, duration_complete = _sum_counter(events, "duration_seconds")
    total_tokens = (input_tokens + output_tokens
                    if input_tokens is not None and output_tokens is not None else None)

    priced_cost = Decimal("0")
    missing_prices = []
    missing_counters = False
    for event in events:
        cout, prix_absent, compteur_absent = _cout_d_un_evenement(event, price_table)
        priced_cost += cout
        if prix_absent is not None:
            missing_prices.append(prix_absent)
        missing_counters = missing_counters or compteur_absent

    if not events:
        cost = Decimal("0")
        price_status = "no_usage"
    elif missing_prices:
        cost = None
        price_status = "not_declared"
    elif missing_counters or not input_complete or not output_complete:
        cost = None
        price_status = "counters_unavailable"
    else:
        cost = priced_cost
        price_status = "declared"

    return {
        "event_count": len(events),
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
        "requests": requests,
        "requests_complete": requests_complete,
        "duration_seconds": (round(duration, 3) if duration is not None else None),
        "duration_complete": duration_complete,
        "cost": _json_number(cost),
        "price_status": price_status,
        "unpriced_models": sorted(set(missing_prices)),
        "missing_counters": sorted({
            name for name, complete in (("input_tokens", input_complete),
                                        ("output_tokens", output_complete))
            if not complete
        }),
    }


def _execution(run_id, events, price_table):
    operations = _unique(event.get("operation") for event in events)
    attempts = sorted({event.get("attempt") for event in events
                       if isinstance(event.get("attempt"), int)})
    stages = _unique(event.get("stage") for event in events)
    stage_counts = {stage: sum(event.get("stage") == stage for event in events)
                    for stage in stages}
    aggregate = _aggregate(events, price_table)
    aggregate.update({
        "run_id": run_id,
        "known": run_id is not None,
        "label": "execution" if run_id is not None else "unknown execution",
        "operation": operations[0] if len(operations) == 1 else "multiple",
        "operations": operations,
        "attempts": attempts,
        "attempt_count": len(attempts),
        "stages": stages,
        "stage_counts": stage_counts,
    })
    return aggregate


def build_usage_report(project_dir, prices_path=None):
    """Builds a JSON-serializable report without grouping by intuition."""
    resolved_prices = prices_path or os.environ.get(PRICES_ENVIRONMENT)
    price_table = _load_prices(resolved_prices)
    journal_path = os.path.join(project_dir, USAGE_FILENAME)
    malformed_lines = []
    events = []
    journal_exists = os.path.exists(journal_path)
    if journal_exists:
        try:
            with open(journal_path, encoding="utf-8") as fh:
                for line_number, line in enumerate(fh, 1):
                    if not line.strip():
                        malformed_lines.append({"line": line_number, "error": "empty line"})
                        continue
                    try:
                        event = json.loads(line)
                    except json.JSONDecodeError:
                        malformed_lines.append({"line": line_number, "error": "invalid JSON"})
                        continue
                    if not isinstance(event, dict):
                        malformed_lines.append({
                            "line": line_number, "error": "expected a JSON object",
                        })
                        continue
                    events.append(event)
        except OSError as exc:
            raise UsagePriceError(f"usage journal is unreadable: {journal_path} — {exc}") from exc

    groups = {}
    for event in events:
        run_id = event.get("run_id")
        if not isinstance(run_id, str) or not run_id.strip():
            run_id = None
        groups.setdefault(run_id, []).append(event)

    executions = [_execution(run_id, grouped, price_table)
                  for run_id, grouped in groups.items()]

    total_groups = {}
    for event in events:
        key = (event.get("provider"), event.get("model"))
        total_groups.setdefault(key, []).append(event)
    totals = []
    for (provider, model), grouped in total_groups.items():
        total = _aggregate(grouped, price_table)
        total.update({"provider": provider, "model": model})
        totals.append(total)

    project_total = _aggregate(events, price_table)
    return {
        "project_dir": os.path.abspath(project_dir),
        "journal": journal_path,
        "journal_exists": journal_exists,
        "price_table": {
            "declared": bool(price_table["path"]),
            "path": price_table["path"],
            "currency": price_table["currency"],
        },
        "malformed_lines": malformed_lines,
        "executions": executions,
        "totals": totals,
        "project_total": project_total,
    }
