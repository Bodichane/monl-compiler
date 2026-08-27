"""Le brief remis à l'IA d'interface.

POINT 72 : le compilateur ne décide RIEN du visuel — ni palette, ni
typographie, ni rayon. La direction vient du DIALOGUE et voyage par ici. Ne
pas y réintroduire de suggestion « facultative » : elle oriente quand même."""

from ..design_skills import render_skill_block
from . import marqueurs, roles_de_champs


def _render_prompt(contract):
    routes_lines = []
    skills_block = render_skill_block(contract.get("design_skills", ["monl-showcase"]))
    for r in contract["routes"]:
        if not r["auth_required"]:
            auth = "public"
        elif r["allowed_actors"]:
            auth = f"JWT ({', '.join(r['allowed_actors'])})"
        else:
            # Point 74 : le webhook de paiement est authentifié, mais pas par
            # un JWT — par une signature du prestataire. Annoncer « JWT () »
            # laisserait croire à une route ouverte à tout compte connecté.
            auth = "signature du prestataire, pas un JWT"

        # Le corps attendu n'apparaissait NULLE PART dans le brief : l'IA
        # devait le déduire de la liste des champs, sans jamais voir les
        # colonnes de rattachement (article_id d'un commentaire). Elle ne
        # pouvait pas les deviner, et le serveur répondait 422 (point 57).
        corps = (f" — corps : `{{{', '.join(r['request_fields'])}}}`"
                 if r.get("request_fields") else "")
        if r.get("upload"):
            upload = r["upload"]
            corps = (f" — multipart/form-data, champ fichier `{upload['field_name']}`, "
                     f"{upload['max_bytes']} octets maximum, types : "
                     f"{', '.join(upload['accepted_types'])}")
        # Point 74 : les notes de route existaient dans le contrat JSON mais
        # n'atteignaient PAS le brief — or c'est le brief que l'IA lit. La
        # forme de la réponse paginée y manquait depuis toujours, et la
        # marche à suivre du règlement y aurait manqué de même.
        note = f" — {r['note']}" if r.get("note") else ""
        routes_lines.append(f"- `{r['method']} {r['path']}` — {r['action']} "
                            f"{r['entity']} — {auth}{corps}{note}")
    entities_lines = []
    ROLE_LABELS = {"title": "TITRE — l'identifie d'un coup d'œil",
                   "media": "MÉDIA — l'image de l'enregistrement",
                   "description": "DESCRIPTION — le texte long",
                   "price": "PRIX",
                   "stock": "DISPONIBILITÉ — à montrer près du prix, pas en note de bas de page",
                   "category": "CATÉGORIE — bon pour un filtre",
                   "meta": "méta — information secondaire"}
    for ent, spec in contract["entities"].items():
        flags = []
        for f in spec["fields"]:
            marks = []
            if f.get("role"):
                marks.append(ROLE_LABELS[f["role"]])
            if f["required"]:
                marks.append("requis")
            if f["hidden_in_reads"]:
                marks.append("jamais renvoyé en lecture")
            if f["server_generated"]:
                marks.append("généré serveur — NE PAS envoyer")
            if f.get("postpayment_only"):
                marks.append("modifiable uniquement via la route après paiement")
            if f.get("upload"):
                upload = f["upload"]
                marks.append(
                    f"Upload multipart via POST/GET sur le champ `{upload['field_name']}`, "
                    f"{upload['max_bytes']} octets maximum ; types : "
                    f"{', '.join(upload['accepted_types'])}. Ne pas l'envoyer en JSON.")
            if f["categorized_in_reads"]:
                marks.append("lu comme libellé de catégorie")
            # BRIQUE 19 (point 96) : l'IA lit le brief, pas le JSON. Y écrire la
            # liste, c'est la différence entre un menu déroulant et un champ
            # texte qui récolte un 422 sur la valeur que l'utilisateur invente.
            if f.get("allowed_values"):
                marks.append("MENU DÉROULANT, valeurs imposées (422 sinon) : "
                             + ", ".join(f"« {v} »" for v in f["allowed_values"]))
            # Point 76 : dire à quoi sert le champ, pas seulement qu'il existe.
            # Sans les valeurs possibles, l'IA doit deviner quoi comparer pour
            # savoir si c'est réglé — et devinera 'paid'.
            if f.get("note"):
                marks.append(f["note"])
            suffix = f" ({'; '.join(marks)})" if marks else ""
            flags.append(f"  - `{f['name']}: {f['type']}`{suffix}")
        forme = roles_de_champs.ARCHETYPE_GUIDANCE[spec["archetype"]]
        anatomie = roles_de_champs.ARCHETYPE_ANATOMY[spec["archetype"]]
        attendus = "\n".join(f"  - {a}" for a in anatomie["attendus"])
        # POINT 88 : les colonnes de liaison sortent dans les réponses (SELECT *)
        # mais n'apparaissaient QUE dans le JSON. Or c'est ici que se joue la
        # jointure la plus facile à rater — celle qui rattache un enregistrement
        # à son titulaire — et une page d'administration ne fait presque que ça.
        liaisons = ""
        if spec["foreign_keys"]:
            lignes_liens = [
                f"  - `{li['column']}` → "
                + (f"identifiant de COMPTE. Retrouver la fiche {li['references']} "
                   f"dont `{li['column']}` porte la MÊME valeur — pas celle dont "
                   f"`id` la porte." if li["references_account"]
                   else f"`id` d'un enregistrement {li['references']}.")
                for li in spec["foreign_keys"]
            ]
            liaisons = ("\nColonnes de liaison présentes dans les réponses :\n"
                        + "\n".join(lignes_liens))
        entities_lines.append(
            f"### {ent}\n_Forme conseillée : {forme}._\n"
            f"_Proche de : {anatomie['voisins']}._\n"
            f"Ce qu'un visiteur s'attend à y trouver :\n{attendus}\n"
            + "\n".join(flags) + liaisons)

    brief_line = (f"\n**Brief produit :** {contract['brief']}\n" if contract.get("brief") else "")

    # Contenu éditorial (point 55). Écrit en toutes lettres que ce texte doit
    # être RENDU tel quel : c'est du contenu, pas une consigne de style, et
    # rien d'autre dans le contrat n'en fournit.
    sections_block = ""
    if contract.get("sections"):
        corps = "\n\n".join(f"### {s['title']}\n{s['body']}"
                            for s in contract["sections"])
        sections_block = (
            "\n## Contenu éditorial à publier tel quel\n"
            "Ces textes sont fournis par l'auteur du projet : ils doivent "
            "apparaître dans l'interface, chacun dans sa propre section, avec "
            "le titre donné et son propre élément portant "
            "`data-monl-section=\"<slug>\"`. Ne pas les réécrire, ne pas les "
            "inventer ailleurs — aucune route d'API ne les sert, ils "
            "n'existent qu'ici. Si le pattern editorial est présent, le bloc "
            "éditorial porte ces éléments à l'intérieur de lui : ne pas créer "
            "ensuite un second bloc qui répète le même titre ou le même texte. "
            "Chaque section doit apparaître une seule fois.\n\n"
            # Point 59 : sans cette phrase, ces textes finissaient derrière un
            # lien de menu, sur une page à part. Un visiteur qui n'ouvre que
            # l'accueil ne les voyait jamais — pour un « à propos », c'est
            # manquer sa raison d'être.
            "**Sur la page d'accueil, pas seulement derrière un lien.** Chaque "
            "section doit être lisible au fil de l'accueil. Un texte long peut "
            "y figurer en version courte et se prolonger sur sa propre page, "
            "mais il ne doit jamais en être absent.\n\n"
            + corps + "\n")

    # POINT 94 : la FAQ, dite comme une LISTE. Rendue dans la même rubrique que
    # les sections, elle redevenait un pavé de prose — c'est exactement le
    # défaut constaté sur SneakerLab, où quatre questions tenaient dans une
    # seule chaîne et sortaient collées en un paragraphe. L'interface était
    # fidèle : c'est le contrat qui ne savait pas dire « questions/réponses ».
    faq_block = ""
    if contract.get("faq"):
        couples = "\n\n".join(f"**{q['question']}**\n{q['answer']}"
                              for q in contract["faq"])
        faq_block = (
            "\n## Questions fréquentes — une LISTE, pas un texte suivi\n"
            "Chaque couple ci-dessous est une question et sa réponse, dans "
            "l'ordre voulu par l'auteur. Les rendre comme des entrées "
            "DISTINCTES et repérables au premier coup d'œil — accordéon, liste "
            "de définitions, ou question en gras suivie de sa réponse. Jamais "
            "en un seul paragraphe : une FAQ dont les questions se touchent ne "
            "se lit pas, et c'est le format qui porte l'information autant que "
            "le texte.\n\n"
            "Ne pas réécrire ces textes, ne pas en ajouter, ne pas les "
            "réordonner.\n\n"
            + couples + "\n")
    # POINT 72 — monl ne décide RIEN du visuel. Il ne calculait pas une
    # palette pour rendre service : il la calculait pour que deux projets ne
    # se ressemblent pas (point 20). Mais ce que le compilateur devine du
    # goût d'un projet, il le devine mal — et une suggestion posée dans le
    # contrat pèse, même annoncée comme facultative. La seule direction
    # légitime est celle que l'auteur a formulée lui-même, dans le dialogue :
    # elle voyage dans le brief, pas dans un bloc de couleurs inventé.
    design_block = """## Direction de design — elle ne vient PAS de monl

Le compilateur n'a **aucun** avis sur le visuel : ni palette, ni typographie,
ni rayon, ni grille, ni mise en page. Il n'en propose pas davantage qu'il n'en
impose — il ne sait pas à quoi ce projet doit ressembler, et il ne fait pas
semblant de le savoir.

La direction est celle que l'auteur a formulée : le **brief** ci-dessus
(intention, registre, place des images), la forme conseillée de chaque entité,
le contenu éditorial. C'est cela qu'il faut servir. Pour le reste — familles
typographiques, gamme chromatique, échelles, rythme, surfaces sombres ou
claires — la décision vous appartient entièrement, c'est votre métier.

Deux exigences seulement, et ce ne sont pas des questions de goût :
- **Contraste** : au moins 4,5:1 entre un texte et son fond (WCAG AA), 3:1
  pour les grands titres. Une interface illisible n'est pas un parti pris.
- **Autonomie** : tout vit dans `frontend/`, aucune ressource distante (voir
  les règles ci-dessous). Les familles déjà présentes sur les machines
  suffisent à porter une identité — c'est leur traitement qui la fait.
"""

    generated_assets_block = """
## Images matricielles produites par la construction

Si `ASSET_MANIFEST.json` liste des `generated_assets`, Monl a déjà écrit ces
images matricielles dans le dossier d'assets déclaré par la spec avant votre
appel. Référencer exactement chaque chemin fourni par le manifeste depuis le
HTML/CSS : ne jamais inventer un nom, ne pas recopier une image dans
`frontend/` et ne pas tenter de produire ses octets dans la réponse texte.
Chaque fichier généré doit être rendu une seule fois, dans le bloc qui porte
son rôle visuel ; ne jamais réutiliser son chemin dans un autre bloc. La
rubrique « Assets graphiques produits par la construction » de
`DESIGN_SYSTEM.md` donne, lorsqu'il y en a, le fichier, son rôle et la
précision de section correspondante.
"""

    express_block = ""
    if "mode express" in (contract.get("brief") or "").lower():
        express_block = """
## Mode express — compléter la matière éditoriale et visuelle

L'auteur a volontairement fourni un brief court. À partir de celui-ci et de
la catégorie décrite par le contrat :
- rédiger les textes d'interface et de présentation nécessaires (accroche,
  bénéfices, méthode, réassurance, appels à l'action, textes d'états vides) ;
- construire une page dense en blocs réellement utiles, pas une simple liste
  suivie d'un formulaire ;
- rendre les vraies images et les vraies fiches renvoyées par l'API quand elles
  existent. Ne jamais fabriquer côté navigateur de faux produits, projets,
  rendez-vous ou autres enregistrements qui contrediraient la base.

Cette liberté concerne la rédaction et la présentation seulement. Elle
n'autorise aucune route, donnée métier, permission ou promesse absente du
contrat.
"""

    # POINT 74 : la note de la route le dit déjà, mais c'est ici que l'IA lit
    # ce qui n'est pas négociable. Le règlement est le seul parcours du
    # frontend où une erreur d'interface coûte de l'argent — il mérite sa
    # ligne, pas seulement une mention dans l'inventaire des routes.
    paiement = [r for r in contract["routes"] if r["action"] == "Pay"]
    paiement_block = ""
    if paiement:
        chemins = ", ".join(f"`{r['path']}`" for r in paiement)
        paiement_block = (
            f"\n- Règlement : {chemins} s'appelle **sans aucun corps** — le "
            "montant vient de la base, pas de vous. Rediriger ensuite le "
            "navigateur vers l'`url` renvoyée. Ne JAMAIS appeler "
            "`POST /paiement/webhook` : c'est la route du prestataire, elle "
            "exige une signature et refusera toute requête du navigateur.")

    identifiant_note = contract["api"]["auth"]["register"].get("note")
    identifiant_block = (f"\n- {identifiant_note}" if identifiant_note else "")
    auth_features = contract["api"]["auth"].get("features") or {}
    auth_feature_lines = []
    if "account_lockout" in auth_features:
        lockout = auth_features["account_lockout"]
        auth_feature_lines.append(
            f"- Verrouillage de compte : après {lockout['max_attempts']} échecs "
            f"dans {lockout['window_seconds']} s, afficher l'échec générique "
            "sans tenter de deviner si l'adresse existe.")
    if "password_reset" in auth_features:
        reset = auth_features["password_reset"]
        auth_feature_lines.append(
            f"- Réinitialisation : afficher les deux écrans "
            f"{reset['request_path']} puis {reset['confirm_path']}. "
            "La première réponse est volontairement générique ; le jeton reçu "
            "par le canal de message se rejoue dans le second écran une seule fois "
            "avant expiration.")
    if "refresh_tokens" in auth_features:
        refresh = auth_features["refresh_tokens"]
        auth_feature_lines.append(
            f"- Session : stocker et rejouer le jeton opaque refresh_token sur "
            f"{refresh['path']} ; chaque succès le remplace. Ne jamais l'envoyer "
            "comme Authorization: Bearer, qui reste réservé au JWT d'accès.")
    if "totp" in auth_features:
        totp = auth_features["totp"]
        auth_feature_lines.append(
            f"- Double facteur : proposer l'activation via {totp['setup_path']} "
            f"puis {totp['enable_path']}, et demander totp_code à la connexion "
            "après activation. Un code ne se rejoue pas.")
    auth_feature_block = ("\n" + "\n".join(auth_feature_lines)
                          if auth_feature_lines else "")

    markers_block = marqueurs._required_markers_block(contract)

    return f"""# Brief frontend — {contract['app']} (généré par monl)
{brief_line}
Vous êtes une IA spécialisée en interfaces. Générez le frontend de
l'application **{contract['app']}** en respectant STRICTEMENT le contrat
ci-dessous. Le backend existe déjà et ne doit pas être modifié.

{design_block}{skills_block}{generated_assets_block}{express_block}
## Système de design préparé avant le code

Avant d'écrire le frontend, lire `DESIGN_SYSTEM.md` lorsqu'il est présent :
il contient le pattern de page, les tokens de départ, les anti-patterns et la
checklist UX sélectionnés pour ce projet. Lire aussi `DESIGN_SPEC.md` et
`ASSET_MANIFEST.json` lorsqu'ils existent. Ces documents orientent la
composition ; le contrat ci-dessous reste l'autorité pour les routes, les
données, les permissions et les états métier.

## Règles non négociables
- Écrire tous les fichiers dans `frontend/`, avec `frontend/index.html`
  comme point d'entrée (HTML/CSS/JS statiques, aucun build requis).
- Frontend AUTONOME : aucune librairie CDN, aucun script externe — tout le
  JS/CSS vit dans `frontend/` (c'est ce qui rend le smoke test possible).
- Visuels locaux — INTERDICTION EXPLICITE : ne crée, n'écris ni ne référence
  aucun fichier image local qui n'est pas listé par `ASSET_MANIFEST.json`.
  Cette interdiction vaut pour les chemins HTML (`<img src>`), CSS
  (`url(...)`, `background-image`) et JavaScript, y compris dans
  `frontend/` et dans tout dossier d'assets. Pour tout visuel qui n'est pas
  listé par le manifeste, l'alternative autorisée et nommée est d'écrire le
  **SVG EN LIGNE dans le HTML**, dans le bloc qui l'utilise. N'invente donc
  jamais un chemin comme `product/default.svg`, `hero.svg` ou `hero.jpg` ;
  vérifie d'abord la liste du manifeste.
- Iconographie : aucune librairie d'icônes (Font Awesome, Material, Lucide,
  Bootstrap Icons…) n'est atteignable, puisque aucun CDN ne l'est — et une
  police d'icônes distante ne le serait pas davantage. Ce qui FONCTIONNE et est
  servi : le SVG écrit EN LIGNE dans le HTML, et les fichiers `.svg` explicitement
  listés par le manifeste. Les fichiers graphiques non listés restent interdits ;
  monl ne dit pas s'il faut des
  icônes, ni lesquelles, ni dans quel style — il dit seulement par quel moyen
  elles sont possibles, parce que la règle ci-dessus, lue seule, laisse croire
  qu'elles ne le sont pas.
- N'appeler QUE les routes listées plus bas, en chemins RELATIFS —
  `fetch('/entite')`, JAMAIS `fetch('http://127.0.0.1:8000/entite')`. Le
  frontend est servi sur `/site` par le serveur qui porte l'API : l'origine
  est déjà la bonne. Une URL absolue avec un port codé en dur casse au
  premier `monl run --port` et fait échouer le smoke test.
- PLANCHER DE PARCOURS : les workflows déclarés par la spec sont des promesses
  de produit. Pour CHAQUE workflow, livrer au moins une entrée d'interface
  atteignable (écran, bouton, formulaire ou gestionnaire) qui appelle une de
  ses routes ; un simple catalogue ne couvre pas un parcours de commande, de
  compte ou de gestion. Les autres routes appelables du workflow doivent être
  raccordées aux actions qu'elles exposent. La vérification lit les fichiers
  réellement livrés, compte les routes appelées et nomme celles qui ne le sont
  par aucun écran. Les routes de service explicitement interdites par le
  contrat restent hors écran et ne doivent jamais être appelées.
- Authentification : `POST /register` (username, password 8+, actor parmi
  {contract['self_register_actors'] or "AUCUN — inscription fermée, ne pas "
   "construire de formulaire d'inscription"}) → `{{status, user_id}}`,
  `POST /login` → `{{access_token, token_type}}`. Le JWT est dans
  `access_token` — le lire sous CE nom exact, puis l'envoyer en en-tête
  `Authorization: Bearer <access_token>` sur toute route non publique. Lire
  un autre nom ne lève aucune erreur : la requête part avec
  `Bearer undefined` et le serveur répond 401 sans que rien ne dise pourquoi. Les rôles déclarés mais absents de cette liste
  ({[a for a in contract['actors'] if a not in contract['self_register_actors']] or "aucun"})
  sont provisionnés hors ligne : ils se connectent par `/login`, jamais par
  `/register`.{identifiant_block}{auth_feature_block}
- Les routes de liste sont paginées : `?limit=&offset=`, réponse
  `{{status, total, limit, offset, data}}`.
- Ne jamais envoyer un champ marqué « généré serveur » à la création.
- Ne pas modifier `app.py`, `schema.sql`, la spec `.ml` ni les autres
  artefacts monl.{paiement_block}

{sections_block}{faq_block}{markers_block}
## Entités
{chr(10).join(entities_lines)}

## Routes disponibles
{chr(10).join(routes_lines)}

## Contrat machine-lisible complet
Le fichier `frontend_contract.json` (même dossier) contient la version
exhaustive de ce contrat — s'y référer en cas de doute.

---

## Vous lisez ceci dans une conversation (claude.ai, sans clé API) ?
Générez le frontend demandé, puis rendez-le sous une forme téléchargeable :
soit un fichier ZIP contenant les fichiers (index.html à la racine ou dans
un unique sous-dossier), soit un `index.html` AUTONOME (CSS et JS inclus
dans le fichier). L'utilisateur l'installera ensuite avec :
`monl import <fichier téléchargé> <dossier du projet>` — monl
re-vérifiera automatiquement l'ensemble (cohérence + smoke test) et, en cas
d'erreurs, elles vous seront recollées ici pour correction.
"""
