"""Le socle de base de données monté dans app.py, et les téléversements."""

from string import Template

from .runtime_headers import security_headers_lines


class MontageRuntimeMixin:
    """Le socle de base de données monté dans app.py, et les téléversements."""

    def _socle_base_et_uploads(self, api_lines):
        """Le socle de base de données, ses migrations, et les téléversements."""
        if self._condition_identity_needed():
            api_lines.extend([
                *Template(r'''def get_optional_identity(request: Request) -> dict:
    _auth = request.headers.get('authorization') or ''
    if not _auth.lower().startswith('bearer '):
        return {}
    _creds = HTTPAuthorizationCredentials(scheme='Bearer', credentials=_auth[7:].strip())
    try:
        return _decode_and_verify_token(_creds)
    except HTTPException:
        return {}
''').substitute().split("\n"),
            ])
        api_lines.extend(self._generate_database_runtime_lines())
        api_lines.extend([
            *Template(r'''@asynccontextmanager
async def _lifespan(_app: FastAPI):
    try:
        init_db()
        yield
    finally:
        _close_database_pool()
''').substitute().split("\n"),
            # CORRECTIF (bêta 3) : '/docs' et '/openapi.json' publiaient la
            # surface complète de l'API en toutes circonstances. Indispensable
            # en développement, rarement souhaitable en déploiement :
            # MONL_DOCS=off les désactive sans toucher au code généré.
            *Template(r"""_docs_actives = os.environ.get('MONL_DOCS', 'on').lower() != 'off'""").substitute().split("\n"),
            *security_headers_lines(),
            *Template(r'''app = _SecurityFastAPI(title='${app_name} - Secure Core', lifespan=_lifespan,
               docs_url='/docs' if _docs_actives else None,
               redoc_url='/redoc' if _docs_actives else None,
               openapi_url='/openapi.json' if _docs_actives else None)
''').substitute(app_name=self.app_name).split("\n"),

            # Déploiement : CORS est opt-in. Une liste explicite est la seule
            # forme acceptée ; '*' ouvrirait l'API à n'importe quelle origine.
            *Template(r'''_CORS_ORIGINS = [origin.strip() for origin in os.environ.get(
    'MONL_CORS_ORIGINS', '').split(',') if origin.strip()]
if '*' in _CORS_ORIGINS:
    raise RuntimeError(
        "MONL_CORS_ORIGINS refuse l'origine '*' : listez des origines "
        'explicites, séparées par des virgules.'
    )
if _CORS_ORIGINS:
    from fastapi.middleware.cors import CORSMiddleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=${cors_methods},
        allow_headers=['Authorization', 'Content-Type', 'X-Request-ID'],
        expose_headers=['X-Request-ID'],
    )
''').substitute(cors_methods=repr(self._cors_methods())).split("\n"),

            # Healthchecks infra : ils ne sont ni dans les workflows ni dans
            # le contrat frontend. La vivacité ne touche jamais SQLite ; la
            # readiness exécute une seule requête triviale.
            *Template(r'''@app.get('/health', include_in_schema=False)
def health():
    return {'status': 'ok'}

@app.get('/health/ready', include_in_schema=False)
def health_ready():
    conn = None
    try:
        conn = _connect()
        conn.execute('SELECT 1')
        return {'status': 'ready'}
    except Exception:
        raise HTTPException(status_code=503, detail='Service indisponible') from None
    finally:
        if conn is not None:
            conn.close()
''').substitute().split("\n"),

            # Logs structurés opt-in. Aucun corps ni en-tête entrant n'est
            # copié dans le journal ; le chemin est privé de sa query string.
            *Template(r'''_LOG_JSON = os.environ.get('MONL_LOG_FORMAT', '').strip().lower() == 'json'
_REQUEST_ID_RE = re.compile(r'^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$$')
def _request_id(request):
    candidate = request.headers.get('x-request-id', '')
    if _REQUEST_ID_RE.fullmatch(candidate):
        return candidate
    return secrets.token_hex(16)

def _write_request_log(request, request_id, status_code, started):
    print(json.dumps({
        'timestamp': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'method': request.method,
        'path': request.url.path,
        'status_code': status_code,
        'duration_ms': round((time.perf_counter() - started) * 1000, 3),
        'request_id': request_id,
    }, ensure_ascii=False), flush=True)

if _LOG_JSON:
    @app.middleware('http')
    async def _structured_request_log(request: Request, call_next):
        started = time.perf_counter()
        request_id = _request_id(request)
        try:
            response = await call_next(request)
        except Exception:
            _write_request_log(request, request_id, 500, started)
            raise
        response.headers['X-Request-ID'] = request_id
        _write_request_log(request, request_id, response.status_code, started)
        return response
''').substitute().split("\n"),

            # Redirection de la racine vers la documentation Swagger/OpenAPI
            # auto-générée par FastAPI — le seul front que monl fournit
            # encore (pivot, point 41) : l'interface réelle vient de l'IA
            # frontend, servie sur '/site' par 'monl run' (wrapper serve.py).
            *Template(r'''from fastapi.responses import RedirectResponse${upload_response_import}

@app.get('/', include_in_schema=False)
async def root():
    return RedirectResponse(url='/docs')
''').substitute(upload_response_import=', FileResponse' if self.upload_fields else '').split("\n"),
        ])

        if self.upload_fields:
            api_lines.extend(self._generate_upload_runtime_lines())

        api_lines.extend([

            # CORRECTIF (roadmap) : remplacement du modèle "actor/user_id
            # auto-déclarés par le client" par un vrai registre d'utilisateurs
            # (table _monl_users, mot de passe haché avec sel via PBKDF2-
            # HMAC-SHA256, 100 000 itérations — pas de dépendance externe type
            # bcrypt nécessaire). LIMITE ASSUMÉE (prototype) : pas de politique
            # de mot de passe, pas de vérification d'email, pas de récupération
            # de compte — voir docs/design_decisions.md.
            *Template(r'''class RegisterRequest(BaseModel):
    username: str
    password: str
    actor: str
''').substitute().split("\n"),
        ])
        return api_lines
