"""Which routes to write, and in what order."""

class OrchestrationRoutesMixin:
    """Which routes to write, and in what order."""

    def _generate_route_lines(self):
        """Assembles the route families in a stable order."""
        api_lines = ["# --- JWT ACCESS-CONTROL ENFORCEMENT AND PERSISTENCE ---"]
        api_lines.extend(self._generate_crud_and_action_route_lines())
        api_lines.extend(self._generate_upload_route_lines())
        api_lines.extend(self._generate_payment_routes())
        api_lines.extend(self._generate_postpayment_routes())
        return api_lines

    def _generate_crud_and_action_route_lines(self):
        """Renders the routes coming from workflows: CRUD and ``Execute``.

        The payment and post-payment families are deliberately outside this
        method: they come from dedicated business rules and are assembled by
        ``_generate_route_lines`` with the same list of plans."""
        api_lines = []

        # FIX (post-v6): routes are now grouped by (action type, target) pair,
        # and
        # no longer generated once per workflow. Reason: before this fix, two
        # different workflows targeting the same action on the same entity
        # (e.g. two
        # actors allowed to "Delete Post" through a 'sharedBy' rule) produced
        # two
        # FastAPI route definitions on the same path
        # ('@app.delete("/post/{id}")'
        # twice) — only the first declared one stayed reachable, the second was
        # silently shadowed, and its actor got a 403 despite a valid spec. The
        # grouping below merges the allowed actors into a single access check
        # per
        # route, listing every legitimate actor.
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
