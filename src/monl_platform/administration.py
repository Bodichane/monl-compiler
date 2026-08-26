"""`monl-platform admin` — les gestes d'exploitation sur les comptes.

**Pourquoi une ligne de commande et pas un panneau web.** Toute intervention
sur un compte passait par `sqlite3` à la main, serveur arrêté : tenable à dix
comptes, pas à cent, et chaque geste risquait une requête tapée de travers,
sans trace de qui l'avait faite. Un panneau web aurait demandé sa propre
authentification, une colonne de privilège dans `users`, et serait devenu la
cible la plus intéressante du service — celle dont une seule faille donne
tous les comptes.

Or **qui possède le shell possède déjà la base**. La ligne de commande
n'ajoute donc aucune surface d'attaque : elle rend sûrs et traçables des
gestes qu'on faisait déjà, en plus mal.

**Tout geste qui écrit est journalisé**, avec le même journal que le serveur.
Sans ça, « qui a supprimé ce compte ? » n'a pas de réponse — et c'est
précisément la question qu'on pose le jour où ça tourne mal.

**Rien n'est demandé deux fois, sauf ce qui ne se défait pas.** La suppression
d'un compte exige `--confirmer` : elle efface le compte, ses clés, ses projets
en base et les dossiers sur le disque, sans rien qui puisse être rendu.
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime, timezone

from .identity import IdentityStore
from .journal import configurer, court, evenement
from .service import CompilationService, PlatformNotFoundError

JOUR = 24 * 3600


def _date(instant: int | None) -> str:
    if not instant:
        return "—"
    return datetime.fromtimestamp(instant, tz=timezone.utc).strftime("%Y-%m-%d %H:%M")


def _echeance(instant: int | None) -> str:
    """La date, et surtout ce qu'elle veut dire aujourd'hui.

    Une colonne de dates seule oblige à faire la soustraction de tête, sur la
    ligne où l'on décide s'il faut prolonger. Le mot « échu » se lit d'un coup.
    """
    if instant is None:
        return "jamais"
    reste = instant - int(time.time())
    if reste <= 0:
        return f"{_date(instant)} (échu)"
    return f"{_date(instant)} (dans {reste // JOUR} j)"


def _magasin(workspace):
    service = CompilationService(workspace)
    return service, IdentityStore(service.workspace)


def _compte_ou_sortir(magasin: IdentityStore, adresse: str) -> dict:
    compte = magasin.compte_par_adresse(adresse)
    if not compte:
        print(f"Aucun compte pour {adresse!r}.", file=sys.stderr)
        raise SystemExit(1)
    return compte


# ---------------------------------------------------------------------------
# Lectures
# ---------------------------------------------------------------------------

def _comptes(magasin: IdentityStore, _service, args) -> int:
    lignes = magasin.comptes()
    if not lignes:
        print("Aucun compte.")
        return 0
    print(f"{'ADRESSE':38s} {'CRÉÉ':17s} {'PROJETS':>7s} {'CLÉS':>5s} {'CODES':>6s}")
    for ligne in lignes:
        print(f"{ligne['email'][:38]:38s} {_date(ligne['created_at']):17s} "
              f"{ligne['projets']:>7d} {ligne['cles']:>5d} {ligne['codes']:>6d}")
    manquants = [ligne["email"] for ligne in lignes if ligne["codes"] == 0]
    if manquants:
        # Un compte sans code n'a AUCUN moyen de reprendre la main sur un mot
        # de passe perdu. C'est la seule colonne de ce tableau qui annonce une
        # perte de données à venir : elle est répétée en clair.
        print(f"\n{len(manquants)} compte(s) sans code de secours : "
              f"un mot de passe perdu y serait définitif.")
    return 0


def _compte(magasin: IdentityStore, _service, args) -> int:
    compte = _compte_ou_sortir(magasin, args.email)
    print(f"Compte   {compte['email']}")
    print(f"         {compte['id']}")
    print(f"Codes de secours restants : {magasin.count_recovery_codes(compte['id'])}")

    projets = magasin.tous_les_projets(compte["id"])
    print(f"\nProjets ({len(projets)})")
    for projet in projets:
        print(f"  {projet['project_id']}  {projet['name'][:30]:30s} "
              f"{_echeance(projet['expires_at'])}")

    cles = magasin.cles_du_compte(compte["id"])
    vivantes = [cle for cle in cles if not cle["revoked_at"]]
    print(f"\nClés d'API ({len(vivantes)} active(s) sur {len(cles)})")
    for cle in cles:
        etat = "révoquée" if cle["revoked_at"] else "active"
        print(f"  {cle['id']}  {cle['prefix']}…  {cle['name'][:24]:24s} {etat:9s} "
              f"dernier usage {_date(cle['last_used_at'])}")
    return 0


def _projets(magasin: IdentityStore, _service, args) -> int:
    compte = _compte_ou_sortir(magasin, args.compte) if args.compte else None
    projets = magasin.tous_les_projets(compte["id"] if compte else None)
    if not projets:
        print("Aucun projet.")
        return 0
    print(f"{'IDENTIFIANT':34s} {'COMPTE':28s} {'NOM':22s} ÉCHÉANCE")
    for projet in projets:
        print(f"{projet['project_id']:34s} {projet['email'][:28]:28s} "
              f"{projet['name'][:22]:22s} {_echeance(projet['expires_at'])}")
    return 0


# ---------------------------------------------------------------------------
# Écritures — toutes journalisées
# ---------------------------------------------------------------------------

def _codes(magasin: IdentityStore, _service, args) -> int:
    """Le geste de dépannage : quelqu'un a perdu son mot de passe ET ses codes.

    C'est la commande la plus puissante du lot — elle donne accès au compte.
    Elle est journalisée pour cette raison précise : une reprise de compte par
    l'exploitant doit laisser une trace qu'on peut relire après coup.
    """
    compte = _compte_ou_sortir(magasin, args.email)
    codes = magasin.create_recovery_codes(compte["id"])
    evenement("codes_regeneres_par_exploitant", compte=court(compte["id"]))
    print(f"Nouvelle série pour {compte['email']} — l'ancienne ne fonctionne plus.")
    print("Ces codes ne seront plus jamais affichés :\n")
    for code in codes:
        print(f"  {code}")
    return 0


def _prolonger(magasin: IdentityStore, _service, args) -> int:
    secondes = None if args.jamais else args.jours * JOUR
    if not magasin.deplacer_echeance(args.projet, secondes):
        print(f"Aucun projet {args.projet!r}.", file=sys.stderr)
        return 1
    evenement("echeance_deplacee", projet=court(args.projet),
              jours=None if args.jamais else args.jours)
    quand = "jamais" if args.jamais else f"dans {args.jours} jours"
    print(f"Projet {args.projet} : expire {quand}.")
    return 0


def _expirer(magasin: IdentityStore, _service, args) -> int:
    """Fait expirer sans effacer : c'est la purge qui nettoiera.

    Effacer ici doublerait le chemin de suppression, et deux chemins finissent
    par diverger — celui qu'on emprunte le moins étant celui qui se casse.
    """
    if not magasin.deplacer_echeance(args.projet, -1):
        print(f"Aucun projet {args.projet!r}.", file=sys.stderr)
        return 1
    evenement("projet_expire_par_exploitant", projet=court(args.projet))
    print(f"Projet {args.projet} marqué échu. La purge le retirera au prochain tour.")
    return 0


def _revoquer(magasin: IdentityStore, _service, args) -> int:
    cle = magasin.revoquer_cle_par_id(args.cle)
    if not cle:
        print(f"Aucune clé active {args.cle!r}.", file=sys.stderr)
        return 1
    evenement("cle_revoquee_par_exploitant", cle=court(args.cle))
    print(f"Clé {cle['name']!r} de {cle['email']} révoquée.")
    return 0


def _supprimer(magasin: IdentityStore, service: CompilationService, args) -> int:
    compte = _compte_ou_sortir(magasin, args.email)
    if not args.confirmer:
        projets = magasin.tous_les_projets(compte["id"])
        print(f"{compte['email']} — {len(projets)} projet(s), "
              f"{len(magasin.cles_du_compte(compte['id']))} clé(s).")
        print("Rien n'a été fait. Ajoutez --confirmer pour effacer "
              "définitivement le compte, ses clés, ses projets et leurs fichiers.")
        return 1
    projets = magasin.delete_user(compte["id"])
    effaces = 0
    for projet in projets:
        try:
            service.delete(projet)
            effaces += 1
        except PlatformNotFoundError:
            continue
    evenement("compte_supprime_par_exploitant", compte=court(compte["id"]),
              projets=len(projets), dossiers=effaces)
    print(f"{compte['email']} supprimé — {len(projets)} projet(s) en base, "
          f"{effaces} dossier(s) sur le disque.")
    return 0


# ---------------------------------------------------------------------------
# Analyse des arguments
# ---------------------------------------------------------------------------

def construire_parseur() -> argparse.ArgumentParser:
    parseur = argparse.ArgumentParser(
        prog="monl-platform admin",
        description="Gestes d'exploitation sur les comptes et les projets.")
    # `--workspace` est déclaré DEUX fois : sur le parseur principal et sur
    # chaque sous-verbe, via un parent commun. Trouvé en l'exécutant — argparse
    # n'accepte une option de premier niveau qu'AVANT le sous-verbe, alors
    # qu'on la tape naturellement à la fin. Refuser la commande pour la place
    # d'un argument, c'est faire chercher une faute là où il n'y en a pas.
    commun = argparse.ArgumentParser(add_help=False)
    # `SUPPRESS` et non `None` : avec un défaut ordinaire, le sous-parseur
    # écrase la valeur donnée AVANT le sous-verbe par son propre défaut, et
    # `admin --workspace X comptes` cesse de marcher. Corriger une position
    # en cassant l'autre n'est pas une correction.
    commun.add_argument("--workspace", default=argparse.SUPPRESS,
                        help="Espace de travail (par défaut MONL_PLATFORM_WORKSPACE).")
    parseur.add_argument("--workspace", default=None, help=argparse.SUPPRESS)
    sous = parseur.add_subparsers(dest="geste", required=True)

    sous.add_parser("comptes", parents=[commun],
                    help="Liste tous les comptes.").set_defaults(faire=_comptes)

    detail = sous.add_parser(
"compte", parents=[commun], help="Détail d'un compte : projets et clés.")
    detail.add_argument("email")
    detail.set_defaults(faire=_compte)

    liste = sous.add_parser(
"projets", parents=[commun], help="Liste les projets.")
    liste.add_argument("--compte", default=None, metavar="EMAIL")
    liste.set_defaults(faire=_projets)

    codes = sous.add_parser(
"codes", parents=[commun], help="Nouvelle série de codes de secours pour un compte bloqué.")
    codes.add_argument("email")
    codes.set_defaults(faire=_codes)

    prolonger = sous.add_parser(
"prolonger", parents=[commun], help="Repousse l'expiration d'un projet.")
    prolonger.add_argument("projet")
    prolonger.add_argument("--jours", type=int, default=30)
    prolonger.add_argument("--jamais", action="store_true",
                           help="Le projet n'expire plus.")
    prolonger.set_defaults(faire=_prolonger)

    expirer = sous.add_parser(
"expirer", parents=[commun], help="Marque un projet échu ; la purge nettoiera.")
    expirer.add_argument("projet")
    expirer.set_defaults(faire=_expirer)

    revoquer = sous.add_parser(
"revoquer-cle", parents=[commun], help="Révoque une clé d'API par son identifiant.")
    revoquer.add_argument("cle")
    revoquer.set_defaults(faire=_revoquer)

    supprimer = sous.add_parser(
"supprimer-compte", parents=[commun], help="Efface un compte et tout ce qui lui appartient.")
    supprimer.add_argument("email")
    supprimer.add_argument("--confirmer", action="store_true")
    supprimer.set_defaults(faire=_supprimer)

    return parseur


def main(argv: list[str]) -> int:
    configurer()
    args = construire_parseur().parse_args(argv)
    service, magasin = _magasin(args.workspace)
    return args.faire(magasin, service, args)
