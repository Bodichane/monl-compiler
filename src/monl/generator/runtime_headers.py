"""Global ASGI wrapper, including errors and the mounts added by serve.py."""


def security_headers_lines():
    """Emits the per-path policy with no runtime dependency on the compiler.

    Swagger and ReDoc are allowed by HOST (cdn.jsdelivr.net), never by exact
    URL: FastAPI changes these URLs from one version to the next, and a frozen
    CSP would silently break /docs. The CDN stays confined to /docs and /redoc."""
    source = '''
def _security_csp(path):
    base = "default-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'"
    if path == '/docs':
        return (base + "; script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net"
                "; style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net"
                "; img-src 'self' data: https://fastapi.tiangolo.com/img/favicon.png")
    if path == '/redoc':
        return (base + "; script-src 'self' https://cdn.jsdelivr.net"
                "; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com"
                "; font-src 'self' https://fonts.gstatic.com"
                "; img-src 'self' data: https://fastapi.tiangolo.com/img/favicon.png https://cdn.redoc.ly/redoc/logo-mini.svg"
                "; worker-src 'self' blob:")
    if path == '/site' or path.startswith('/site/'):
        return (base + "; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'"
                "; img-src 'self' data:; font-src 'self' data:")
    if path == '/docs/oauth2-redirect':
        return base + "; script-src 'self' 'unsafe-inline'"
    return base

class _SecurityHeadersMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
        headers = dict(scope.get('headers', []))
        secure = (scope.get('scheme') == 'https' or
                  headers.get(b'x-forwarded-proto', b'').strip().lower() == b'https')
        values = {
            b'x-content-type-options': b'nosniff',
            b'x-frame-options': b'DENY',
            b'referrer-policy': b'strict-origin-when-cross-origin',
            b'content-security-policy': _security_csp(scope['path']).encode('ascii'),
        }
        if secure:
            values[b'strict-transport-security'] = b'max-age=31536000'

        async def security_send(message):
            if message['type'] == 'http.response.start':
                excluded = set(values) | {b'strict-transport-security'}
                message['headers'] = [(key, value) for key, value in message.get('headers', [])
                                      if key.lower() not in excluded] + list(values.items())
            await send(message)

        await self.app(scope, receive, security_send)

class _SecurityFastAPI(FastAPI):
    def build_middleware_stack(self):
        stack = super().build_middleware_stack()
        if os.environ.get('MONL_SECURITY_HEADERS', 'on').strip().lower() == 'off':
            return stack
        # Hors ServerErrorMiddleware : même les réponses 500 portent les en-têtes.
        return _SecurityHeadersMiddleware(stack)
'''
    return source.strip().splitlines() + ['']
