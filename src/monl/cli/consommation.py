"""Ce qu'une construction a coûté."""

import json
import os

from ..usage import UsagePriceError, build_usage_report
from . import emplacement, nomenclature


def _usage_value(value):
    if value is None:
        return "inconnu"
    if isinstance(value, float):
        return f"{value:.3f}".rstrip("0").rstrip(".")
    return str(value)

def _usage_cost(item, currency):
    cost = item.get("cost")
    if cost is not None:
        valeur = _usage_value(cost)
        return f"{valeur} {currency}" if currency else valeur
    if item.get("price_status") == "not_declared":
        return "prix non déclaré"
    if item.get("price_status") == "counters_unavailable":
        return "compteurs de jetons indisponibles"
    return "aucun coût"

def _usage_measure(item):
    measures = []
    if item.get("input_tokens") is not None or item.get("output_tokens") is not None:
        measures.append(
            f"entrée {_usage_value(item.get('input_tokens'))}, "
            f"sortie {_usage_value(item.get('output_tokens'))} jetons"
        )
    if item.get("requests") is not None:
        measures.append(f"{_usage_value(item['requests'])} requête(s) d'image")
    return " | ".join(measures) or "jetons non applicables"

def _usage_line(item, currency, prefix="  "):
    operations = item.get("operation") or "opération inconnue"
    attempts = ",".join(str(value) for value in item.get("attempts", [])) or "inconnues"
    stages = ", ".join(
        f"{stage}×{item['stage_counts'][stage]}"
        if item.get("stage_counts", {}).get(stage, 0) > 1 else stage
        for stage in item.get("stages", [])
    ) or "aucune"
    return (f"{prefix}{operations} | tentatives {attempts} | étapes {stages} | "
            f"{_usage_measure(item)} | "
            f"durée {_usage_value(item.get('duration_seconds'))} s | "
            f"coût {_usage_cost(item, currency)}")

def _usage_total_line(item, currency, prefix="  "):
    return (f"{prefix}{_usage_measure(item)} | "
            f"durée {_usage_value(item.get('duration_seconds'))} s | "
            f"coût {_usage_cost(item, currency)}")

def _print_usage_report(report):
    if not report["journal_exists"]:
        print(f"ℹ️ Aucun journal de consommation IA dans {report['journal']} : "
              "aucune consommation mesurée.")
        return

    price = report["price_table"]
    source = price["path"] or "aucune table"
    print(f"─── Usage IA — {report['project_dir']} ───")
    print(f"Table de prix : {source}"
          + (f" ({price['currency']})" if price["currency"] else ""))
    print(f"─── Exécutions ({len(report['executions'])}) ───")
    for execution in report["executions"]:
        if execution["known"]:
            prefix = f"  run_id={execution['run_id']} | "
        else:
            prefix = ("  exécution inconnue — événements sans run_id; aucun "
                      "regroupement déduit | ")
        print(_usage_line(execution, price["currency"], prefix=prefix))

    print("─── Totaux fournisseur / modèle ───")
    if not report["totals"]:
        print("  (aucun événement exploitable)")
    for total in report["totals"]:
        print(f"  {total.get('provider') or 'fournisseur inconnu'} / "
              f"{total.get('model') or 'modèle inconnu'}")
        print(_usage_total_line(total, price["currency"], prefix="    "))

    print("─── Total projet ───")
    print(_usage_total_line(report["project_total"], price["currency"]))
    for malformed in report["malformed_lines"]:
        print(f" ⚠️ Ligne {malformed['line']} ignorée : {malformed['error']}.")

def cmd_usage(project_dir, prices_path=None, json_output=False):
    """Lire un journal de consommation sans estimer les lignes non tarifées."""
    project_dir = os.path.abspath(project_dir)
    souci = emplacement._erreur_de_chemin(project_dir)
    if souci:
        if json_output:
            print(json.dumps({"error": souci}, ensure_ascii=False))
        else:
            print(souci)
        raise SystemExit(1)
    if not os.path.exists(os.path.join(project_dir, nomenclature.STATE_FILENAME)):
        message = (f" ❌ {nomenclature.STATE_FILENAME} introuvable — ce dossier n'est pas un "
                   "projet monl.")
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
