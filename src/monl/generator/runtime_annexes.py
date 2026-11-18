"""Uploads and messaging: two foundations that exist only when declared."""

from string import Template


class AnnexesRuntimeMixin:
    """Uploads and messaging: two foundations that exist only when declared."""

    def _generate_upload_runtime_lines(self):
        """Disk foundation for Uploads, emitted only when the spec carries some.

        The client's file name and its ``Content-Type`` are never used to choose
        the path or the type. The file is written to a temporary file under the
        dedicated root, checked by byte signature, then renamed to a random
        hexadecimal reference."""
        return [
            *Template(r'''# --- CLIENT UPLOAD STORAGE (outside the frontend and artifacts) ---
UPLOADS_ROOT = os.path.abspath(os.environ.get('MONL_UPLOADS_DIR') or '.monl_uploads')
_UPLOAD_SIGNATURES = {
    'image/png': (b'\x89PNG\r\n\x1a\n',),
    'image/jpeg': (b'\xff\xd8\xff',),
    'image/gif': (b'GIF87a', b'GIF89a'),
    'image/webp': (b'RIFF',),
    'application/pdf': (b'%PDF-',),
}
def _detect_upload_type(prefix):
    if prefix.startswith(b'RIFF') and prefix[8:12] == b'WEBP':
        return 'image/webp'
    for _mime, _signatures in _UPLOAD_SIGNATURES.items():
        if any(prefix.startswith(_signature) for _signature in _signatures):
            return _mime
    return None

def _upload_path(table, row_id, field, reference):
    if not isinstance(reference, str) or not re.fullmatch(r'[0-9a-f]{64}', reference):
        return None
    _root = os.path.abspath(UPLOADS_ROOT)
    _path = os.path.abspath(os.path.join(_root, table, str(row_id), field, reference))
    try:
        if os.path.commonpath((_root, _path)) != _root:
            return None
    except ValueError:
        return None
    return _path

def _remove_upload(table, row_id, field, reference):
    _path = _upload_path(table, row_id, field, reference)
    if not _path or not os.path.isfile(_path):
        return True
    try:
        os.unlink(_path)
        return True
    except OSError as _error:
        print(f'⚠️ Upload not removed after deleting the row: {_error}')
        return False

def _save_upload(upload_file, table, row_id, field, max_bytes, accepted_types):
    _reference = secrets.token_hex(32)
    _directory = os.path.join(UPLOADS_ROOT, table, str(row_id), field)
    os.makedirs(_directory, mode=0o700, exist_ok=True)
    _final = _upload_path(table, row_id, field, _reference)
    _temporary = _final + '.part'
    _written = 0
    _prefix = b''
    try:
        with open(_temporary, 'wb') as _output:
            while True:
                _chunk = upload_file.file.read(1024 * 1024)
                if not _chunk:
                    break
                if _written + len(_chunk) > max_bytes:
                    raise HTTPException(status_code=413, detail=f'Fichier trop gros : {max_bytes} octets maximum.')
                if len(_prefix) < 64:
                    _prefix += _chunk[:64 - len(_prefix)]
                _output.write(_chunk)
                _written += len(_chunk)
        _actual_type = _detect_upload_type(_prefix)
        if _actual_type not in accepted_types:
            raise HTTPException(status_code=415, detail='Forbidden file type: byte signature not allowed.')
        os.replace(_temporary, _final)
        return _reference, _written, _actual_type
    except Exception:
        try:
            if os.path.exists(_temporary):
                os.unlink(_temporary)
        except OSError:
            pass
        raise
''').substitute().split("\n"),
        ]

    def _generate_message_runtime_lines(self):
        """Asynchronous sending foundation for a B2 message, emitted on demand."""
        if not self.message_rules_by_trigger:
            return []
        return [
            *Template(r'''# --- MESSAGES SORTANTS (brique B2) ---
MESSAGE_RULES = ${message_rules}
MESSAGE_LOGGER = logging.getLogger('monl.messages')

def _message_header_safe(value, name):
    if not isinstance(value, str) or '\r' in value or '\n' in value:
        raise ValueError(f"{name} contient un saut de ligne interdit")

def _message_body(text):
    return '\n\n'.join(text.split('¶'))

def _envoyer_message(rule, user_id, record_id):
    try:
        _conn = _connect()
        try:
            _row = _conn.execute('SELECT username FROM _monl_users WHERE id = ?',
                                 (user_id,)).fetchone()
        finally:
            _conn.close()
        if not _row:
            raise RuntimeError(f'account {user_id} not found')
        _destinataire = _row[0]
        _message_header_safe(_destinataire, 'The recipient')
        if not _RE_EMAIL.fullmatch(_destinataire):
            raise ValueError('The account does not carry a usable email address')
        _hote = (os.environ.get('MONL_SMTP_HOST') or '').strip()
        if not _hote:
            raise RuntimeError('the environment variable MONL_SMTP_HOST is missing')
        _expediteur = (os.environ.get('MONL_SMTP_FROM') or '').strip()
        if not _expediteur:
            raise RuntimeError('the environment variable MONL_SMTP_FROM is missing')
        _message_header_safe(_expediteur, 'The sender')
        if not _RE_EMAIL.fullmatch(_expediteur):
            raise ValueError('MONL_SMTP_FROM does not carry a usable email address')
        try:
            _port = int(os.environ.get('MONL_SMTP_PORT', '587'))
        except ValueError as _error:
            raise RuntimeError('MONL_SMTP_PORT must be an integer') from _error
        _utilisateur = (os.environ.get('MONL_SMTP_USERNAME') or '').strip()
        _mot_de_passe = os.environ.get('MONL_SMTP_PASSWORD') or ''
        if bool(_utilisateur) != bool(_mot_de_passe):
            raise RuntimeError('MONL_SMTP_USERNAME and MONL_SMTP_PASSWORD must be provided together')
        _courriel = EmailMessage()
        _courriel['From'] = _expediteur
        _courriel['To'] = _destinataire
        _courriel['Subject'] = rule['subject']
        _courriel.set_content(_message_body(rule['body']))
        with smtplib.SMTP(_hote, _port, timeout=5) as _smtp:
            if _utilisateur:
                _smtp.login(_utilisateur, _mot_de_passe)
            _smtp.send_message(_courriel)
        MESSAGE_LOGGER.info('[MONL_MESSAGE] message sent: %s#%s to %s',
                            rule['trigger_entity'], record_id, _destinataire)
    except Exception as _error:
        # The business write is already committed. The failure is
        # deliberately detached from the HTTP response, but never
        # swallowed: the explicit trace lets the operator know the
        # message did not leave, and why.
        MESSAGE_LOGGER.exception('[MONL_MESSAGE] message not sent for %s#%s: %s',
                                 rule.get('trigger_entity'), record_id, _error)

def _declencher_message(entity, user_id, record_id):
    _rule = MESSAGE_RULES.get(entity)
    if not _rule:
        return
    threading.Thread(target=_envoyer_message,
                     args=(_rule, user_id, record_id),
                     daemon=True, name=f'monl-message-{entity.lower()}').start()
''').substitute(message_rules=repr(self.message_rules_by_trigger)).split("\n"),
        ]
