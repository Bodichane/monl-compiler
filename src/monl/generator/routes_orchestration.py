"""Quelles routes écrire, et dans quel ordre."""

class OrchestrationRoutesMixin:
    """Quelles routes écrire, et dans quel ordre."""

    def _generate_route_lines(self):
        """Assemble les familles de routes dans un ordre stable."""
        api_lines = ["# --- ENFORCEMENT DU CONTRÔLE D'ACCÈS PAR JWT ET PERSISTANCE ---"]
        api_lines.extend(self._generate_crud_and_action_route_lines())
        api_lines.extend(self._generate_upload_route_lines())
        api_lines.extend(self._generate_payment_routes())
        api_lines.extend(self._generate_postpayment_routes())
        return api_lines

    def _generate_crud_and_action_route_lines(self):
        """Rend les routes issues des workflows : CRUD et ``Execute``.

        Les familles paiement et post-paiement sont volontairement hors de
        cette méthode : elles naissent de règles métier dédiées et sont
        assemblées par ``_generate_route_lines`` avec la même liste de plans.
        """
        api_lines = []

        # CORRECTIF (post-v6) : les routes sont désormais regroupées par couple
        # (type d'action, cible), et non plus générées une fois par workflow.
        # Raison : avant ce correctif, deux workflows différents visant la même
        # action sur la même entité (ex. deux acteurs autorisés à faire "Delete Post"
        # via une règle 'sharedBy') produisaient deux définitions de route FastAPI
        # sur le même chemin ('@app.delete(\"/post/{id}\")' deux fois) — seule la
        # première déclarée restait effectivement joignable, la seconde était
        # silencieusement masquée, et son acteur recevait un 403 malgré une spec
        # valide. Le regroupement ci-dessous fusionne les acteurs autorisés en un
        # seul contrôle d'accès par route, listant tous les acteurs légitimes.
        route_map = self.compilation_plans.route_map

        for (act_type, _key), plan in route_map.items():
            context = self._route_access_context(plan)

            if act_type == "Create":
                api_lines.extend(self._generate_create_route_lines(
                    plan, context, act_type))
            elif act_type == "Read":
                api_lines.extend(self._generate_read_route_lines(
                    plan, context, act_type))
            elif act_type == "Update":
                api_lines.extend(self._generate_update_route_lines(
                    plan, context, act_type))
            elif act_type == "Delete":
                api_lines.extend(self._generate_delete_route_lines(
                    plan, context, act_type))
            elif act_type == "Execute":
                api_lines.extend(self._generate_execute_route_lines(
                    plan, context, act_type))

        return api_lines
