"""Data used to keep the platform guide synchronized with the product."""

from __future__ import annotations

# Les douze types de la grammaire (`TYPE` dans src/monl/parser.py). Un test
# refuse toute divergence, dans les deux sens.
TYPES: list[tuple[str, str]] = [
    ("String", "Texte court sur une ligne : un nom, une référence, une catégorie."),
    ("Text", "Texte long, multi-lignes : une description, un message."),
    ("Integer", "Nombre entier : un stock, une quantité, un compteur."),
    ("Float", "Nombre à virgule, pour ce qui n'est pas un montant."),
    ("Boolean", "Vrai ou faux."),
    ("Date", "Un jour, sans heure."),
    ("DateTime", "Un instant. Le type qu'exige <code>timestamp</code>."),
    ("Email", "Adresse électronique."),
    ("UUID", "Identifiant technique. Pour un numéro qu'un humain lit et dicte, "
             "préférez <code>numbered</code>."),
    ("Money", "Un montant. Distinct de <code>Float</code> : c'est lui que "
              "<code>payable</code> et <code>sumOf</code> attendent."),
    ("Image", "Un fichier LOCAL, déclaré dans le bloc <code>assets</code> et "
              "vérifié présent à la compilation. Indisponible sur cette "
              "plateforme, qui n'accepte aucun téléversement."),
    ("Upload", "Un fichier déposé par le client à l'exécution."),
]

REGLES_ACCES: list[tuple[str, str]] = [
    ("rule Entite.Action ownedBy Acteur",
     "Seul le propriétaire agit. Le filtrage couvre <b>aussi la lecture</b> — "
     "liste et accès direct. La colonne de propriété est peuplée depuis le "
     "jeton à la création, jamais fournie par le client."),
    ("rule Ligne.Action ownedBy Commande",
     "Propriété <b>transitive</b> : cette ligne appartient à qui possède sa "
     "commande. La chaîne doit remonter jusqu'à un compte."),
    ("rule Entite.Action public",
     "Retire l'authentification d'une action précise. Une galerie se lit sans "
     "compte ; l'écriture reste fermée."),
    ("rule Article.Read publicWhen statut \"publie\"",
     "Lecture publique <b>sous condition</b> : liste filtrée, détail en 404. "
     "Appliqué côté API — un contenu masqué ne reste pas lisible par son URL."),
    ("rule Message.Read accessibleBy expediteur_id, destinataire_id",
     "Réservé aux parties que l'enregistrement désigne : c'est la messagerie "
     "privée. Au moins deux colonnes, sinon <code>ownedBy</code> suffit."),
    ("rule Entite.Action sharedBy Role, Autre",
     "Ouvre la même route à plusieurs rôles. Posé sur une action déjà régie "
     "par <code>ownedBy</code> ou <code>accessibleBy</code>, il nomme le "
     "<b>superviseur</b> : il voit et modifie tout, les autres restent chez eux."),
    ("rule Vote.Create oncePer Participant, Entree",
     "Un compte n'agit qu'une fois par cible. L'unicité tient à un index "
     "composite en base, jamais à une vérification applicative — c'est lui qui "
     "protège aussi deux requêtes simultanées."),
    ("rule Commande.Create requiresOwn Fiche",
     "L'appelant doit déjà posséder une fiche pour créer ceci. Répond 409 en "
     "disant quoi créer d'abord : une commande qu'on ne peut attribuer à "
     "personne est inexpédiable."),
]

REGLES_CHAMPS: list[tuple[str, str]] = [
    ("rule Produit.prix min 0",
     "Borne d'entrée, <b>422 avant tout INSERT</b>. Valeur sur les nombres, "
     "longueur sur les textes."),
    ("rule Produit.nom max 120", "La borne haute, même mécanique."),
    ("rule Membre.pseudo unique",
     "Index unique en base : un doublon répond 409, à la création comme à la "
     "modification."),
    ("rule Produit.nom required",
     "Assertion vérifiée : le champ doit exister. Une règle qui désigne un "
     "champ inexistant fait échouer la compilation."),
    ("rule Commande.statut oneOf \"panier\", \"expediee\"",
     "Une valeur parmi une liste, sur un champ texte. Le message d'erreur "
     "énumère les valeurs permises, et le contrat demande un menu déroulant."),
]

REGLES_SERVEUR: list[tuple[str, str]] = [
    ("rule Message.auteur generated",
     "Le serveur écrit un pseudonyme stable par compte. Le champ disparaît du "
     "corps de requête : un champ libre ne garantit aucune identité."),
    ("rule Commande.passeeLe timestamp",
     "Instant de création, ISO 8601 UTC, écrit une fois. Absent des corps de "
     "requête — création <b>et</b> modification : une date qu'on se donne "
     "à soi-même n'atteste de rien."),
    ("rule Commande.reference numbered \"CMD-{YYYY}-{NNNN}\"",
     "Le numéro qu'un humain lit et dicte. Le compteur vit dans une table "
     "système : un numéro n'est jamais réattribué, même après suppression."),
    ("rule Ligne.sousTotal derivedFrom Produit.prix by quantite",
     "Calculé depuis une ligne liée, et <b>recalculé</b> à la modification. "
     "Sans lui, le client écrit le montant qu'on va lui facturer."),
    ("rule Commande.total sumOf Ligne.sousTotal",
     "Somme des lignes enfants, recalculée à chaque écriture — création, "
     "modification <b>et suppression</b>. Jamais ajustée par addition : une "
     "somme qu'on ajuste se désynchronise."),
    ("rule Membre.email hidden",
     "Retiré de toutes les réponses de lecture, pour tout le monde. Reste en "
     "base et reste modifiable."),
    ("rule Message.jaimes categorized: \"discret\" below 10, \"viral\" otherwise",
     "Remplace un nombre par un libellé à la lecture. Le dernier palier est "
     "toujours <code>otherwise</code> : la couverture est totale."),
]

REGLES_COMMERCE: list[tuple[str, str]] = [
    ("rule Ligne.Create decrements Produit.stock by quantite",
     "Décompte <b>la quantité demandée</b>. Un <code>min 0</code> déclaré sur "
     "le stock arme la vérification de disponibilité : sans lui, un compteur "
     "garde le droit de passer sous zéro. Rendu à la suppression."),
    ("rule Jaime.Create increments Message.jaimes by 1",
     "Le symétrique, pour les compteurs."),
    ("rule Commande.total payable",
     "Ouvre <code>POST /commande/{id}/paiement</code> et "
     "<code>POST /paiement/webhook</code>. Le montant est relu <b>en base</b> "
     "à chaque appel — la route n'accepte aucun corps de requête. Exige un "
     "montant calculé par le serveur : un total que le payeur peut écrire "
     "fait échouer la compilation."),
    ("rule Commande.statut \"annulee\" releases Ligne",
     "Atteindre cette valeur rend le stock, une seule fois, et l'état devient "
     "terminal."),
    ("rule Commande.statut writableAfterPayment Vendeur",
     "Un enregistrement réglé se fige. Cette règle rouvre <b>un</b> champ, par "
     "une route dédiée réservée au rôle nommé — jamais au propriétaire."),
]

CONTENU: list[tuple[str, str]] = [
    ("seed Entite", "Jeu de démonstration, écrit une seule fois et seulement "
     "dans une table vide. Une vitrine vide ne se juge pas."),
    ("seed Enfant for Parent.champ \"valeur\"",
     "Rattache l'enfant en désignant son parent par une <b>valeur</b>, jamais "
     "par un rang : un numéro ne se lit pas et se décale à la première insertion."),
    ("landing / brief", "Ce que fait l'application, en une phrase. C'est le "
     "point de départ du brief d'interface."),
    ("section \"Titre\": \"Texte\"",
     "Une rubrique éditoriale. Le séparateur <code>¶</code> y découpe des "
     "paragraphes, la grammaire interdisant le saut de ligne dans une chaîne."),
    ("question \"Q\": \"R\"", "Un couple de FAQ. L'ordre déclaré est conservé."),
    ("capability auth / identifier: email, phone",
     "Contraint la <b>forme</b> de l'identifiant de compte, et surtout le "
     "normalise : sans forme canonique, une majuscule suffit à créer un "
     "second compte. <code>phone_prefix: \"+229\"</code> rend « 97… » et "
     "« +22997… » équivalents."),
    ("actor Client selfRegister",
     "Seuls les rôles ainsi marqués peuvent s'inscrire par "
     "<code>POST /register</code>. Les autres se provisionnent hors ligne avec "
     "le <code>manage.py</code> généré — laisser choisir son rôle à "
     "l'inscription serait une élévation de privilège en un appel HTTP."),
]

ROUTES_API: list[tuple[str, str, str]] = [
    ("GET", "/health", "État du service."),
    ("GET", "/ready", "Disponibilité du stockage persistant."),
    ("GET", "/api/version", "Version du compilateur et du contrat frontend."),
    ("GET", "/api/templates", "Les dix modèles métier du dialogue guidé."),
    ("GET", "/api/examples", "Le catalogue des spécifications d'exemple."),
    ("GET", "/api/examples/{example_id}", "La spécification d'un exemple, en texte."),
    ("GET", "/auth/fournisseurs", "Fournisseurs OAuth réellement configurés."),
    ("POST", "/api/auth/register", "Crée un compte et ouvre une session."),
    ("POST", "/api/auth/login", "Ouvre une session avec email et mot de passe."),
    ("POST", "/api/auth/logout", "Révoque la session du navigateur."),
    ("DELETE", "/api/auth/account", "Supprime le compte, ses clés et ses projets. Exige le mot de passe dans le corps, et l'effacement est irréversible."),
    ("GET", "/api/auth/recovery-codes", "Combien de codes de secours restent utilisables."),
    ("POST", "/api/auth/recovery-codes", "Génère une nouvelle série de huit codes et invalide l'ancienne. Les codes ne sont montrés qu'ici."),
    ("POST", "/api/auth/recover", "Reprend la main sur un compte : adresse, code de secours et nouveau mot de passe. Le code est consommé, toutes les sessions tombent."),
    ("GET", "/api/auth/me", "Compte de la session active."),
    ("GET", "/api/projects", "Projets du compte connecté."),
    ("DELETE", "/api/projects/{project_id}", "Supprime un projet et son archive."),
    ("GET", "/api/keys", "Clés MCP du compte, sans leur secret."),
    ("POST", "/api/keys", "Crée une clé MCP affichée une seule fois."),
    ("DELETE", "/api/keys/{key_id}", "Révoque définitivement une clé MCP."),
    ("POST", "/api/validate", "Parseur et audit réels, sans rien écrire."),
    ("POST", "/api/compile", "Compile et rend un manifeste (201)."),
    ("GET", "/api/projects/{project_id}", "Manifeste et résumé d'une compilation."),
    ("GET", "/api/projects/{project_id}/contract", "Le contrat frontend complet."),
    ("GET", "/api/projects/{project_id}/download", "Archive ZIP, sans le secret JWT."),
    ("POST", "/api/projects/{project_id}/build", "Met une construction en file."),
    ("POST", "/api/projects/{project_id}/builds", "Met une construction en file."),
    ("GET", "/api/projects/{project_id}/builds", "Historique des constructions du projet."),
    ("GET", "/api/projects/{project_id}/builds/{build_id}", "État et coût d'une construction."),
    ("GET", "/api/projects/{project_id}/builds/{build_id}/etapes", "Étapes réellement journalisées."),
    ("POST", "/api/projects/{project_id}/serve", "Démarre le site construit (alias explicite)."),
    ("POST", "/api/projects/{project_id}/start", "Démarre le site construit."),
    ("POST", "/api/projects/{project_id}/stop", "Arrête le site construit."),
    ("GET", "/api/models", "Catalogue des modèles du constructeur."),
    ("GET", "/api/usage", "Consommation de jetons du compte."),
    ("GET", "/api/telechargements", "Artefacts réellement disponibles au téléchargement."),
    ("GET", "/api/telechargements/{name}", "Télécharge un artefact publié."),
    ("GET", "/mcp", "Configuration MCP et gestion des clés d’accès."),
    ("POST", "/mcp", "Transport MCP HTTP, authentifié par clé Bearer."),
]

OUTILS_MCP: list[tuple[str, str]] = [
    ("monl_list_templates", "Découvrir les modèles métier."),
    ("monl_validate_spec", "Les erreurs du vrai parseur et de l'audit."),
    ("monl_compile_backend", "Compiler, et recevoir l'identifiant du projet."),
    ("monl_inspect_contract", "Lire le manifeste et le contrat complet."),
]

LIMITES: list[tuple[str, str]] = [
    ("Aucun téléversement",
     "Une spec déclarant un bloc <code>assets</code> ou un champ "
     "<code>Image</code> est refusée : le compilateur vérifie que le fichier "
     "existe, et rien ici ne permet de le déposer. Utilisez "
     "<code>String</code> pour une adresse distante, ou le compilateur en "
     "local avec <code>monl assets add</code>."),
    ("Pas de dialogue guidé",
     "Le dialogue qui produit une spec par questions est une commande locale "
     "(<code>monl</code>). La plateforme part d'une spécification déjà écrite."),
    ("Rétention bornée",
     "Les projets vivent dans le stockage persistant puis expirent après "
     "30 jours par défaut. Téléchargez l'archive avant cette échéance."),
    ("Compilations isolées et bornées",
     "Chaque compilation tourne dans un sous-processus limité en durée, CPU, "
     "mémoire et fichiers. Les quotas sont persistés et partagés entre workers."),
    ("Le secret ne voyage pas",
     "L'archive ne contient jamais <code>.jwt_secret</code> : le backend en "
     "génère un au premier démarrage, sur la machine qui l'héberge."),
]

