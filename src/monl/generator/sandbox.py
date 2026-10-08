"""Coquilles vides des blocs 'custom' (sandbox_ai.py)."""

from string import Template

_CUSTOM_FUNCTION = Template('''def ${name}(context: dict) -> dict:
    """
    Objectif : ${description}
    """
    # TODO:
    return {'message': 'Coquille vide déterministe pour ${name}'}
''')


def _docstring_litterale(texte):
    """Un antislash de la spec reste un antislash dans la docstring émise."""
    return texte.replace("\\", "\\\\")


class SandboxMixin:
    def _generate_ai_sandbox(self):
        """Génère les coquilles à compléter à la main, sans normaliser les octets.

        substitute ne réinterprète pas les dollars/accolades des valeurs ; la
        description est insérée dans une docstring NON raw, donc ses antislashs
        sont doublés : sinon `\\N` ou `\\x` rendent sandbox_ai.py invalide.
        Le SQL reste exclusivement derrière la frontière generator/sql.py.
        """
        sb_lines = ["# BLOCS 'custom' — logique métier à compléter à la main (déterministe)\n"]
        for func in self.custom_functions:
            sb_lines.append(_CUSTOM_FUNCTION.substitute(
                name=func["name"],
                description=_docstring_litterale(
                    func.get("description", "Logique métier custom.").strip()),
            ))
        return "\n".join(sb_lines)
