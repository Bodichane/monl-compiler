"""The six steps of the smoke test, in the order they run.

"Exists" is not "served" (point 83): the two middle steps ask the same
question — does the server return this file at the announced URL? — one
on the DECLARED assets, the other on what the AI invented while writing
the page. A missing file raises NO exception: jsdom receives the 404 and
carries on, like a real browser."""

import json
import os
import shutil
import subprocess

from . import claimed_files, email_verification, foundations, probes


def _account_of_test(base, contract, errors, warnings):
    """Register then log in a real account, and return its token."""
    # --- 2a. real account: register → login → token ---
    # FIX (beta 3): the test account was created with the first role in
    # alphabetical order, which is often a privileged role — now refused at
    # registration (403). We take a role open to self-registration; if the spec
    # declares none, the application has no registration flow to exercise.
    self_register = contract.get("self_register_actors") or []
    actor, token = None, None
    if self_register:
        actor = self_register[0]
        # POINT 95: the test account's identifier must respect the form the
        # application REQUIRES. Hard-coded, 'smoke' got a 422 on every app
        # declaring 'identifier: email' — and the smoke test, meant to prove
        # the app works, failed on its own registration. The verifier cannot
        # ignore a rule it enforces elsewhere.
        identifier = foundations._identifier_smoke(contract)
        status, _b = foundations._http("POST", base + "/register",
                           {"username": identifier, "password": "smokepass123",
                            "actor": actor})
        if status != 200:
            errors.append(f"/register returned {status} (expected 200)")
        status, body = foundations._http("POST", base + "/login",
                             {"username": identifier, "password": "smokepass123"})
        token = email_verification.check_login(
            base, contract, status, body, errors, warnings)
        # A role NOT open to registration must never be obtainable through a
        # plain HTTP call: that is the flaw fixed in beta 3, exercised here on
        # every run.
        for rang, provisioned in enumerate(
                [a for a in contract["actors"] if a not in self_register], start=1):
            status, _b = foundations._http("POST", base + "/register",
                               {"username": foundations._identifier_smoke(contract, rang),
                                "password": "smokepass123", "actor": provisioned})
            if status == 200:
                errors.append(f"/register accepted provisioned role '{provisioned}' "
                              f"(privilege escalation: expected a 403 refusal)")
    else:
        warnings.append("No 'selfRegister' role: registration flow not tested "
                        "(accounts are provisioned by manage.py).")
    return email_verification.actor_connected(actor, contract), token

def _try_the_routes(actor, base, contract, errors, token):
    """Each contract route, called for real."""
    # --- 2b. each contract route, under real conditions ---
    for route in contract["routes"]:
        concrete = route["path"].replace("{id}", "1")
        _try_the_refusal(route, base, concrete, errors)
        if route["method"] != "GET":
            continue
        if route["auth_required"]:
            _try_the_read_authenticated(route, actor, base, concrete,
                                              contract, errors, token)
        else:
            _try_the_read_public(route, base, concrete, contract, errors)


# The three functions below are extracted from `_eprouver_les_routes`
# (complexity ceiling): same calls, same expected statuses, same messages.
# The two read checks are mutually exclusive (auth_required or not), so
# grouping them does not change the order of the calls made for a route.
def _try_the_refusal(route, base, concrete, errors):
    """What a request without the right credential must get."""
    path, method = route["path"], route["method"]
    if route.get("auth_mode") == "refresh_token":
        # BRICK B4: /refresh is authenticated by a dedicated opaque token,
        # never by the access JWT. An empty request must be refused,
        # without requiring a Bearer that has precisely no business here.
        status, _b = foundations._http(method, base + concrete,
                           body={} if method in ("POST", "PUT") else None)
        if status < 400:
            errors.append(f"{method} {path} accepted an empty refresh "
                          f"(response {status})")
    elif route["auth_required"] and route["allowed_actors"]:
        status, _b = foundations._http(method, base + concrete,
                           body={} if method in ("POST", "PUT") else None)
        if status not in (401, 403):
            errors.append(f"{method} {path} without a token returned {status} "
                          f"(expected a 401/403 refusal)")
    elif route["auth_required"]:
        # POINT 74: a route protected OTHERWISE than by a JWT — the payment
        # webhook, authenticated by the provider's signature. No actor
        # opens it, so requiring 401/403 makes no sense: without a
        # configured key it answers 503, and with a key 400 (missing
        # signature). What must hold in every case is that a bare request
        # is REFUSED.
        status, _b = foundations._http(method, base + concrete,
                           body={} if method in ("POST", "PUT") else None)
        if status < 400:
            errors.append(f"{method} {path} accepted a request without "
                          f"any authentication (response {status})")


def _try_the_read_public(route, base, concrete, contract, errors):
    """A public GET answers, and so does its declared list query."""
    path = route["path"]
    status, _b = foundations._http("GET", base + concrete)
    if route["action"] == "List" and status != 200:
        errors.append(f"GET {path} (public) returned {status} (expected 200)")
    if route["action"] == "Read" and status not in (200, 404):
        errors.append(f"GET {path} (public) returned {status} (expected 200/404)")
    if route["action"] == "List" and route.get("list_query"):
        probe = probes._list_query_probe(route, contract)
        status, _b = foundations._http("GET", base + concrete + probe)
        if status != 200:
            errors.append(f"GET {path}{probe} (public) returned {status} "
                          f"(expected 200)")


def _try_the_read_authenticated(route, actor, base, concrete, contract,
                                      errors, token):
    """A protected list answers the test account, list query included."""
    path = route["path"]
    if not (token and actor in route["allowed_actors"] and route["action"] == "List"):
        return
    status, _b = foundations._http("GET", base + concrete, token=token)
    if status != 200:
        errors.append(f"GET {path} with {actor} token returned {status} "
                      f"(expected 200)")
    if status == 200 and route.get("list_query"):
        probe = probes._list_query_probe(route, contract)
        status, _b = foundations._http("GET", base + concrete + probe,
                           token=token)
        if status != 200:
            errors.append(f"GET {path}{probe} with the contract's list "
                          f"capabilities returned {status} (expected 200)")


def _try_a_creation(actor, base, contract, errors, token, warnings):
    """A real creation, to exercise the request body end to end."""
    # A real creation on the first entity the actor can create, to exercise the
    # contract's request body end to end.
    for route in contract["routes"]:
        if route["action"] != "Create" or actor not in route["allowed_actors"]:
            continue
        entity = contract["entities"][route["entity"]]
        fields = {f["name"]: f for f in entity["fields"]}
        # The body is built from the CONTRACT's request_fields, not from the
        # entity's field list: the attachment columns (a comment's article) are
        # not part of it, and the probe called itself "contract-compliant"
        # while omitting what the contract requires (point 57).
        references = {fk["column"]: fk["references"]
                      for fk in entity["foreign_keys"]}
        payload, parent_missing = {}, None
        for name in route.get("request_fields") or []:
            spec = fields.get(name)
            if spec:
                payload[name] = probes._sample_value(spec["type"], name, spec)
                continue
            # Foreign keys are CONSTRAINED in the database: inventing an
            # identifier would make the insertion fail for a reason unrelated
            # to the contract.
            parent = references.get(name)
            identifier = probes._first_id(base, parent, token) if parent else None
            if identifier is None:
                parent_missing = (name, parent)
                break
            payload[name] = identifier
        if parent_missing:
            name, parent = parent_missing
            warnings.append(
                f"creation of {route['entity']} not tested: '{name}' "
                f"requires an existing {parent}, and none is readable "
                f"(adding a 'seed {parent}' block would make this path "
                f"verifiable)")
            break
        status, _b = foundations._http("POST", base + route["path"], payload,
                           token=None if not route["auth_required"] else token)
        if status != 200:
            errors.append(f"POST {route['path']} with a contract-compliant body "
                          f"returned {status} (expected 200)")
        break

def _assets_really_served(assets_dir, assets_src, base, contract, errors, has_assets):
    """Do the DECLARED assets answer at the URL the contract announces?"""
    # --- 2c. declared assets: really served? (brick 13) --- The validator has
    # already checked that each file EXISTS on disk. This check answers the
    # other half of the question, the only one that matters for a browser: does
    # the server return it, at the URL the contract announces? A mount placed
    # after the /site one would exist without ever answering, and nothing would
    # have said so.
    if has_assets:
        assets = contract.get("assets") or {}
        for key in ("logo", "favicon"):
            if not assets.get(key):
                continue
            url = f"{base}/site/{assets[key]}"
            status, _b = foundations._http("GET", url)
            if status != 200:
                errors.append(
                    f"declared asset '{key}' ({assets[key]}) returned {status} at "
                    f"/site/{assets[key]}: the file exists but is not SERVED.")
        # An assets folder declared but mounted nowhere is a silent trap: it is
        # exercised on a real file of the folder.
        witness = next((n for n in sorted(os.listdir(assets_src))
                       if os.path.isfile(os.path.join(assets_src, n))), None)
        if witness:
            status, _b = foundations._http("GET", f"{base}/site/{assets_dir}/{witness}")
            if status != 200:
                errors.append(
                    f"assets directory '{assets_dir}/' is not served: "
                    f"/site/{assets_dir}/{witness} returned {status}.")

def _files_claimed_served(base, errors, has_frontend, workdir):
    """Are the files the AI CLAIMED delivered? (brick 29)"""
    # --- 2d. files CLAIMED by the frontend: really served? (brick 29, point
    # 137) — the same question as 2c, asked about what the AI wrote and not
    # about what the spec declares. Point 83 exercised the DECLARED assets;
    # nobody had declared these: the AI invented them while writing the page.
    if has_frontend:
        front_dir = os.path.join(workdir, "frontend")
        for page, path in claimed_files._references_locales(front_dir):
            url = claimed_files._url_of_reference(page, path)
            if url is None:
                errors.append(
                    f"frontend/{page} references '{path}', which escapes the site.")
                continue
            status, _b = foundations._http("GET", base + url)
            if status == 200:
                continue
            detail = (f"frontend/{page} references '{path}': "
                      f"{url} returned {status}.")
            if path.lower().endswith(
                    (".png", ".jpg", ".jpeg", ".webp", ".gif", ".avif")):
                # A frequent and silent cause: `monl import` KEEPS only the
                # allowlist, so a photo present in the archive is discarded
                # without a word, and the page that claims it stays. Its place
                # is the assets folder (brick 13), which is versioned and
                # checked.
                detail += (" An image delivered with the frontend is not "
                           "retained: declare it in the spec's 'assets'.")
            else:
                detail += " This file was not delivered."
            errors.append(detail)

def _first_report_json(output):
    """The first JSON line of the jsdom runner's output, or None. Extracted from
    `_frontend_dans_jsdom` (complexity ceiling)."""
    for line in output.splitlines():
        try:
            return json.loads(line)
        except json.JSONDecodeError:
            continue
    return None


def _frontend_in_jsdom(base, contract, errors, has_frontend, say, warnings, workdir):
    """The frontend, loaded in a real headless browser."""
    # --- 3. real frontend in jsdom (if Node is available) ---
    if has_frontend:
        node = shutil.which("node")
        if not node:
            warnings.append("Node.js not found — the frontend was not executed "
                            "(static check only). Install node for a complete "
                            "smoke test.")
        else:
            jsdom_ok = foundations._ensure_jsdom(workdir, say)
            if not jsdom_ok:
                warnings.append("jsdom unavailable (npm installation failed) — "
                                "the frontend was not executed.")
            else:
                runner = os.path.join(workdir, "_smoke_runner.js")
                with open(runner, "w", encoding="utf-8") as fh:
                    fh.write(foundations.JSDOM_RUNNER)
                proc = subprocess.run(
                    [node, runner, os.path.join(workdir, "frontend"), base],
                    cwd=workdir, capture_output=True, text=True, timeout=60,
                    env={**os.environ, "NODE_PATH": foundations._jsdom_node_path()})
                report = _first_report_json(proc.stdout)
                if report is None:
                    errors.append("the jsdom runner produced no report: "
                                  + (proc.stderr or proc.stdout)[-300:])
                else:
                    for err in dict.fromkeys(report["js_errors"]):  # deduplicated (onerror + listener)
                        errors.append(f"JavaScript exception in frontend: {err}")
                    known = {r["path"].split("/")[1] for r in contract["routes"]}
                    known |= {"register", "login", "logout", "docs", "site"}
                    for f in report["fetches"]:
                        first = f["url"].lstrip("/").split("/")[0].split("?")[0]
                        if f["url"].startswith("/") and first not in known:
                            errors.append(f"frontend calls a path outside the "
                                          f"contract: {f['url']}")
                        elif f["status"] in (0, 404, 422, 500):
                            errors.append(f"frontend call {f['url']} → "
                                          f"{f['status'] or f.get('error', '?')}")
                    if not report["fetches"]:
                        warnings.append("the frontend made no API calls on "
                                        "load — nothing to check over the network.")
