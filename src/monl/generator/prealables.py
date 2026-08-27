"""Ce qu'il faut DÉJÀ avoir, et qui échappe à une condition.

`requiresOwn` (point 90) et son pendant à la suppression (point 96), plus
les deux exemptions DÉCLARATIVES de `publicWhen` (point 116) — le
superviseur et le propriétaire. `_condition_exemptions` est la source
unique partagée par la route et le runtime."""




class PrealablesMixin:
    """Ce qu'il faut DÉJÀ avoir, et qui échappe à une condition."""

    def _condition_exemptions(self, entity):
        """POINT 116 : QUI échappe à la condition 'publicWhen' de cette entité.

        Rend (superviseurs déclarés, colonnes d'identité du propriétaire).
        Source UNIQUE des deux exemptions : la route de lecture les émet, et
        `runtime.py` s'en sert pour n'écrire la dépendance d'identité
        facultative QUE si au moins une exemption existe — sans quoi une spec
        sans superviseur ni propriétaire porterait une fonction que rien
        n'appelle. Deux calculs séparés finiraient par diverger, et c'est le
        genre d'écart qui rouvre un contrôle d'accès.
        """
        if (entity, "Read") not in self.public_conditions:
            return [], []
        superviseurs = sorted(self.access_supervisors.get(f"{entity}.Read", []))
        proprietaire = sorted(self._identity_fk_columns().get(entity, set()))
        return superviseurs, proprietaire

    def _condition_identity_needed(self):
        """Vrai si au moins une lecture conditionnée porte une exemption."""
        return any(any(self._condition_exemptions(entity))
                   for entity, action in self.public_conditions
                   if action == "Read")

    def _profile_lookup(self, entity):
        """POINT 90 : (table, colonne) où chercher la fiche que 'requiresOwn'
        exige, ou None si la règle ne s'applique pas à cette entité.

        La colonne est celle que la route Create de l'entité EXIGÉE peuple
        depuis le jeton — donc celle qui porte un identifiant de COMPTE. Elle
        vient de `_identity_fk_columns`, source unique de cette distinction
        depuis le point 88 : la retrouver autrement, c'est réécrire la moitié du
        bug que ce point-là a corrigé."""
        requise = self.required_profiles.get(entity)
        if not requise:
            return None
        colonnes = self._identity_fk_columns().get(requise, set())
        if not colonnes:
            return None
        return requise.lower(), sorted(colonnes)[0]

    def _profile_dependents(self, entity):
        """POINT 96 : entités qui EXIGENT une fiche de 'entity' pour exister.

        Pendant exact de `_profile_lookup`, à l'autre bout du cycle de vie.
        `requiresOwn` gardait la CRÉATION et rien d'autre : sur
        `projets/SneakerLab`, supprimer sa fiche client laissait la commande en
        base — une commande en carnet sans destinataire, exactement l'état que
        le point 90 avait été écrit pour empêcher. Le trou se rouvrait par
        l'autre bout.

        Retourne [(table, colonne de compte)] : où chercher les enregistrements
        qui deviendraient orphelins."""
        dependantes = []
        for dependante, requise in sorted(self.required_profiles.items()):
            if requise != entity:
                continue
            colonnes = self._identity_fk_columns().get(dependante, set())
            if not colonnes:
                # Sans colonne d'identité, rien ne relie la dépendante à un
                # compte : on ne devine pas plutôt que de refuser à tort.
                continue
            dependantes.append((dependante, dependante.lower(), sorted(colonnes)[0]))
        return dependantes

    def _profile_account_column(self, entity):
        """Colonne de compte de l'entité EXIGÉE elle-même — pour compter les
        fiches restantes. `requiresOwn` demande « au moins une » : supprimer
        l'avant-dernière est donc légitime, seule la DERNIÈRE est refusée."""
        colonnes = self._identity_fk_columns().get(entity, set())
        return sorted(colonnes)[0] if colonnes else None
