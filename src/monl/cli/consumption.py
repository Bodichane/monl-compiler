"""What a build cost."""

import json
import os

from ..usage import UsagePriceError, build_usage_report
from . import location, nomenclature


def _usage_value(value):
    if value is None:
        return "unknown"
    if isinstance(value, float):
        return f"{value:.3f}".rstrip("0").rstrip(".")
    return str(value)

def _usage_cost(item, currency):
    cost = item.get("cost")
    if cost is not None:
        valeur = _usage_value(cost)
        return f"{valeur} {currency}" if currency else valeur
    if item.get("price_status") == "not_declared":
        return "price not declared"
    if item.get("price_status") == "counters_unavailable":
        return "token counters unavailable"
    return "no cost"

def _usage_measure(item):
    measures = []
    if item.get("input_tokens") is not None or item.get("output_tokens") is not None:
        measures.append(
            f"input {_usage_value(item.get('input_tokens'))}, "
            f"output {_usage_value(item.get('output_tokens'))} tokens"
        )
    if item.get("requests") is not None:
        measures.append(f"{_usage_value(item['requests'])} image request(s)")
    return " | ".join(measures) or "tokens not applicable"

def _usage_line(item, currency, prefix="  "):
    operations = item.get("operation") or "unknown operation"
    attempts = ",".join(str(value) for value in item.get("attempts", [])) or "unknown"
    stages = ", ".join(
        f"{stage}×{item['stage_counts'][stage]}"
        if item.get("stage_counts", {}).get(stage, 0) > 1 else stage
        for stage in item.get("stages", [])
    ) or "none"
    return (f"{prefix}{operations} | attempts {attempts} | stages {stages} | "
            f"{_usage_measure(item)} | "
            f"duration {_usage_value(item.get('duration_seconds'))} s | "
            f"cost {_usage_cost(item, currency)}")

def _usage_total_line(item, currency, prefix="  "):
    return (f"{prefix}{_usage_measure(item)} | "
            f"duration {_usage_value(item.get('duration_seconds'))} s | "
            f"cost {_usage_cost(item, currency)}")

def _print_usage_report(report):
    if not report["journal_exists"]:
        print(f"ℹ️ No AI usage log in {report['journal']}: "
              "no usage measured.")
        return

    price = report["price_table"]
    source = price["path"] or "no table"
    print(f"─── AI usage — {report['project_dir']} ───")
    print(f"Price table: {source}"
          + (f" ({price['currency']})" if price["currency"] else ""))
    print(f"─── Runs ({len(report['executions'])}) ───")
    for execution in report["executions"]:
        if execution["known"]:
            prefix = f"  run_id={execution['run_id']} | "
        else:
            prefix = ("  unknown run — events without run_id; no "
                      "grouping inferred | ")
        print(_usage_line(execution, price["currency"], prefix=prefix))

    print("─── Provider / model totals ───")
    if not report["totals"]:
        print("  (no usable events)")
    for total in report["totals"]:
        print(f"  {total.get('provider') or 'unknown provider'} / "
              f"{total.get('model') or 'unknown model'}")
        print(_usage_total_line(total, price["currency"], prefix="    "))

    print("─── Project total ───")
    print(_usage_total_line(report["project_total"], price["currency"]))
    for malformed in report["malformed_lines"]:
        print(f" ⚠️ Line {malformed['line']} ignored: {malformed['error']}.")

def cmd_usage(project_dir, prices_path=None, json_output=False):
    """Read a consumption log without estimating the unpriced lines."""
    project_dir = os.path.abspath(project_dir)
    issue = location._error_of_path(project_dir)
    if issue:
        if json_output:
            print(json.dumps({"error": issue}, ensure_ascii=False))
        else:
            print(issue)
        raise SystemExit(1)
    if not os.path.exists(os.path.join(project_dir, nomenclature.STATE_FILENAME)):
        message = (f" ❌ {nomenclature.STATE_FILENAME} not found — this directory is not a "
                   "monl project.")
        if json_output:
            print(json.dumps({"error": message}, ensure_ascii=False))
        else:
            print(message)
        raise SystemExit(1)
    try:
        report = build_usage_report(project_dir, prices_path=prices_path)
    except UsagePriceError as err:
        if json_output:
            print(json.dumps({"error": str(err)}, ensure_ascii=False))
        else:
            print(f" ❌ {err}")
        raise SystemExit(1) from err
    if json_output:
        print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    else:
        _print_usage_report(report)
