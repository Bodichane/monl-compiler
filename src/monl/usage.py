"""Lecture honnête du journal de consommation des fournisseurs IA.

Les tarifs ne vivent pas dans monl : ils sont fournis par l'exploitant. Ce
module ne fait donc que vérifier la forme de la table, agréger les événements
et calculer les coûts quand le tarif et les deux compteurs nécessaires sont
présents.
"""

import json
import math
import os
from decimal import Decimal, InvalidOperation

USAGE_FILENAME = ".monl_ai_usage.jsonl"
PRICES_ENVIRONMENT = "MONL_USAGE_PRICES"


class UsagePriceError(ValueError):
    """Table de prix absente ou inexploitable."""


def _decimal(value, label):
    if isinstance(value, bool) or value is None:
        raise UsagePriceError(f"tarif invalide pour {label}")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise UsagePriceError(f"tarif invalide pour {label}") from exc
    if not result.is_finite() or result < 0:
        raise UsagePriceError(f"tarif invalide pour {label}")
    return result


def _load_prices(path):
    if not path:
        return {"currency": None, "prices": {}, "path": None}
    try:
        with open(path, encoding="utf-8") as fh:
            document = json.load(fh)
    except OSError as exc:
        raise UsagePriceError(f"table de prix illisible : {path} — {exc}") from exc
    except json.JSONDecodeError as exc:
        raise UsagePriceError(f"table de prix JSON invalide : {path}") from exc

    if not isinstance(document, dict):
        raise UsagePriceError("la table de prix doit être un objet JSON")
    currency = document.get("currency")
    if currency is not None and (not isinstance(currency, str) or not currency.strip()):
        raise UsagePriceError("currency doit être une chaîne non vide")
    declared = document.get("prices", document)
    if not isinstance(declared, dict):
        raise UsagePriceError("prices doit être un objet fournisseur → modèle")

    prices = {}
    for provider, models in declared.items():
        if provider == "currency":
            continue
        if not isinstance(provider, str) or not isinstance(models, dict):
            raise UsagePriceError("chaque fournisseur doit contenir un objet de modèles")
        prices[provider] = {}
        for model, rates in models.items():
            if not isinstance(model, str) or not isinstance(rates, dict):
                raise UsagePriceError("chaque modèle doit contenir un objet de tarifs")
            input_rate = rates.get("input_per_million_tokens")
            output_rate = rates.get("output_per_million_tokens")
            if input_rate is None or output_rate is None:
                raise UsagePriceError(
                    f"tarifs incomplets pour {provider}/{model} : "
                    "input_per_million_tokens et output_per_million_tokens sont requis")
            prices[provider][model] = {
                "input": _decimal(input_rate, f"{provider}/{model} input"),
                "output": _decimal(output_rate, f"{provider}/{model} output"),
            }
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


def _unique(values):
    return list(dict.fromkeys(value for value in values if value is not None))


def _price_label(provider, model):
    return f"{provider or 'fournisseur inconnu'}/{model or 'modèle inconnu'}"


def _aggregate(events, price_table):
    input_tokens, input_complete = _sum_counter(events, "input_tokens")
    output_tokens, output_complete = _sum_counter(events, "output_tokens")
    duration, duration_complete = _sum_counter(events, "duration_seconds")
    total_tokens = (input_tokens + output_tokens
                    if input_tokens is not None and output_tokens is not None else None)

    priced_cost = Decimal("0")
    missing_prices = []
    missing_counters = False
    for event in events:
        provider = event.get("provider")
        model = event.get("model")
        rates = price_table["prices"].get(provider, {}).get(model)
        if rates is None:
            missing_prices.append(_price_label(provider, model))
            continue
        input_value = _counter(event, "input_tokens")
        output_value = _counter(event, "output_tokens")
        if input_value is None or output_value is None:
            missing_counters = True
            continue
        priced_cost += (
            Decimal(str(input_value)) * rates["input"] / Decimal("1000000")
            + Decimal(str(output_value)) * rates["output"] / Decimal("1000000")
        )

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
        "label": "exécution" if run_id is not None else "exécution inconnue",
        "operation": operations[0] if len(operations) == 1 else "multiple",
        "operations": operations,
        "attempts": attempts,
        "attempt_count": len(attempts),
        "stages": stages,
        "stage_counts": stage_counts,
    })
    return aggregate


def build_usage_report(project_dir, prices_path=None):
    """Construit un rapport JSON-sérialisable sans regrouper par intuition."""
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
                        malformed_lines.append({"line": line_number, "error": "ligne vide"})
                        continue
                    try:
                        event = json.loads(line)
                    except json.JSONDecodeError:
                        malformed_lines.append({"line": line_number, "error": "JSON invalide"})
                        continue
                    if not isinstance(event, dict):
                        malformed_lines.append({
                            "line": line_number, "error": "objet JSON attendu",
                        })
                        continue
                    events.append(event)
        except OSError as exc:
            raise UsagePriceError(f"journal illisible : {journal_path} — {exc}") from exc

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
