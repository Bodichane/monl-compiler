"""De quoi fabriquer un appel plausible sur une route qu'on ne connaît pas."""

import urllib.request

from . import fondations


def _premier_id(base, entite, token):
    """Identifiant d'un enregistrement RÉEL de l'entité parente, ou None si
    la liste est vide ou hors de portée de cet acteur. Sert à rattacher une
    création à une cible qui existe : les clés étrangères sont contraintes
    (PRAGMA foreign_keys = ON dans le backend généré)."""
    if not entite:
        return None
    status, corps = fondations._http("GET", f"{base}/{entite.lower()}?limit=1", token=token)
    if status != 200:
        return None
    donnees = (corps or {}).get("data") or []
    return donnees[0].get("id") if donnees else None

def _sample_value(ftype, fname, spec=None):
    # POINT 96 : un champ `oneOf` n'accepte QUE ses valeurs — 'smoke-status'
    # récolterait un 422, et le smoke test déclarerait cassée une application
    # saine. Deuxième occurrence de la leçon du point 95 : le vérificateur est
    # un client comme un autre, et toute brique qui contraint une ENTRÉE le
    # contraint aussi. La première valeur déclarée fait l'affaire — sur un
    # statut, c'est l'état initial.
    choix = (spec or {}).get("allowed_values")
    if choix:
        return choix[0]
    if ftype == "Integer":
        return 1
    if ftype in ("Float", "Money"):
        return 1.5
    if ftype == "Boolean":
        return True
    if ftype == "Email":
        return "smoke@exemple.fr"
    # POINT 101 : TROISIÈME occurrence de la leçon des points 95 et 96. Le type
    # 'UUID' vérifie enfin sa forme ; `smoke-reference` récolterait donc un 422
    # et le smoke test déclarerait cassée une boutique saine. Valeur FIXE et non
    # tirée au sort : un vérificateur doit donner deux fois le même verdict sur
    # la même application.
    if ftype == "UUID":
        return "3f2504e0-4f89-41d3-9a0c-0305e82c3301"
    # Un champ d'illustration recevait ici une URL `picsum.photos`. Le
    # vérificateur est un client comme un autre (points 95, 96, 100) : il n'a
    # pas à nommer un hôte distant que le reste du projet ne nomme plus. Il
    # tombe donc dans le repli générique — non vide, pour qu'une contrainte
    # `min` de longueur (point 85) continue de passer, et déterministe, parce
    # qu'un vérificateur doit rendre deux fois le même verdict.
    return f"smoke-{fname}"

def _list_query_probe(route, contract):
    """Construit une requête de liste conforme aux capacités déclarées."""
    query = route.get("list_query") or {}
    if not query:
        return ""
    fields = {
        field["name"]: field
        for field in (contract.get("entities", {}).get(route["entity"], {})
                      .get("fields") or [])
    }
    pairs = []
    for filtre in query.get("filters") or []:
        spec = fields[filtre["field"]]
        choices = filtre.get("allowed_values")
        value = choices[0] if choices else _sample_value(
            spec["type"], spec["name"], spec)
        if spec["type"] == "Boolean":
            value = str(value).lower()
        pairs.append((filtre["parameter"], value))
    tri = query.get("sort")
    if tri:
        pairs.extend(((tri["parameter"], tri["fields"][0]),
                      (tri["direction_parameter"], "asc")))
    return "?" + urllib.parse.urlencode(pairs)
