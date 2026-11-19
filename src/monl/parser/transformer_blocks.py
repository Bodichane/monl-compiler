"""The top-level blocks: `ui`, `landing`, `assets`, `migration`,
`capability`.

A FLAT form for `section`, `question` and `link` (points 55, 94, 144): an
indented sub-block would have added a level to the only grammar where
indentation has already cost two bugs. The declaration ORDER is kept — in
a FAQ or a footer it carries meaning."""

from lark import Transformer, v_args


@v_args(inline=True)
class BlocsMixin(Transformer):
    """The top-level blocks: `ui`, `landing`, `assets`,

    INHERITS FROM ``Transformer`` ON PURPOSE, and carries its OWN
    ``@v_args``. Lark applies this decorator by SKIPPING any name already
    present in the MRO above the decorated class: a bare mixin's methods would
    therefore never be wrapped, and would receive a LIST of children instead
    of inlined arguments. Nothing would crash — the meaning of the parse would
    change."""

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
        # Temporary marker: the sections ACCUMULATE, whereas the block's other
        # keys overwrite each other. A plain merge would lose all of them but
        # the last.
        return {"_section": {"title": str(titre).strip('"'),
                             "body": str(corps).strip('"')}}

    def landing_question(self, question, reponse):
        # Same temporary marker as the sections, same reason: the questions
        # ACCUMULATE where the other keys overwrite each other.
        return {"_question": {"question": str(question).strip('"'),
                              "answer": str(reponse).strip('"')}}

    def landing_link(self, libelle, adresse):
        # Same temporary marker as the sections and the questions: the links
        # ACCUMULATE where the other keys overwrite each other.
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
        # The DECLARATION ORDER is kept: in a FAQ it carries meaning (one
        # answers first what is asked most), and nothing allows recovering it
        # afterwards.
        if faq:
            merged["faq"] = faq
        # Same reason as the FAQ: in a footer, the declared order is the one
        # one wants to see, and nothing allows recovering it afterwards.
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

    def capability_verify_email(self, duree):
        return {"verify_email": int(duree)}

    def capability_verify_resend(self, maximum, fenetre):
        return {"verify_resend": {"max_attempts": int(maximum),
                                  "window_seconds": int(fenetre)}}

    def capability_password_reset(self, duree):
        return {"password_reset": int(duree)}

    def capability_refresh_tokens(self, duree):
        return {"refresh_tokens": int(duree)}

    def capability_totp(self):
        return {"totp": True}

    def capability_provider(self, nom):
        # Lowercased at parse time: 'FedaPay' and 'fedapay' are the same
        # provider, and letting both through would make two specs for a single
        # intent (same reason as for the currency).
        return {"provider": str(nom).lower()}

    def capability_currency(self, code):
        # Normalized to uppercase at parse time: 'xof' and 'XOF' are the same
        # ISO code, and letting both through would make two different specs for
        # a single intent.
        return {"currency": str(code).upper()}

    def capability_block(self, name, *props):
        # The indented block being optional, Lark passes None when it is
        # absent: a capability without properties stays exactly what it was.
        options = {}
        for p in props:
            if p:
                options.update(p)
        return {"capability": {"name": str(name), **options}}
