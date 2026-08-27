"""Les routes de téléversement (brique B1)."""

class UploadsRoutesMixin:
    """Les routes de téléversement (brique B1)."""

    def _generate_upload_route_lines(self):
        """Routes multipart et téléchargement privé des champs Upload."""
        api_lines = []
        for upload in self.upload_fields:
            entity = upload["entity"]
            field = upload["field"]
            table = entity.lower()
            path = f"/{table}/{{id}}/{field}"
            _write_context, write_deps, write_acl = self._upload_access_context(
                "Update", entity)
            write_suffix = f", {write_deps}" if write_deps else ""
            api_lines += [
                f"@app.post({path!r}, tags=['Upload'])",
                f"def upload_{table}_{field}(id: int, upload_file: UploadFile = File(..., alias={field!r}){write_suffix}):",
                *write_acl,
                "    _conn = _connect(); _cursor = _conn.cursor()",
                f"    _cursor.execute('SELECT \"{field}\" FROM \"{table}\" WHERE id = ?', (id,))",
                "    _row = _cursor.fetchone()",
                "    if not _row:",
                "        _conn.close()",
                "        raise HTTPException(status_code=404, detail='Enregistrement introuvable')",
                "    _old_reference = _row[0]",
                "    _new_reference = None",
                "    try:",
                f"        _new_reference, _byte_count, _actual_type = _save_upload(upload_file, {table!r}, id, {field!r}, {upload['max_bytes']}, {upload['accepted_types']!r})",
                f"        _cursor.execute('UPDATE \"{table}\" SET \"{field}\" = ? WHERE id = ?', (_new_reference, id))",
                "        _conn.commit()",
                "    except Exception:",
                "        _conn.rollback()",
                "        _conn.close()",
                "        if _new_reference:",
                f"            _remove_upload({table!r}, id, {field!r}, _new_reference)",
                "        raise",
                "    _conn.close()",
                "    if _old_reference:",
                f"        _remove_upload({table!r}, id, {field!r}, _old_reference)",
                "    return {'status': 'success', 'id': id, 'field': " + repr(field) + ", 'bytes': _byte_count, 'content_type': _actual_type}",
                "",
            ]

            _read_context, read_deps, read_acl = self._upload_access_context(
                "Read", entity)
            read_suffix = f", {read_deps}" if read_deps else ""
            api_lines += [
                f"@app.get({path!r}, tags=['Upload'])",
                f"def read_{table}_{field}(id: int{read_suffix}):",
                *read_acl,
                "    _conn = _connect(); _cursor = _conn.cursor()",
                f"    _cursor.execute('SELECT \"{field}\" FROM \"{table}\" WHERE id = ?', (id,))",
                "    _row = _cursor.fetchone(); _conn.close()",
                "    if not _row or not _row[0]:",
                "        raise HTTPException(status_code=404, detail='Fichier introuvable')",
                f"    _file_path = _upload_path({table!r}, id, {field!r}, _row[0])",
                "    if not _file_path or not os.path.isfile(_file_path):",
                "        raise HTTPException(status_code=404, detail='Fichier introuvable')",
                "    return FileResponse(_file_path, media_type='application/octet-stream', filename='download', headers={'X-Content-Type-Options': 'nosniff'})",
                "",
            ]
        return api_lines
