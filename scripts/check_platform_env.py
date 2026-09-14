"""Valide le fichier `.env` avant un déploiement public de la plateforme."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from urllib.parse import urlsplit

_NOM = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_VRAI = {"1", "true", "yes"}


def _valeur_brute(valeur: str) -> str:
    """Décode les guillemets simples de la syntaxe dotenv sans l'évaluer."""
    valeur = valeur.strip()
    if len(valeur) >= 2 and valeur[0] == valeur[-1] and valeur[0] in "\"'":
        return valeur[1:-1]
    return valeur


def lire_env(chemin: Path) -> tuple[dict[str, str], list[str]]:
    """Lit uniquement des affectations dotenv, sans exécuter le fichier."""
    valeurs: dict[str, str] = {}
    erreurs: list[str] = []
    try:
        lignes = chemin.read_text(encoding="utf-8").splitlines()
    except OSError as erreur:
        return {}, [f"impossible de lire {chemin}: {erreur}"]

    for numero, brute in enumerate(lignes, 1):
        ligne = brute.strip()
        if not ligne or ligne.startswith("#"):
            continue
        if ligne.startswith("export "):
            ligne = ligne[7:].lstrip()
        nom, separateur, valeur = ligne.partition("=")
        nom = nom.strip()
        if not separateur or not _NOM.fullmatch(nom):
            erreurs.append(f"ligne {numero}: affectation dotenv invalide")
            continue
        if nom in valeurs:
            erreurs.append(f"ligne {numero}: variable dupliquée {nom}")
            continue
        valeurs[nom] = _valeur_brute(valeur)
    return valeurs, erreurs


def valider(valeurs: dict[str, str], erreurs: list[str] | None = None) -> list[str]:
    """Rend les erreurs qui empêcheraient d'ouvrir la plateforme au public."""
    fautes = list(erreurs or [])

    domaine = valeurs.get("MONL_PLATFORM_DOMAIN", "").strip().rstrip(".")
    if not domaine:
        fautes.append("MONL_PLATFORM_DOMAIN est obligatoire")
    elif domaine.lower() in {"localhost", "127.0.0.1", "::1"}:
        fautes.append("MONL_PLATFORM_DOMAIN ne doit pas rester sur localhost")
    elif any(caractere in domaine for caractere in ("/", ":", " ", "\t")):
        fautes.append("MONL_PLATFORM_DOMAIN doit être un nom d'hôte sans port ni chemin")

    public = valeurs.get("MONL_PLATFORM_PUBLIC_URL", "").strip()
    try:
        morceaux = urlsplit(public)
        hostname = morceaux.hostname
    except ValueError:
        morceaux = None
        hostname = None
    if morceaux is None or morceaux.scheme != "https" or not hostname:
        fautes.append("MONL_PLATFORM_PUBLIC_URL doit être une URL HTTPS")
    elif hostname.lower() in {"localhost", "127.0.0.1", "::1"}:
        fautes.append("MONL_PLATFORM_PUBLIC_URL ne doit pas rester sur localhost")
    if morceaux is not None and (
        morceaux.username or morceaux.password or morceaux.query or morceaux.fragment
    ):
        fautes.append("MONL_PLATFORM_PUBLIC_URL ne doit contenir ni identifiant, ni requête, ni fragment")

    for nom in ("MONL_COOKIE_SECURE", "MONL_TRUST_PROXY"):
        if valeurs.get(nom, "").strip().lower() not in _VRAI:
            fautes.append(f"{nom} doit être activée pour le proxy TLS")

    oauth_actif = False
    etat_secret = valeurs.get("MONL_PLATFORM_OAUTH_STATE_SECRET", "").strip()
    for fournisseur in ("GITHUB", "GOOGLE"):
        identifiant = valeurs.get(f"MONL_OAUTH_{fournisseur}_CLIENT_ID", "").strip()
        secret = valeurs.get(f"MONL_OAUTH_{fournisseur}_SECRET", "").strip()
        if bool(identifiant) != bool(secret):
            fautes.append(
                f"OAuth {fournisseur.lower()}: identifiant et secret doivent être renseignés ensemble"
            )
        if identifiant and secret:
            oauth_actif = True
    if oauth_actif:
        if not etat_secret:
            fautes.append("MONL_PLATFORM_OAUTH_STATE_SECRET est obligatoire si OAuth est activé")
        elif len(etat_secret) < 32:
            fautes.append("MONL_PLATFORM_OAUTH_STATE_SECRET doit faire au moins 32 caractères")

    return fautes


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("env_file", nargs="?", type=Path, default=Path(".env"))
    args = parser.parse_args(argv)

    valeurs, erreurs_lecture = lire_env(args.env_file)
    erreurs = valider(valeurs, erreurs_lecture)
    if erreurs:
        print("Configuration de plateforme invalide :", file=sys.stderr)
        for erreur in erreurs:
            print(f"- {erreur}", file=sys.stderr)
        return 1

    print(f"Configuration de plateforme valide : {args.env_file}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
