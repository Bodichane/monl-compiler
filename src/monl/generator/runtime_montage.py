"""The database foundation mounted in app.py, and uploads."""

from string import Template

from .runtime_headers import security_headers_lines


class MontageRuntimeMixin:
    """The database foundation mounted in app.py, and uploads."""

    def _socle_base_et_uploads(self, api_lines):
        """The database foundation, its migrations, and uploads."""
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
            # FIX (beta 3): '/docs' and '/openapi.json' published the whole API
            # surface in every circumstance. Essential in development, rarely
            # desirable in deployment: MONL_DOCS=off disables them without
            # touching the generated code.
            *Template(r"""_docs_actives = os.environ.get('MONL_DOCS', 'on').lower() != 'off'""").substitute().split("\n"),
            *security_headers_lines(),
            *Template(r'''app = _SecurityFastAPI(title='${app_name} - Secure Core', lifespan=_lifespan,
               docs_url='/docs' if _docs_actives else None,
               redoc_url='/redoc' if _docs_actives else None,
               openapi_url='/openapi.json' if _docs_actives else None)
''').substitute(app_name=self.app_name).split("\n"),

            # Deployment: CORS is opt-in. An explicit list is the only accepted
            # form; '*' would open the API to any origin.
            *Template(r'''_CORS_ORIGINS = [origin.strip() for origin in os.environ.get(
    'MONL_CORS_ORIGINS', '').split(',') if origin.strip()]
if '*' in _CORS_ORIGINS:
    raise RuntimeError(
        "MONL_CORS_ORIGINS refuses the origin '*': list explicit "
        'origins, separated by commas.'
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

            # Infra healthchecks: they are neither in the workflows nor in the
            # frontend contract. Liveness never touches SQLite; readiness runs
            # a single trivial query.
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

            # Opt-in structured logs. No incoming body or header is copied into
            # the log; the path is stripped of its query string.
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

            # Redirect the root to the Swagger/OpenAPI documentation
            # auto-generated by FastAPI — the only front end monl still
            # provides (pivot, point 41): the real interface comes from the
            # frontend AI, served on '/site' by 'monl run' (serve.py wrapper).
            *Template(r'''from fastapi.responses import RedirectResponse${upload_response_import}

@app.get('/', include_in_schema=False)
async def root():
    return RedirectResponse(url='/docs')
''').substitute(upload_response_import=', FileResponse' if self.upload_fields else '').split("\n"),
        ])

        if self.upload_fields:
            api_lines.extend(self._generate_upload_runtime_lines())

        api_lines.extend([

            # FIX (roadmap): replaced the model of an "actor/user_id
            # self-declared by the client" with a real user registry (table
            # _monl_users, password hashed with a salt through
            # PBKDF2-HMAC-SHA256, 100,000 iterations — no external dependency
            # such as bcrypt needed). ACCEPTED LIMIT (prototype): no password
            # policy, no email verification, no account recovery — see
            # docs/design_decisions.md.
            *Template(r'''class RegisterRequest(BaseModel):
    username: str
    password: str
    actor: str
''').substitute().split("\n"),
        ])
        return api_lines
