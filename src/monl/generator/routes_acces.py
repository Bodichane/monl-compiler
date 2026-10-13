"""Le contexte d'accès d'une route : qui peut, et sur quelles lignes.

POINT 108 : tout le SQL de contrôle d'accès passe par `generator/sql.py`.
Ne jamais reconstruire une requête de contrôle par f-string."""

from string import Template

from . import sql


class AccesRoutesMixin:
    """Le contexte d'accès d'une route : qui peut, et sur quelles lignes."""

    def _route_access_context(self, plan):
        """Prépare les invariants de sécurité communs à chaque route."""
        base_target = plan.base_target
        target = plan.target
        tag = plan.tags[0]
        access = self.compilation_plans.access_policies[(base_target, plan.action)]
        allowed_actors = sorted(access.actors)
        is_public = access.public
        if is_public:
            security_check = Template(r"""    pass  # Route publique (règle 'public') : aucune authentification requise""").substitute()
            dependency_injection = ""
        elif len(allowed_actors) == 1:
            security_check = (
                Template(r"""    if current_actor != "${actor}": raise HTTPException(status_code=403, detail="Contrôle d'accès : Rôle ${actor} requis")""").substitute(actor=allowed_actors[0])
            )
            dependency_injection = "current_actor: str = Depends(verify_jwt_and_get_actor)"
        else:
            allowed_set_literal = ", ".join(Template(r'''"${actor}"''').substitute(actor=actor) for actor in allowed_actors)
            security_check = (
                Template(r"""    if current_actor not in {${allowed_set_literal}}: raise HTTPException(status_code=403, detail="Contrôle d'accès : Rôle parmi [${actors}] requis")""").substitute(allowed_set_literal=allowed_set_literal, actors=", ".join(allowed_actors))
            )
            dependency_injection = "current_actor: str = Depends(verify_jwt_and_get_actor)"
        return {
            "base_target": base_target,
            "target": target,
            "tag": tag,
            "access": access,
            "allowed_actors": allowed_actors,
            "is_public": is_public,
            "security_check": security_check,
            "dependency_injection": dependency_injection,
            "dep_suffix": Template(r""", ${dependency_injection}""").substitute(dependency_injection=dependency_injection) if dependency_injection else "",
        }

    def _upload_access_context(self, action, entity):
        """ACL de la ligne pour le dépôt ou la relecture d'un Upload."""
        plan = self.compilation_plans.route_map[(action, entity)]
        context = self._route_access_context(plan)
        access = context["access"]
        dependencies = context["dependency_injection"]
        lines = [context["security_check"]]
        if access.party_fields:
            dependencies = Template(r"""${dependencies}, current_user_id: int = Depends(get_current_user_id)""").substitute(dependencies=dependencies)
            columns = ", ".join(Template(r'''"${column}"''').substitute(column=column) for column in access.party_fields)
            lines.extend([
                Template(r"""    _acl_conn = _connect(); _acl_cur = _acl_conn.cursor()""").substitute(),
                Template(r"""    _acl_cur.execute('SELECT ${columns} FROM "${entity}" WHERE id = ?', (id,))""").substitute(columns=columns, entity=entity.lower()),
                *Template(r"""    _acl_row = _acl_cur.fetchone(); _acl_conn.close()
    if not _acl_row: raise HTTPException(status_code=404, detail='Enregistrement introuvable')""").substitute().split("\n"),
            ])
            supervisors = sorted(access.supervisors)
            if supervisors:
                literal = ", ".join(repr(actor) for actor in supervisors)
                lines.extend([
                    Template(r"""    if current_actor not in {${literal}} and current_user_id not in _acl_row:""").substitute(literal=literal),
                    Template(r"""        raise HTTPException(status_code=404, detail='Fichier introuvable')""").substitute(),
                ])
            else:
                lines.extend([
                    *Template(r"""    if current_user_id not in _acl_row:
        raise HTTPException(status_code=404, detail='Fichier introuvable')""").substitute().split("\n"),
                ])
        elif access.owner_entity:
            check_actor, owner_select = self._owner_lookup_sql(
                entity, access.owner_entity)
            dependencies = Template(r"""${dependencies}, current_user_id: int = Depends(get_current_user_id)""").substitute(dependencies=dependencies)
            lines.extend([
                Template(r"""    if current_actor == ${check_actor}:""").substitute(check_actor=repr(check_actor)),
                Template(r"""        _acl_conn = _connect(); _acl_cur = _acl_conn.cursor()""").substitute(),
                Template(r"""        _acl_cur.execute(${text}, ${sql})""").substitute(text=repr(owner_select.text), sql=sql.params_tuple(owner_select)),
                *Template(r"""        _acl_row = _acl_cur.fetchone(); _acl_conn.close()
        if not _acl_row: raise HTTPException(status_code=404, detail='Enregistrement introuvable')
        if _acl_row[0] != current_user_id:
            raise HTTPException(status_code=404, detail='Fichier introuvable')""").substitute().split("\n"),
            ])
        else:
            raise ValueError(
                Template(r"""Génération : aucune ACL par ligne pour ${entity}.${action} Upload""").substitute(entity=entity, action=action))
        return context, dependencies, lines
