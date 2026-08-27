"""Les blocs de premier niveau : `ui`, `landing`, `assets`,
`migration`, `capability`.

Forme PLATE pour `section`, `question` et `link` (points 55, 94, 144) : un
sous-bloc indenté aurait ajouté un niveau à la seule grammaire où
l'indentation a déjà coûté deux bugs. L'ORDRE de déclaration est conservé —
dans une FAQ ou un pied de page il porte du sens."""

from lark import Transformer, v_args


@v_args(inline=True)
class BlocsMixin(Transformer):
    """Les blocs de premier niveau : `ui`, `landing`, `assets`,

    HÉRITE DE ``Transformer`` À DESSEIN, et porte son PROPRE ``@v_args``.
    Lark applique ce décorateur en SAUTANT tout nom déjà présent dans la MRO
    au-dessus de la classe décorée : les méthodes d'un mixin nu ne seraient
    donc jamais enveloppées, et recevraient une LISTE d'enfants au lieu
    d'arguments inlinés. Rien ne planterait — le sens du parsing changerait.
    """

    def ui_theme(self, name):
        return {"theme": str(name)}

    def ui_primary(self, name):
        return {"primary": str(name)}

    def ui_order(self, *names):
        return {"order": [str(n) for n in names]}

    def ui_block(self, entity_name, *props):
        merged = {}
        for p in props:
            if p:
                merged.update(p)
        return {"ui": {"entity": str(entity_name), **merged}}

    def landing_mode(self, name):
        return {"mode": str(name)}

    def landing_template(self, string_literal):
        return {"template": str(string_literal).strip('"')}

    def landing_brief(self, string_literal):
        return {"brief": str(string_literal).strip('"')}

    def landing_section(self, titre, corps):
        # Marqueur temporaire : les sections s'ACCUMULENT, alors que les
        # autres clés du bloc s'écrasent. Un simple merge les perdrait
        # toutes sauf la dernière.
        return {"_section": {"title": str(titre).strip('"'),
                             "body": str(corps).strip('"')}}

    def landing_question(self, question, reponse):
        # Même marqueur temporaire que les sections, même raison : les
        # questions s'ACCUMULENT là où les autres clés s'écrasent.
        return {"_question": {"question": str(question).strip('"'),
                              "answer": str(reponse).strip('"')}}

    def landing_link(self, libelle, adresse):
        # Même marqueur temporaire que les sections et les questions : les
        # liens s'ACCUMULENT là où les autres clés s'écrasent.
        return {"_link": {"label": str(libelle).strip('"'),
                          "url": str(adresse).strip('"')}}

    def landing_block(self, *props):
        merged, sections, faq, links = {}, [], [], []
        for p in props:
            if not p:
                continue
            if "_section" in p:
                sections.append(p["_section"])
            elif "_question" in p:
                faq.append(p["_question"])
            elif "_link" in p:
                links.append(p["_link"])
            else:
                merged.update(p)
        if sections:
            merged["sections"] = sections
        # L'ORDRE DE DÉCLARATION est conservé : dans une FAQ il porte du sens
        # (on répond d'abord à ce qu'on demande le plus), et rien ne permet de
        # le retrouver après coup.
        if faq:
            merged["faq"] = faq
        # Même raison que la FAQ : dans un pied de page, l'ordre déclaré est
        # celui qu'on veut voir, et rien ne permet de le retrouver après coup.
        if links:
            merged["links"] = links
        return {"landing": merged}

    def assets_dir(self, valeur):
        return {"dir": str(valeur).strip('"')}

    def assets_logo(self, valeur):
        return {"logo": str(valeur).strip('"')}

    def assets_favicon(self, valeur):
        return {"favicon": str(valeur).strip('"')}

    def assets_block(self, *props):
        merged = {}
        for p in props:
            if p:
                merged.update(p)
        return {"assets": merged}

    def rename_migration(self, reference, new_name):
        return {"kind": "rename", "reference": str(reference),
                "new_name": str(new_name)}

    def alter_migration(self, reference, old_type, new_type):
        return {"kind": "alter", "reference": str(reference),
                "from_type": str(old_type), "to_type": str(new_type)}

    def drop_migration(self, reference):
        return {"kind": "drop", "reference": str(reference)}

    def migration_block(self, name, *operations):
        return {"migration": {"name": str(name),
                               "operations": list(operations)}}

    def capability_identifier(self, *formes):
        return {"identifier": [str(f) for f in formes]}

    def capability_phone_prefix(self, valeur):
        return {"phone_prefix": str(valeur).strip('"')}

    def capability_lockout(self, maximum, fenetre):
        return {"lockout": {"max_attempts": int(maximum),
                             "window_seconds": int(fenetre)}}

    def capability_password_reset(self, duree):
        return {"password_reset": int(duree)}

    def capability_refresh_tokens(self, duree):
        return {"refresh_tokens": int(duree)}

    def capability_totp(self):
        return {"totp": True}

    def capability_provider(self, nom):
        # Minuscules dès le parsing : 'FedaPay' et 'fedapay' sont le même
        # prestataire, et laisser passer les deux ferait deux specs pour une
        # seule intention (même raison que pour la devise).
        return {"provider": str(nom).lower()}

    def capability_currency(self, code):
        # Normalisé en majuscules dès le parsing : 'xof' et 'XOF' sont le même
        # code ISO, et laisser passer les deux ferait deux specs différentes
        # pour une seule intention.
        return {"currency": str(code).upper()}

    def capability_block(self, name, *props):
        # Le bloc indenté étant optionnel, Lark passe None quand il est absent :
        # une capacité sans propriété reste exactement ce qu'elle était.
        options = {}
        for p in props:
            if p:
                options.update(p)
        return {"capability": {"name": str(name), **options}}
