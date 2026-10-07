"""En-têtes du backend compilé, mesurés par de vraies requêtes HTTP."""
import os
import re
import shutil
from pathlib import Path
from urllib.parse import urlsplit

import pytest
import requests

from monl.cli import compile_project
from tests.support.server import uvicorn_server
from tests.test_temoins_securite import SPEC

ROOT = Path(__file__).resolve().parents[1]
HEADERS = {
    'X-Content-Type-Options': 'nosniff',
    'X-Frame-Options': 'DENY',
    'Referrer-Policy': 'strict-origin-when-cross-origin',
}


@pytest.fixture
def project(tmp_path):
    spec = tmp_path / 'spec.ml'
    spec.write_text(SPEC, encoding='utf-8')
    compile_project(str(spec), str(tmp_path))
    shutil.copytree(ROOT / 'demo/frontend', tmp_path / 'frontend')
    # Une erreur non interceptée exerce l'enveloppe EXTERNE à Starlette.
    with (tmp_path / 'serve.py').open('a') as module:
        module.write("\n@app.get('/temoin-500')\ndef crash():\n    raise RuntimeError('temoin')\n")
    return tmp_path


def assert_headers(response):
    for name, value in HEADERS.items():
        assert response.headers.get(name) == value, (response.status_code, name)
    assert "frame-ancestors 'none'" in response.headers['Content-Security-Policy']


def test_api_site_erreurs_et_hsts(project):
    with uvicorn_server(project, module='serve:app') as base:
        for path, status in [('/health', 200), ('/site/', 200), ('/site', 307),
                             ('/absent', 404), ('/note', 401), ('/temoin-500', 500)]:
            response = requests.get(base + path, timeout=10, allow_redirects=False)
            assert response.status_code == status, response.text
            assert_headers(response)
            assert 'Strict-Transport-Security' not in response.headers
            assert 'https://' not in response.headers['Content-Security-Policy']
        for proto in ('https', 'http'):
            response = requests.get(base + '/health', timeout=10,
                                    headers={'X-Forwarded-Proto': proto})
            assert response.status_code == 200
            assert ('Strict-Transport-Security' in response.headers) == (proto == 'https')
            if proto == 'https':
                assert response.headers['Strict-Transport-Security'] == 'max-age=31536000'
        site = requests.get(base + '/site/', timeout=10)
        assert '<script' in site.text and '<style' in site.text
        csp = site.headers['Content-Security-Policy']
        assert "script-src 'self' 'unsafe-inline'" in csp
        assert "style-src 'self' 'unsafe-inline'" in csp


@pytest.mark.parametrize('path', ['/docs', '/redoc'])
def test_documentation_et_ressources_cdn(project, path):
    with uvicorn_server(project, module='serve:app') as base:
        response = requests.get(base + path, timeout=10)
        assert response.status_code == 200
        assert_headers(response)
        csp = response.headers['Content-Security-Policy']
        urls = re.findall(r'(?:src|href)="(https://[^"]+)"', response.text)
        assert len(urls) == 3, urls
        for url in urls:
            assert url in csp or ('https://' + urlsplit(url).netloc) in csp, url
        assert requests.get(base + '/openapi.json', timeout=10).status_code == 200
        if path == '/docs':
            assert 'SwaggerUIBundle' in response.text
            assert "script-src 'self' 'unsafe-inline'" in csp
            assert 'fonts.googleapis.com' not in csp
        else:
            assert 'https://cdn.redoc.ly/redoc/logo-mini.svg' in csp
            assert 'fonts.gstatic.com' in csp
            assert "style-src 'self' 'unsafe-inline'" in csp


def test_desactivation_de_tous_les_headers(project):
    env = dict(os.environ, MONL_SECURITY_HEADERS='off')
    with uvicorn_server(project, module='serve:app', env=env) as base:
        for path in ('/health', '/site/', '/docs', '/temoin-500'):
            response = requests.get(base + path, timeout=10,
                                    headers={'X-Forwarded-Proto': 'https'})
            assert response.status_code == (500 if path == '/temoin-500' else 200)
            for name in (*HEADERS, 'Content-Security-Policy', 'Strict-Transport-Security'):
                assert name not in response.headers, name


def test_site_avec_fichiers_locaux(project):
    frontend = project / 'frontend'
    (frontend / 'index.html').write_text(
        '<link rel="stylesheet" href="styles.css"><script src="app.js"></script>',
        encoding='utf-8')
    (frontend / 'styles.css').write_text('body {color: red}', encoding='utf-8')
    (frontend / 'app.js').write_text('window.siteLoaded = true;', encoding='utf-8')
    with uvicorn_server(project, module='serve:app') as base:
        for file in ('index.html', 'styles.css', 'app.js'):
            response = requests.get(base + '/site/' + file, timeout=10)
            assert response.status_code == 200
            assert response.text == (frontend / file).read_text(encoding='utf-8')
            assert_headers(response)
            csp = response.headers['Content-Security-Policy']
            assert "script-src 'self' 'unsafe-inline'" in csp
            assert "style-src 'self' 'unsafe-inline'" in csp
            assert 'https://' not in csp
