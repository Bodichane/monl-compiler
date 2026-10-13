"""Les routes de téléversement (brique B1)."""

from string import Template


class UploadsRoutesMixin:
    """Les routes de téléversement (brique B1)."""

    def _generate_upload_route_lines(self):
        """Routes multipart et téléchargement privé des champs Upload."""
        api_lines = []
        for upload in self.upload_fields:
            entity = upload["entity"]
            field = upload["field"]
            table = entity.lower()
            path = Template(r"""/${table}/{id}/${field}""").substitute(table=table, field=field)
            _write_context, write_deps, write_acl = self._upload_access_context(
                "Update", entity)
            write_suffix = Template(r""", ${write_deps}""").substitute(write_deps=write_deps) if write_deps else ""
            api_lines.extend([
                Template(r"""@app.post(${path}, tags=['Upload'])""").substitute(path=repr(path)),
                Template(r"""def upload_${table}_${field}(id: int, upload_file: UploadFile = File(..., alias=${field_2})${write_suffix}):""").substitute(table=table, field=field, field_2=repr(field), write_suffix=write_suffix),
                *write_acl,
                Template(r"""    _conn = _connect(); _cursor = _conn.cursor()""").substitute(),
                Template(r"""    _cursor.execute('SELECT "${field}" FROM "${table}" WHERE id = ?', (id,))""").substitute(field=field, table=table),
                *Template(r"""    _row = _cursor.fetchone()
    if not _row:
        _conn.close()
        raise HTTPException(status_code=404, detail='Enregistrement introuvable')
    _old_reference = _row[0]
    _new_reference = None
    try:""").substitute().split("\n"),
                Template(r"""        _new_reference, _byte_count, _actual_type = _save_upload(upload_file, ${table}, id, ${field}, ${max_bytes}, ${accepted_types})""").substitute(table=repr(table), field=repr(field), max_bytes=upload['max_bytes'], accepted_types=repr(upload['accepted_types'])),
                Template(r"""        _cursor.execute('UPDATE "${table}" SET "${field}" = ? WHERE id = ?', (_new_reference, id))""").substitute(table=table, field=field),
                *Template(r"""        _conn.commit()
    except Exception:
        _conn.rollback()
        _conn.close()
        if _new_reference:""").substitute().split("\n"),
                Template(r"""            _remove_upload(${table}, id, ${field}, _new_reference)""").substitute(table=repr(table), field=repr(field)),
                *Template(r"""        raise
    _conn.close()
    if _old_reference:""").substitute().split("\n"),
                Template(r"""        _remove_upload(${table}, id, ${field}, _old_reference)""").substitute(table=repr(table), field=repr(field)),
                Template(r"""    return {'status': 'success', 'id': id, 'field': ${field}, 'bytes': _byte_count, 'content_type': _actual_type}""").substitute(field=repr(field)),
                "",
            ])

            _read_context, read_deps, read_acl = self._upload_access_context(
                "Read", entity)
            read_suffix = Template(r""", ${read_deps}""").substitute(read_deps=read_deps) if read_deps else ""
            api_lines.extend([
                Template(r"""@app.get(${path}, tags=['Upload'])""").substitute(path=repr(path)),
                Template(r"""def read_${table}_${field}(id: int${read_suffix}):""").substitute(table=table, field=field, read_suffix=read_suffix),
                *read_acl,
                Template(r"""    _conn = _connect(); _cursor = _conn.cursor()""").substitute(),
                Template(r"""    _cursor.execute('SELECT "${field}" FROM "${table}" WHERE id = ?', (id,))""").substitute(field=field, table=table),
                *Template(r"""    _row = _cursor.fetchone(); _conn.close()
    if not _row or not _row[0]:
        raise HTTPException(status_code=404, detail='Fichier introuvable')""").substitute().split("\n"),
                Template(r"""    _file_path = _upload_path(${table}, id, ${field}, _row[0])""").substitute(table=repr(table), field=repr(field)),
                *Template(r"""    if not _file_path or not os.path.isfile(_file_path):
        raise HTTPException(status_code=404, detail='Fichier introuvable')
    return FileResponse(_file_path, media_type='application/octet-stream', filename='download', headers={'X-Content-Type-Options': 'nosniff'})
""").substitute().split("\n"),
            ])
        return api_lines
