"""What it takes to make a plausible call on a route we do not know."""

import urllib.request

from . import foundations


def _premier_id(base, entite, token):
    """Identifier of a REAL record of the parent entity, or None if the list is
    empty or out of this actor's reach. Used to attach a creation to a target
    that exists: foreign keys are constrained (PRAGMA foreign_keys = ON in the
    generated backend)."""
    if not entite:
        return None
    status, corps = foundations._http("GET", f"{base}/{entite.lower()}?limit=1", token=token)
    if status != 200:
        return None
    donnees = (corps or {}).get("data") or []
    return donnees[0].get("id") if donnees else None

def _sample_value(ftype, fname, spec=None):
    # POINT 96: a `oneOf` field accepts ONLY its values — 'smoke-status' would
    # get a 422, and the smoke test would declare a healthy application broken.
    # Second occurrence of the point 95 lesson: the verifier is a client like
    # any other, and any brick that constrains an INPUT constrains it too. The
    # first declared value will do — on a status, it is the initial state.
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
    # POINT 101: THIRD occurrence of the lesson of points 95 and 96. The 'UUID'
    # type finally checks its form; `smoke-reference` would therefore get a 422
    # and the smoke test would declare a healthy shop broken. A FIXED value,
    # not a random one: a verifier must give the same verdict twice on the same
    # application.
    if ftype == "UUID":
        return "3f2504e0-4f89-41d3-9a0c-0305e82c3301"
    # An illustration field used to receive a `picsum.photos` URL here. The
    # verifier is a client like any other (points 95, 96, 100): it has no
    # business naming a remote host the rest of the project no longer names. It
    # therefore falls into the generic fallback — non-empty, so that a length
    # `min` constraint (point 85) keeps passing, and deterministic, because a
    # verifier must give the same verdict twice.
    return f"smoke-{fname}"

def _list_query_probe(route, contract):
    """Builds a list request matching the declared capabilities."""
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
