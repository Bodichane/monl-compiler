"""Le jeu de démonstration colle à ce que la personne a demandé.

Chaque modèle du catalogue porte un jeu FIGÉ : toute boutique sortait avec
« Théière Kyoto », « Tasse Duo » et « Thé vert Sencha », quelle que soit la
description — une boulangerie recevait de très beaux textes sur le pain et
vendait des théières. La description n'atteignait que le ``brief``, donc les
TEXTES ; jamais les données.

Le dialogue guidé reste entièrement déterministe : aucune IA, aucun appel
réseau. C'est sa frontière et elle ne bouge pas. La plateforme, elle, appelle
DÉJÀ une IA et tient la description — c'est là que la personnalisation vit,
et nulle part ailleurs.

**Trois décisions.**

*L'IA écrit des LIGNES, jamais la structure.* Elle reçoit le CSV produit par
``monl content export`` et doit rendre le même en-tête ; un en-tête différent
fait refuser sa réponse. Les colonnes viennent donc du compilateur : elle ne
peut ni ajouter un champ, ni en inventer un, ni toucher au schéma.

*Le chemin d'écriture est celui du point 115, sans une ligne de plus.*
``importer_contenu`` remplace les blocs ``seed`` et fait REVALIDER la spec par
le vrai parseur et le vrai validateur. Tous les refus du compilateur
s'appliquent donc à ce qu'une IA vient d'écrire — y compris les bornes de
champ, les types et les rattachements.

*Un échec ne casse jamais la construction.* Réponse illisible, en-tête faux,
type invalide, spec qui ne compilerait plus : le CSV d'origine est restauré et
le jeu du modèle reste en place. Un catalogue générique est un défaut ; une
construction perdue est une facture.
"""

import csv
import io
import os
import re

from monl.content_tool import exporter_contenu, importer_contenu

#: Un bloc par entité, introduit par son nom. Le format demandé est du CSV et
#: non du JSON : c'est déjà celui de `monl content`, et l'emballage JSON d'un
#: texte libre est exactement ce qui cassait au point 148.
_BLOC = re.compile(r"^###\s*(\w+)\s*$(.*?)(?=^###\s*\w+\s*$|\Z)",
                   re.MULTILINE | re.DOTALL)

#: Au-delà, ce n'est plus une démonstration : c'est du remplissage payé au
#: jeton. En deçà d'une ligne, la vitrine s'ouvre vide.
MAX_FICHES = 12


class SeedAIError(Exception):
    """La réponse du modèle est inexploitable — jamais fatale."""


def _sans_cloture(texte):
    """Retire une clôture Markdown éventuelle autour d'un bloc."""
    texte = texte.strip()
    if texte.startswith("```"):
        texte = re.sub(r"^```[a-zA-Z0-9_+-]*\s*\n?", "", texte)
        texte = re.sub(r"\n?```\s*$", "", texte)
    return texte.strip()


def blocs_de_la_reponse(reponse):
    """{entité: texte CSV} — ce que le modèle propose, sans l'avoir validé."""
    trouves = {}
    for nom, corps in _BLOC.findall(reponse or ""):
        corps = _sans_cloture(corps)
        if corps:
            trouves[nom] = corps
    return trouves


def _lignes_valides(texte_csv, colonnes):
    """Refuse tout ce qui ne colle pas exactement à l'en-tête attendu."""
    lecteur = csv.reader(io.StringIO(texte_csv))
    try:
        entete = next(lecteur)
    except StopIteration:
        raise SeedAIError("bloc vide") from None
    if [c.strip() for c in entete] != list(colonnes):
        raise SeedAIError(
            f"en-tête refusé {entete} — attendu exactement {list(colonnes)}")
    lignes = [ligne for ligne in lecteur if any(c.strip() for c in ligne)]
    if not lignes:
        raise SeedAIError("aucune ligne de contenu")
    if len(lignes) > MAX_FICHES:
        lignes = lignes[:MAX_FICHES]
    for ligne in lignes:
        if len(ligne) != len(colonnes):
            raise SeedAIError(
                f"ligne à {len(ligne)} colonnes pour {len(colonnes)} attendues")
    return entete, lignes


def prompt_de_contenu(description, csvs):
    """Le brief du remplacement. Court : il est payé, et il ne décide rien."""
    morceaux = [
        "Tu remplis le CATALOGUE DE DÉMONSTRATION d'un site qui vient d'être "
        "généré. Voici ce que ce site doit être :",
        f"\n    {description.strip()}\n",
        "Ci-dessous, le contenu de démonstration actuel, générique et hors "
        "sujet. Réécris UNIQUEMENT les lignes pour qu'elles correspondent à "
        "cette activité : des noms, des descriptions et des prix crédibles "
        "pour ce métier, en français.",
        "",
        "RÈGLES, toutes impératives :",
        "- rends un bloc par entité, introduit par `### NomDeLEntite` ;",
        "- REPRENDS l'en-tête à l'identique, colonne pour colonne, sans en "
        "ajouter, retirer ni renommer une seule ;",
        "- respecte le type de chaque colonne : un prix est un nombre "
        "décimal, un stock un entier ; jamais de symbole monétaire ;",
        "- laisse VIDE toute colonne d'image : aucun fichier n'existe ;",
        f"- entre 1 et {MAX_FICHES} lignes par entité ;",
        "- du CSV brut, rien d'autre : ni commentaire, ni explication.",
        "",
    ]
    for entite, texte in csvs.items():
        morceaux.append(f"### {entite}")
        morceaux.append(texte.strip())
        morceaux.append("")
    return "\n".join(morceaux)


def personnaliser_le_jeu(spec_path, project_dir, description, provider,
                         say=None, operation="contenu", run_id=None):
    """Réécrit le jeu de démonstration. Rend un rapport, ne lève jamais.

    Le retour dit ce qui a RÉELLEMENT changé — pas ce qui a été tenté.
    """
    dire = say or (lambda *_a: None)
    rapport = {"entites": [], "raison": None}
    if not (description or "").strip():
        rapport["raison"] = "aucune description : rien à personnaliser"
        return rapport

    dossier = os.path.join(project_dir, "content")
    try:
        export = exporter_contenu(spec_path, project_dir)
    except Exception as err:   # un export impossible n'est pas fatal
        rapport["raison"] = f"export impossible : {err}"
        return rapport

    colonnes = {e: infos["colonnes"] for e, infos in export["entites"].items()}
    if not colonnes:
        rapport["raison"] = "aucune entité ne porte de jeu de démonstration"
        return rapport

    originaux = {}
    csvs = {}
    for entite in colonnes:
        chemin = os.path.join(dossier, f"{entite}.csv")
        with open(chemin, encoding="utf-8") as fh:
            originaux[chemin] = fh.read()
        csvs[entite] = originaux[chemin]

    def restaurer():
        for chemin, contenu in originaux.items():
            with open(chemin, "w", encoding="utf-8") as fh:
                fh.write(contenu)

    try:
        reponse = provider(prompt_de_contenu(description, csvs))
    except Exception as err:   # un fournisseur peut lever n'importe quoi
        rapport["raison"] = f"le modèle n'a pas répondu : {err}"
        restaurer()
        return rapport
    finally:
        _journaliser(project_dir, provider, operation, run_id)

    blocs = blocs_de_la_reponse(reponse)
    ecrits = []
    for entite, attendues in colonnes.items():
        if entite not in blocs:
            continue
        try:
            entete, lignes = _lignes_valides(blocs[entite], attendues)
        except SeedAIError as err:
            dire(f" ⚠️  Contenu de {entite} ignoré : {err}")
            continue
        chemin = os.path.join(dossier, f"{entite}.csv")
        with open(chemin, "w", encoding="utf-8", newline="") as fh:
            writer = csv.writer(fh)
            writer.writerow(entete)
            writer.writerows(lignes)
        ecrits.append((entite, len(lignes)))

    if not ecrits:
        rapport["raison"] = "aucun bloc exploitable dans la réponse"
        restaurer()
        return rapport

    try:
        importer_contenu(spec_path, project_dir)
    except Exception as err:
        # La spec n'a PAS été touchée : `importer_contenu` revalide avant
        # d'écrire. On remet seulement les CSV en état.
        rapport["raison"] = f"la spec obtenue ne compilerait pas : {err}"
        restaurer()
        return rapport

    rapport["entites"] = ecrits
    for entite, nombre in ecrits:
        dire(f" -> Contenu de démonstration adapté : {entite}, {nombre} fiche(s).")
    return rapport


def _journaliser(project_dir, provider, operation, run_id):
    """Cet appel coûte : il est compté comme tous les autres."""
    try:
        from monl.frontend_ai import _record_provider_usage

        _record_provider_usage(project_dir, provider, operation, 1,
                               stage="seed", retry=0, run_id=run_id)
    except Exception:   # la mesure ne doit jamais casser l'appel
        pass
