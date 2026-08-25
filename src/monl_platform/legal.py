"""Conditions d'utilisation et politique de confidentialité.

Deux règles ont guidé l'écriture, et elles se voient dans le texte.

**Rien n'est inventé.** L'éditeur du service — nom, forme juridique, adresse,
contact — n'est pas déductible du code : ces emplacements portent un
marqueur `À COMPLÉTER` bien visible plutôt qu'une identité plausible.
Fabriquer une mention légale serait produire un faux document.

**Ce qui est dit est vérifiable dans le code.** La liste des données
conservées est confrontée au schéma SQLite réel par
`tests/test_platform_legal.py` : une table qui garde de la donnée
personnelle et que la page ne nomme pas fait échouer la suite. Une politique
de confidentialité qui se désynchronise du code est pire qu'absente — elle
affirme.
"""

from __future__ import annotations

from .theme import page

MARQUEUR = "À COMPLÉTER"

EDITEUR = "Itchane Bodi"
CONTACT = "contact@monl.dev"
# Contrairement aux deux constantes ci-dessus, celle-ci est un fait PUBLIC :
# OVH publie sa propre identité légale pour que ses clients la citent. Elle est
# donc renseignée — relevée sur https://www.ovhcloud.com/fr/terms-and-conditions/
# le 26/08/2026, pas écrite de mémoire. Le téléphone ne figure sur aucune des
# pages publiques d'OVH ; la LCEN le demande pour l'hébergeur, il reste donc à
# ajouter si le service relève du droit français.
#
# Précision utile : nommer l'hébergeur n'est PAS une exigence du RGPD, qui
# porte sur l'identité du responsable de traitement et les droits des
# personnes. C'est la LCEN française qui l'impose, et elle s'applique selon
# l'établissement de l'éditeur et le public visé — pas selon le pays du
# serveur. La mention est gardée parce qu'elle ne coûte rien et couvre ce cas.
HEBERGEUR = ("OVH SAS, SAS au capital de 50 000 000 € — "
             "2 rue Kellermann, 59100 Roubaix, France — RCS 424 761 419")


def est_complete() -> bool:
    """Vrai quand les trois emplacements portent une vraie identité."""
    return all(MARQUEUR not in valeur for valeur in (EDITEUR, CONTACT, HEBERGEUR))


def _lignes_manquantes() -> str:
    """Nomme ce qui reste à renseigner, et rien d'autre.

    Un décompte figé (« ces trois emplacements ») enverrait corriger ce qui
    est déjà juste dès qu'une seule valeur manque — même reproche qu'au
    point 97 du compilateur : une hypothèse affichée comme un diagnostic est
    pire qu'un message vague.
    """
    manquants = [nom for nom, valeur in (("l'éditeur", EDITEUR),
                                         ("l'adresse de contact", CONTACT),
                                         ("l'hébergeur", HEBERGEUR))
                 if MARQUEUR in valeur]
    if not manquants:
        return ""
    quoi = manquants[0] if len(manquants) == 1 else (
        ", ".join(manquants[:-1]) + " et " + manquants[-1])
    return (f'<span class="trou">Il reste à renseigner {quoi} avant toute '
            'ouverture au public : ces valeurs ne se déduisent pas du code, '
            'et les inventer produirait un faux.</span>')


MENTIONS = f"""
<section class="shell legal">
<span class="maj">Mentions légales</span>
<h1>Qui édite ce service, qui l'héberge, et comment nous joindre.</h1>

{_lignes_manquantes()}

<h2>Éditeur</h2>
<p>Ce service est édité par <strong>{EDITEUR}</strong>, personne physique,
également directeur de la publication.</p>

<h2>Hébergeur</h2>
<p>Ce service est hébergé par <strong>{HEBERGEUR}</strong>.</p>

<h2>Contact</h2>
<p>Pour toute question sur le service, et pour exercer vos droits sur vos
données, écrivez à <strong>{CONTACT}</strong>.</p>
<p>Aucune autre voie de contact n'existe : le service n'envoie aucun courriel
et ne dispose d'aucun support téléphonique.</p>

<h2>Propriété</h2>
<p>Vous restez propriétaire des spécifications que vous soumettez et des
backends produits à partir d'elles. Le compilateur monl et le code de cette
plateforme relèvent de leur propre licence, publiée avec leur code source.</p>

<h2>Les autres documents</h2>
<ul>
<li><a href="/conditions">Conditions d'utilisation</a> — ce que le service
promet, et ce qu'il ne garantit pas.</li>
<li><a href="/confidentialite">Politique de confidentialité</a> — les données
conservées, leur durée de vie, et comment tout effacer.</li>
</ul>
</section>
"""


CSS = """
.legal { max-width: 74ch; padding-block: var(--space-7) var(--space-8); }
.legal h1 { font-size: clamp(32px, 5vw, 48px); letter-spacing: -.03em; margin-bottom: var(--space-3); }
.legal .maj { color: var(--muted); font: 600 12px var(--mono); letter-spacing: .1em;
              text-transform: uppercase; margin-bottom: var(--space-6); display: block; }
.legal h2 { font-size: 22px; margin: var(--space-7) 0 var(--space-3); letter-spacing: -.02em; }
.legal h3 { font-size: 16px; margin: var(--space-5) 0 var(--space-2); }
.legal p, .legal li { color: var(--muted); }
.legal strong { color: var(--ink); font-weight: 600; }
.legal ul { padding-left: var(--space-5); display: grid; gap: 6px; margin: var(--space-3) 0; }
.legal table { width: 100%; border-collapse: collapse; margin: var(--space-4) 0; font-size: 14px; }
.legal th, .legal td { text-align: left; padding: 10px 12px; border-bottom: 1px solid var(--line);
                       vertical-align: top; }
.legal th { color: var(--ink); font-weight: 600; }
.legal td:first-child { font-family: var(--mono); font-size: 13px; color: var(--ink); white-space: nowrap; }
.legal .trou { display: block; border: 1px dashed var(--line-strong); border-radius: 10px;
               padding: var(--space-4); margin: var(--space-4) 0; background: var(--surface-2);
               color: var(--ink); font-size: 14px; }
.legal .trou b { font-family: var(--mono); font-size: 13px; }
.legal .identite { border-left: 3px solid var(--line-strong); padding-left: var(--space-4);
                   margin: var(--space-4) 0; color: var(--ink); }
.legal .identite b { font-weight: 600; }
@media (max-width: 620px) { .legal td:first-child { white-space: normal; } }
"""

# Ce que chaque table conserve. Le test confronte cette liste au schéma réel :
# ajouter une table sans l'inscrire ici fait échouer la suite.
DONNEES = [
    ("users", "Adresse électronique, empreinte scrypt du mot de passe, date de création.",
     "Tant que le compte existe."),
    ("sessions", "Empreinte SHA-256 du jeton de session, date d'expiration.",
     "30 jours, puis effacement automatique."),
    ("projects", "Identifiant et nom du projet compilé, dates de création et d'expiration.",
     "30 jours par défaut, puis effacement automatique du dossier et de la ligne."),
    ("api_keys", "Nom de la clé, ses treize premiers caractères, empreinte SHA-256, "
                 "date de dernier usage.", "Tant que la clé n'est pas révoquée."),
    ("rate_limits", "Empreinte du compte ou de l'adresse IP, compteur de la fenêtre en cours.",
     "Le temps d'une fenêtre de limitation, au plus une heure."),
]

_LIGNES = "".join(
    f"<tr><td>{table}</td><td>{quoi}</td><td>{duree}</td></tr>"
    for table, quoi, duree in DONNEES
)

CONFIDENTIALITE = f"""
<section class="shell legal">
<span class="maj">Politique de confidentialité</span>
<h1>Ce que le service conserve, et pendant combien de temps.</h1>

<p>Cette page décrit les données réellement enregistrées par la plateforme. Elle est
confrontée au schéma de la base par la suite de tests : une donnée conservée et non
décrite ici fait échouer la construction.</p>

<h2>Les données conservées</h2>
<table>
<thead><tr><th>Où</th><th>Quoi</th><th>Combien de temps</th></tr></thead>
<tbody>{_LIGNES}</tbody>
</table>

<h3>Ce que le service ne fait pas</h3>
<ul>
<li><strong>Aucun mot de passe n'est stocké en clair.</strong> Seule une empreinte
scrypt, avec un sel propre à chaque compte.</li>
<li><strong>Aucun jeton n'est stocké en clair</strong> — ni session, ni clé d'API. Une
clé perdue ne peut pas être retrouvée, seulement révoquée et remplacée.</li>
<li><strong>Aucun traceur, aucune mesure d'audience, aucun cookie publicitaire.</strong>
Le seul cookie déposé est <code>monl_session</code>, strictement nécessaire à la
connexion.</li>
<li><strong>Aucun courriel n'est envoyé.</strong> Votre adresse sert d'identifiant de
connexion, rien d'autre. Elle n'est ni vérifiée, ni utilisée pour vous écrire.</li>
<li><strong>Aucune donnée n'est transmise à un tiers.</strong> Les specs que vous
compilez et les backends produits ne quittent pas le service.</li>
</ul>

<h2>Vos specs et vos backends</h2>
<p>Le texte que vous compilez est écrit sur le disque du serveur le temps de produire
le backend, puis conservé avec le projet. <strong>Le tout est effacé automatiquement à
l'expiration du projet</strong>, sans intervention. Vous pouvez supprimer un projet à
tout moment depuis la console.</p>

<h2>Vos droits</h2>
<p><strong>La suppression est immédiate et complète.</strong> Depuis la page de votre
compte, la suppression efface le compte, ses sessions, ses clés d'API, ses projets en
base <em>et</em> les dossiers correspondants sur le disque. Rien n'est conservé, et
l'opération est irréversible.</p>
<p>Pour l'accès, la rectification, l'opposition ou la portabilité, écrivez à
<strong>{CONTACT}</strong>. Le responsable du traitement est nommé dans les
<a href="/mentions-legales">mentions légales</a>.</p>
<p>Vous pouvez également <strong>introduire une réclamation auprès de l'autorité de
contrôle</strong> de votre pays de résidence si vous estimez que le traitement de vos
données n'est pas conforme.</p>

<h2>Conservation des journaux</h2>
<p>Le service journalise les événements d'exploitation — connexions, compilations,
révocations de clés — pour pouvoir constater un incident. <strong>Ces journaux ne
contiennent aucun mot de passe, aucun jeton et aucune clé</strong> : le composant qui
les écrit masque ces valeurs par construction, qu'elles soient reconnues à leur nom ou
à leur forme.</p>
</section>
"""

CONDITIONS = """
<section class="shell legal">
<span class="maj">Conditions d'utilisation</span>
<h1>Ce que le service promet, et ce qu'il ne promet pas.</h1>

<h2>Le service</h2>
<p>La plateforme compile une spécification Monl en une application complète
(FastAPI, SQLite, JWT). La compilation est <strong>déterministe</strong> : la même
spec produit le même backend, sans intelligence artificielle et sans appel réseau.</p>

<h2>Le compte</h2>
<ul>
<li>Un compte se crée avec une adresse électronique et un mot de passe d'au moins
huit caractères. <strong>L'adresse n'est pas vérifiée</strong>, et aucun courriel
n'est envoyé.</li>
<li><strong>Un mot de passe perdu ne peut pas être réinitialisé</strong>, faute de
courriel : le compte et ses projets seraient alors définitivement inaccessibles.
Conservez-le dans un gestionnaire de mots de passe.</li>
<li>Vous êtes responsable des clés d'API que vous créez. Une clé compromise se révoque
depuis la page dédiée ; elle ne peut pas être relue.</li>
</ul>

<h2>Ce que vous pouvez compiler</h2>
<p>Vous restez propriétaire de vos specs et des backends produits. Il vous appartient
de disposer des droits sur ce que vous soumettez, et de ne pas vous en servir pour
produire un service illicite.</p>
<p>Le service refuse une spec qu'il juge dangereuse ou trop coûteuse à compiler. Les
compilations sont bornées en temps, en mémoire et en taille de sortie, et limitées en
nombre par compte et par heure.</p>

<h2>Ce qui n'est pas garanti</h2>
<ul>
<li><strong>Aucune disponibilité n'est garantie.</strong> Le service peut être
interrompu, à tout moment et sans préavis.</li>
<li><strong>Vos projets sont temporaires.</strong> Ils sont effacés automatiquement
après leur période de rétention. Téléchargez l'archive de ce que vous voulez garder.</li>
<li>Le backend produit est fourni <strong>tel quel</strong>. Sa mise en production,
sa sécurité d'exploitation et la sauvegarde de ses données vous incombent.</li>
</ul>

<h2>Résiliation</h2>
<p>Vous pouvez supprimer votre compte à tout moment depuis la page de votre compte :
l'effacement est immédiat, complet et irréversible. L'éditeur peut suspendre un compte
qui met le service en péril ou en fait un usage illicite.</p>

<h2>Modification</h2>
<p>Ces conditions peuvent évoluer. La version en vigueur est celle publiée sur cette
page.</p>

<h2>Qui édite ce service</h2>
<p>L'éditeur, l'hébergeur et l'adresse de contact sont nommés dans les
<a href="/mentions-legales">mentions légales</a>.</p>
</section>
"""

MENTIONS_HTML = page(
    title="Mentions légales — monl compiler",
    description="Qui édite ce service, qui l'héberge, et comment nous joindre.",
    body=MENTIONS, extra_css=CSS,
)

CONDITIONS_HTML = page(
    title="Conditions d'utilisation — monl compiler",
    description="Ce que le service promet, ce qu'il ne garantit pas, et comment "
                "résilier un compte.",
    body=CONDITIONS, extra_css=CSS,
)

CONFIDENTIALITE_HTML = page(
    title="Confidentialité — monl compiler",
    description="Les données conservées par la plateforme, leur durée de vie, et "
                "comment tout effacer.",
    body=CONFIDENTIALITE, extra_css=CSS,
)
