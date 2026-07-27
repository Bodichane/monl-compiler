"""Coquilles vides des blocs 'custom' (sandbox_ai.py).

Extrait de l'ancien module monolithique src/generator.py (1307 lignes)
lors du découpage en package — voir docs/design_decisions.md.
"""


class SandboxMixin:
    def _generate_ai_sandbox(self):
        """Génère les coquilles vides des blocs 'custom' — logique métier
        à écrire à la main dans ce module (aucune IA ne les remplit)."""
        sb_lines = ["# BLOCS 'custom' — logique métier à compléter à la main (déterministe)\n"]
        for func in self.custom_functions:
            name = func["name"]
            desc = func.get("description", "Logique métier custom.").strip()
            sb_lines.append(f"def {name}(context: dict) -> dict:\n    \"\"\"\n    Objectif : {desc}\n    \"\"\"\n    # TODO:\n    return {{'message': 'Coquille vide déterministe pour {name}'}}\n")
        return "\n".join(sb_lines)
