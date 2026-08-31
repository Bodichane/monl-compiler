"""Analyse conservatrice des appels ``fetch`` du frontend livré."""

import os
import posixpath
import re

_FETCH_CHEMIN = re.compile(
    r"\bfetch\s*\(\s*(?P<quote>['\"`])(?P<path>.*?)(?P=quote)"
    r"(?=\s*(?:,|\)))",
    re.IGNORECASE | re.DOTALL,
)


def _parameter_reaches_fetch(body, parameter):
    motif = re.escape(parameter)
    if re.search(rf"\bfetch\s*\(\s*[^,)]*\b{motif}\b", body):
        return True
    for call in re.finditer(r"\bfetch\s*\(\s*(\w+)\s*[,)]", body):
        variable = re.escape(call.group(1))
        if re.search(rf"\b(?:const|let|var)\s+{variable}\s*=[^;]*\b{motif}\b",
                     body):
            return True
    return False


def _normalise_path(path, dynamic_suffix=False):
    path = path.strip()
    path = re.sub(r"^\$\{[^}]+\}", "", path)
    if not path.startswith("/"):
        return None
    path = re.sub(r"\$\{[^}]+\}", "{id}", path)
    path = path.split("?", 1)[0].split("#", 1)[0]
    if dynamic_suffix:
        path = path.rstrip("/") + "/${id}"
    path = re.sub(r"\$\{[^}]+\}", "{id}", path)
    if "$" in path:
        return None
    return posixpath.normpath(path)


def _add_fetch_call(calls, path, suffix, dynamic_suffix=False, suffix_text=""):
    path = _normalise_path(path, dynamic_suffix)
    if path is None:
        return
    if dynamic_suffix:
        ending = re.search(r"['\"](/[^'\"]*)['\"]\s*$", suffix_text)
        if ending:
            path += ending.group(1)
    closing = re.match(r"\s*\)", suffix)
    options = re.match(r"\s*,\s*\{(?P<body>.*?)\}\s*\)", suffix, re.DOTALL)
    if closing:
        method = "GET"
    elif options:
        method_match = re.search(
            r"\bmethod\s*:\s*(?:\w+\s*\?\s*)?"
            r"['\"](GET|POST|PUT|DELETE)['\"]",
            options.group("body"), re.IGNORECASE)
        method = method_match.group(1).upper() if method_match else "GET"
    else:
        method = None
    calls.add((method, path))


def _direct_fetch_calls(source):
    calls = set()
    for match in _FETCH_CHEMIN.finditer(source):
        _add_fetch_call(calls, match.group("path"), source[match.end():])
    return calls


def _verifiable_wrappers(source):
    wrappers = []
    for definition in re.finditer(
            r"(?:async\s+)?function\s+(\w+)\s*\(([^)]*)\)\s*\{", source):
        name, parameters = definition.groups()
        names = [parameter.strip().split("=", 1)[0].strip()
                 for parameter in parameters.split(",") if parameter.strip()]
        if names and _parameter_reaches_fetch(
                source[definition.end():definition.end() + 5000], names[0]):
            wrappers.append(name)
    return wrappers


def _wrapper_literal_calls(source, wrapper):
    calls = set()
    matches = re.finditer(
        rf"\b{re.escape(wrapper)}\s*\(\s*"
        r"(?P<quote>['\"`])(?P<path>.*?)(?P=quote)"
        r"(?P<suffix>\s*\+\s*[^,)]*)?"
        r"(?=\s*(?:,|\)))",
        source, re.DOTALL)
    for call in matches:
        _add_fetch_call(
            calls, call.group("path"), source[call.end():],
            dynamic_suffix=bool(call.group("suffix")),
            suffix_text=call.group("suffix") or "",
        )
    return calls


def _wrapper_conditional_calls(source, wrapper):
    calls = set()
    for call in re.finditer(
            rf"\b{re.escape(wrapper)}\s*\((?P<args>[^;\n]*)", source):
        arguments = call.group("args")
        paths = [match.group(1) for match in re.finditer(
            r"['\"](/[^'\"]*)['\"]", arguments)
            if not re.search(r"\+\s*$", arguments[:match.start()])]
        methods = [method.upper() for method in re.findall(
            r"\bmethod\s*:\s*(?:\w+\s*\?\s*)?"
            r"['\"](GET|POST|PUT|DELETE)['\"]",
            arguments, re.IGNORECASE)]
        if not paths or not methods:
            continue
        for index, path in enumerate(paths):
            dynamic = path.endswith("/") and ("+" in arguments or "?" in arguments)
            method = methods[index] if index < len(methods) else methods[0]
            normalised = _normalise_path(path, dynamic)
            if normalised:
                calls.add((method, normalised))
    return calls


def _wrapper_fetch_calls(source, wrapper):
    return (_wrapper_literal_calls(source, wrapper)
            | _wrapper_conditional_calls(source, wrapper))


def _source_fetch_calls(source):
    calls = _direct_fetch_calls(source)
    for wrapper in _verifiable_wrappers(source):
        calls |= _wrapper_fetch_calls(source, wrapper)
    return calls


def frontend_fetch_calls(frontend_dir):
    """Retourne les appels ``fetch`` statiquement identifiables."""
    calls = set()
    for root, _dirs, names in os.walk(frontend_dir):
        for name in names:
            if not name.endswith((".html", ".js")):
                continue
            try:
                with open(os.path.join(root, name), encoding="utf-8",
                          errors="ignore") as fh:
                    source = fh.read()
            except OSError:
                continue
            calls |= _source_fetch_calls(source)
    return calls
