"""Validates the `.env` file before a public deployment of the platform."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from urllib.parse import urlsplit

_NOM = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_VRAI = {"1", "true", "yes"}


def _valeur_brute(valeur: str) -> str:
    """Decodes dotenv single quotes without evaluating the value."""
    valeur = valeur.strip()
    if len(valeur) >= 2 and valeur[0] == valeur[-1] and valeur[0] in "\"'":
        return valeur[1:-1]
    return valeur


def lire_env(chemin: Path) -> tuple[dict[str, str], list[str]]:
    """Reads dotenv assignments only, without executing the file."""
    valeurs: dict[str, str] = {}
    erreurs: list[str] = []
    try:
        lignes = chemin.read_text(encoding="utf-8").splitlines()
    except OSError as erreur:
        return {}, [f"cannot read {chemin}: {erreur}"]

    for numero, brute in enumerate(lignes, 1):
        ligne = brute.strip()
        if not ligne or ligne.startswith("#"):
            continue
        if ligne.startswith("export "):
            ligne = ligne[7:].lstrip()
        nom, separateur, valeur = ligne.partition("=")
        nom = nom.strip()
        if not separateur or not _NOM.fullmatch(nom):
            erreurs.append(f"line {numero}: invalid dotenv assignment")
            continue
        if nom in valeurs:
            erreurs.append(f"line {numero}: duplicated variable {nom}")
            continue
        valeurs[nom] = _valeur_brute(valeur)
    return valeurs, erreurs


def valider(valeurs: dict[str, str], erreurs: list[str] | None = None) -> list[str]:
    """Returns the errors that would keep the platform from opening to the public."""
    fautes = list(erreurs or [])

    domaine = valeurs.get("MONL_PLATFORM_DOMAIN", "").strip().rstrip(".")
    if not domaine:
        fautes.append("MONL_PLATFORM_DOMAIN is required")
    elif domaine.lower() in {"localhost", "127.0.0.1", "::1"}:
        fautes.append("MONL_PLATFORM_DOMAIN must not stay on localhost")
    elif any(caractere in domaine for caractere in ("/", ":", " ", "\t")):
        fautes.append("MONL_PLATFORM_DOMAIN must be a host name without port or path")

    public = valeurs.get("MONL_PLATFORM_PUBLIC_URL", "").strip()
    try:
        morceaux = urlsplit(public)
        hostname = morceaux.hostname
    except ValueError:
        morceaux = None
        hostname = None
    if morceaux is None or morceaux.scheme != "https" or not hostname:
        fautes.append("MONL_PLATFORM_PUBLIC_URL must be an HTTPS URL")
    elif hostname.lower() in {"localhost", "127.0.0.1", "::1"}:
        fautes.append("MONL_PLATFORM_PUBLIC_URL must not stay on localhost")
    if morceaux is not None and (
        morceaux.username or morceaux.password or morceaux.query or morceaux.fragment
    ):
        fautes.append("MONL_PLATFORM_PUBLIC_URL must contain no credentials, query or fragment")

    for nom in ("MONL_COOKIE_SECURE", "MONL_TRUST_PROXY"):
        if valeurs.get(nom, "").strip().lower() not in _VRAI:
            fautes.append(f"{nom} must be enabled for the TLS proxy")

    oauth_actif = False
    etat_secret = valeurs.get("MONL_PLATFORM_OAUTH_STATE_SECRET", "").strip()
    for fournisseur in ("GITHUB", "GOOGLE"):
        identifiant = valeurs.get(f"MONL_OAUTH_{fournisseur}_CLIENT_ID", "").strip()
        secret = valeurs.get(f"MONL_OAUTH_{fournisseur}_SECRET", "").strip()
        if bool(identifiant) != bool(secret):
            fautes.append(
                f"OAuth {fournisseur.lower()}: client id and secret must be set together"
            )
        if identifiant and secret:
            oauth_actif = True
    if oauth_actif:
        if not etat_secret:
            fautes.append("MONL_PLATFORM_OAUTH_STATE_SECRET is required when OAuth is enabled")
        elif len(etat_secret) < 32:
            fautes.append("MONL_PLATFORM_OAUTH_STATE_SECRET must be at least 32 characters")

    return fautes


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("env_file", nargs="?", type=Path, default=Path(".env"))
    args = parser.parse_args(argv)

    valeurs, erreurs_lecture = lire_env(args.env_file)
    erreurs = valider(valeurs, erreurs_lecture)
    if erreurs:
        print("Invalid platform configuration:", file=sys.stderr)
        for erreur in erreurs:
            print(f"- {erreur}", file=sys.stderr)
        return 1

    print(f"Valid platform configuration: {args.env_file}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
