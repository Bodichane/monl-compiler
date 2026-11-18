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
            auth = "provider signature, not a JWT"

        # Le corps attendu n'apparaissait NULLE PART dans le brief : l'IA
        # devait le déduire de la liste des champs, sans jamais voir les
        # colonnes de rattachement (article_id d'un commentaire). Elle ne
        # pouvait pas les deviner, et le serveur répondait 422 (point 57).
        corps = (f" — body: `{{{', '.join(r['request_fields'])}}}`"
                 if r.get("request_fields") else "")
        if r.get("upload"):
            upload = r["upload"]
            corps = (f" — multipart/form-data, file field `{upload['field_name']}`, "
                     f"{upload['max_bytes']} bytes maximum, types: "
                     f"{', '.join(upload['accepted_types'])}")
        # Point 74 : les notes de route existaient dans le contrat JSON mais
        # n'atteignaient PAS le brief — or c'est le brief que l'IA lit. La
        # forme de la réponse paginée y manquait depuis toujours, et la
        # marche à suivre du règlement y aurait manqué de même.
        note = f" — {r['note']}" if r.get("note") else ""
        routes_lines.append(f"- `{r['method']} {r['path']}` — {r['action']} "
                            f"{r['entity']} — {auth}{corps}{note}")
    entities_lines = []
    ROLE_LABELS = {"title": "TITLE — identifies it at a glance",
                   "media": "MEDIA — the record's image",
                   "description": "DESCRIPTION — the long text",
                   "price": "PRICE",
                   "stock": "AVAILABILITY — show it near the price, not as a footnote",
                   "category": "CATEGORY — good for a filter",
                   "meta": "meta — secondary information"}
    for ent, spec in contract["entities"].items():
        flags = []
        for f in spec["fields"]:
            marks = []
            if f.get("role"):
                marks.append(ROLE_LABELS[f["role"]])
            if f["required"]:
                marks.append("required")
            if f["hidden_in_reads"]:
                marks.append("never returned on read")
            if f["server_generated"]:
                marks.append("server-generated — DO NOT send")
            if f.get("postpayment_only"):
                marks.append("editable only through the after-payment route")
            if f.get("upload"):
                upload = f["upload"]
                marks.append(
                    f"Multipart upload via POST/GET on the field `{upload['field_name']}`, "
                    f"{upload['max_bytes']} bytes maximum; types: "
                    f"{', '.join(upload['accepted_types'])}. Do not send it as JSON.")
            if f["categorized_in_reads"]:
                marks.append("read as a category label")
            # BRIQUE 19 (point 96) : l'IA lit le brief, pas le JSON. Y écrire la
            # liste, c'est la différence entre un menu déroulant et un champ
            # texte qui récolte un 422 sur la valeur que l'utilisateur invente.
            if f.get("allowed_values"):
                marks.append("DROPDOWN MENU, fixed values (422 otherwise): "
                             + ", ".join(f"“{v}”" for v in f["allowed_values"]))
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
                + (f"ACCOUNT identifier. Find the {li['references']} record "
                   f"whose `{li['column']}` holds the SAME value — not the one whose "
                   f"`id` holds it." if li["references_account"]
                   else f"`id` of a {li['references']} record.")
                for li in spec["foreign_keys"]
            ]
            liaisons = ("\nLink columns present in responses:\n"
                        + "\n".join(lignes_liens))
        entities_lines.append(
            f"### {ent}\n_Suggested form: {forme}._\n"
            f"_Close to: {anatomie['voisins']}._\n"
            f"What a visitor expects to find there:\n{attendus}\n"
            + "\n".join(flags) + liaisons)

    brief_line = (f"\n**Product brief:** {contract['brief']}\n" if contract.get("brief") else "")

    # Contenu éditorial (point 55). Écrit en toutes lettres que ce texte doit
    # être RENDU tel quel : c'est du contenu, pas une consigne de style, et
    # rien d'autre dans le contrat n'en fournit.
    sections_block = ""
    if contract.get("sections"):
        corps = "\n\n".join(f"### {s['title']}\n{s['body']}"
                            for s in contract["sections"])
        sections_block = (
            "\n## Editorial content to publish as is\n"
            "These texts are supplied by the project's author: they must "
            "appear in the interface, each in its own section, with the given "
            "title and its own element carrying "
            "`data-monl-section=\"<slug>\"`. Do not rewrite them, do not "
            "invent them elsewhere — no API route serves them, they exist "
            "only here. If the editorial pattern is present, the editorial "
            "block carries these elements inside it: do not then create a "
            "second block repeating the same title or text. "
            "Each section must appear only once.\n\n"
            # Point 59 : sans cette phrase, ces textes finissaient derrière un
            # lien de menu, sur une page à part. Un visiteur qui n'ouvre que
            # l'accueil ne les voyait jamais — pour un « à propos », c'est
            # manquer sa raison d'être.
            "**On the home page, not only behind a link.** Each section must "
            "be readable as one scrolls the home page. A long text may appear "
            "there in a short version and continue on its own page, but it "
            "must never be absent from it.\n\n"
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
            "\n## Frequently asked questions — a LIST, not running text\n"
            "Each pair below is a question and its answer, in the order the "
            "author chose. Render them as DISTINCT entries that can be spotted "
            "at a glance — accordion, definition list, or a bold question "
            "followed by its answer. Never as a single paragraph: an FAQ whose "
            "questions run together cannot be read, and the format carries the "
            "information as much as the text.\n\n"
            "Do not rewrite these texts, do not add any, do not reorder "
            "them.\n\n"
            + couples + "\n")
    # POINT 72 — monl ne décide RIEN du visuel. Il ne calculait pas une
    # palette pour rendre service : il la calculait pour que deux projets ne
    # se ressemblent pas (point 20). Mais ce que le compilateur devine du
    # goût d'un projet, il le devine mal — et une suggestion posée dans le
    # contrat pèse, même annoncée comme facultative. La seule direction
    # légitime est celle que l'auteur a formulée lui-même, dans le dialogue :
    # elle voyage dans le brief, pas dans un bloc de couleurs inventé.
    design_block = """## Design direction — it does NOT come from monl

The compiler has **no** opinion on visuals: no palette, no typography, no
radius, no grid, no layout. It suggests none any more than it imposes any — it
does not know what this project should look like, and it does not pretend to.

The direction is the one the author expressed: the **brief** above (intent,
register, place of images), each entity's suggested form, the editorial
content. That is what must be served. For the rest — type families, color
range, scales, rhythm, dark or light surfaces — the decision is entirely
yours; it is your craft.

Only two requirements, and neither is a matter of taste:
- **Contrast**: at least 4.5:1 between a text and its background (WCAG AA),
  3:1 for large headings. An unreadable interface is not a stylistic choice.
- **Self-containment**: everything lives in `frontend/`, no remote resource
  (see the rules below). The families already present on machines are enough
  to carry an identity — it is how they are treated that makes it.
"""

    generated_assets_block = """
## Raster images produced by the build

If `ASSET_MANIFEST.json` lists `generated_assets`, Monl has already written
these raster images into the assets folder declared by the spec before your
call. Reference each path supplied by the manifest exactly from the HTML/CSS:
never invent a name, do not copy an image into `frontend/` and do not try to
produce its bytes in the text response. Each generated file must be rendered
only once, in the block that carries its visual role; never reuse its path in
another block. The "Graphic assets produced by the build" section of
`DESIGN_SYSTEM.md` gives, when there are any, the file, its role and the
matching section detail.
"""

    express_block = ""
    if "express mode" in (contract.get("brief") or "").lower():
        express_block = """
## Express mode — fill in the editorial and visual material

The author deliberately supplied a short brief. From it and from the category
the contract describes:
- write the interface and presentation texts that are needed (hook, benefits,
  method, reassurance, calls to action, empty-state texts);
- build a page dense with genuinely useful blocks, not a bare list followed by
  a form;
- render the real images and the real records returned by the API when they
  exist. Never fabricate in the browser fake products, projects, appointments
  or other records that would contradict the database.

This freedom covers writing and presentation only. It authorizes no route,
business data, permission or promise absent from the contract.
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
            f"\n- Payment: {chemins} is called **with no body at all** — the "
            "amount comes from the database, not from you. Then redirect the "
            "browser to the returned `url`. NEVER call "
            "`POST /paiement/webhook`: it is the provider's route, it requires "
            "a signature and will refuse any request from the browser.")

    identifiant_note = contract["api"]["auth"]["register"].get("note")
    identifiant_block = (f"\n- {identifiant_note}" if identifiant_note else "")
    auth_features = contract["api"]["auth"].get("features") or {}
    auth_feature_lines = []
    if "account_lockout" in auth_features:
        lockout = auth_features["account_lockout"]
        auth_feature_lines.append(
            f"- Account lockout: after {lockout['max_attempts']} failures "
            f"within {lockout['window_seconds']} s, show the generic failure "
            "without trying to guess whether the address exists.")
    auth_feature_lines += _instructions_verification(auth_features)
    if "password_reset" in auth_features:
        reset = auth_features["password_reset"]
        auth_feature_lines.append(
            f"- Password reset: show the two screens "
            f"{reset['request_path']} then {reset['confirm_path']}. "
            "The first response is deliberately generic; the token received "
            "through the message channel is replayed in the second screen only once "
            "before it expires.")
    if "refresh_tokens" in auth_features:
        refresh = auth_features["refresh_tokens"]
        auth_feature_lines.append(
            f"- Session: store and replay the opaque refresh_token on "
            f"{refresh['path']}; each success replaces it. Never send it "
            "as Authorization: Bearer, which stays reserved to the access JWT.")
    if "totp" in auth_features:
        totp = auth_features["totp"]
        auth_feature_lines.append(
            f"- Two-factor authentication: offer activation via {totp['setup_path']} "
            f"then {totp['enable_path']}, and ask for totp_code at sign-in "
            "after activation. A code cannot be replayed.")
    auth_feature_block = ("\n" + "\n".join(auth_feature_lines)
                          if auth_feature_lines else "")

    markers_block = marqueurs._required_markers_block(contract)

    return f"""# Frontend brief — {contract['app']} (generated by monl)
{brief_line}
You are an AI specialized in interfaces. Generate the frontend of the
**{contract['app']}** application, STRICTLY following the contract below.
The backend already exists and must not be modified.

{design_block}{skills_block}{generated_assets_block}{express_block}
## Design system prepared before the code

Before writing the frontend, read `DESIGN_SYSTEM.md` when it is present: it
contains the page pattern, starting tokens, anti-patterns and UX checklist
selected for this project. Also read `DESIGN_SPEC.md` and
`ASSET_MANIFEST.json` when they exist. These documents guide the composition;
the contract below remains the authority for routes, data, permissions and
business states.

## Non-negotiable rules
- Write every file in `frontend/`, with `frontend/index.html` as the entry
  point (static HTML/CSS/JS, no build required).
- SELF-CONTAINED frontend: no CDN library, no external script — all the
  JS/CSS lives in `frontend/` (that is what makes the smoke test possible).
- Local visuals — EXPLICIT BAN: do not create, write or reference any local
  image file that is not listed by `ASSET_MANIFEST.json`. This ban applies to
  HTML paths (`<img src>`), CSS (`url(...)`, `background-image`) and
  JavaScript, including inside `frontend/` and any assets folder. For any
  visual not listed by the manifest, the named, allowed alternative is to
  write the **SVG INLINE in the HTML**, in the block that uses it. So never
  invent a path such as `product/default.svg`, `hero.svg` or `hero.jpg`;
  check the manifest's list first.
- Iconography: no icon library (Font Awesome, Material, Lucide, Bootstrap
  Icons…) is reachable, since no CDN is — and a remote icon font would not be
  either. What WORKS and is served: SVG written INLINE in the HTML, and the
  `.svg` files explicitly listed by the manifest. Unlisted graphic files stay
  forbidden; monl does not say whether icons are needed, nor which ones, nor in
  what style — it only says by what means they are possible, because the rule
  above, read alone, suggests they are not.
- Call ONLY the routes listed below, with RELATIVE paths —
  `fetch('/entity')`, NEVER `fetch('http://127.0.0.1:8000/entity')`. The
  frontend is served at `/site` by the server that carries the API: the
  origin is already right. An absolute URL with a hard-coded port breaks at
  the first `monl run --port` and makes the smoke test fail.
- WORKFLOW FLOOR: the workflows declared by the spec are product promises. For
  EACH workflow, deliver at least one reachable interface entry (screen,
  button, form or handler) that calls one of its routes; a plain catalog does
  not cover an ordering, account or management flow. The workflow's other
  callable routes must be wired to the actions they expose. The check reads
  the files actually delivered, counts the routes called and names those no
  screen calls. Service routes the contract explicitly forbids stay off-screen
  and must never be called.
- Authentication: `POST /register` (username, password 8+, actor among
  {contract['self_register_actors'] or "NONE — registration closed, do not "
   "build a registration form"}) → `{{status, user_id}}`,
  `POST /login` → `{{access_token, token_type}}`. The JWT is in
  `access_token` — read it under THAT exact name, then send it in the
  `Authorization: Bearer <access_token>` header on every non-public route.
  Reading another name raises no error: the request goes out with
  `Bearer undefined` and the server answers 401 with nothing saying why. Roles declared but absent from this list
  ({[a for a in contract['actors'] if a not in contract['self_register_actors']] or "none"})
  are provisioned offline: they sign in through `/login`, never through
  `/register`.{identifiant_block}{auth_feature_block}
- List routes are paginated: `?limit=&offset=`, response
  `{{status, total, limit, offset, data}}`.
- Never send a field marked "server-generated" on creation.
- Do not modify `app.py`, `schema.sql`, the `.ml` spec or the other monl
  artifacts.{paiement_block}

{sections_block}{faq_block}{markers_block}
## Entities
{chr(10).join(entities_lines)}

## Available routes
{chr(10).join(routes_lines)}

## Complete machine-readable contract
The `frontend_contract.json` file (same folder) holds the exhaustive version
of this contract — refer to it when in doubt.

---

## Reading this in a conversation (claude.ai, no API key)?
Generate the requested frontend, then return it in a downloadable form:
either a ZIP file containing the files (index.html at the root or in a single
subfolder), or a SELF-CONTAINED `index.html` (CSS and JS included in the
file). The user will then install it with:
`monl import <downloaded file> <project folder>` — monl will automatically
recheck everything (consistency + smoke test) and, if there are errors, they
will be pasted back here for correction.
"""


def _instructions_verification(auth_features):
    """Parcours de confirmation, sans augmenter la complexité du brief."""
    auth_feature_lines = []
    if "verify_email" in auth_features:
        auth_feature_lines.append(
            "- Warn the user: a new registration on an unconfirmed address replaces the password and resends a message, within the verify_resend quota. "
            "Email confirmation: after /register, show the waiting-for-confirmation state, with no session. "
            "Handle /login 403 detail.code=email_not_verified by offering POST /verify-email/resend "
            "with username; show its generic response even at the limit. The link received opens a screen: "
            "ask for an explicit action, then POST /verify-email with username and token in the body, "
            "never an automatic confirmation by GET. After confirmation, offer /login.")
    return auth_feature_lines
