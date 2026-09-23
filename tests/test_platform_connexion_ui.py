"""Contrats visuels et accessibles de la porte d'entrée de la console."""

from monl_platform.account import AUTH_HTML
from monl_platform.console import CONSOLE_HTML
from monl_platform.landing import GITHUB_URL, LANDING_HTML
from monl_platform.theme import page


def test_la_connexion_expose_les_fournisseurs_reellement_configures():
    assert 'id="oauth-zone"' in AUTH_HTML
    assert "fetch('/auth/fournisseurs')" in AUTH_HTML
    assert 'href="/auth/${encodeURIComponent(provider.name)}"' in AUTH_HTML


def test_le_formulaire_reste_nomme_et_pilotable_au_clavier():
    assert '<label for="email">' in AUTH_HTML
    assert '<label for="password"' in AUTH_HTML
    assert 'autocomplete="current-password"' in AUTH_HTML
    assert 'aria-controls="password"' in AUTH_HTML
    assert 'role="tablist"' in AUTH_HTML
    assert "setAttribute('aria-selected'" in AUTH_HTML
    assert "Connexion annulée" in AUTH_HTML


def test_le_mot_de_passe_oublie_est_un_lien_secondaire_sous_le_formulaire():
    assert 'class="auth-tabs trois"' not in AUTH_HTML
    assert 'id="auth-recovery"' in AUTH_HTML
    assert 'data-mode="recover"' in AUTH_HTML


def test_les_decors_sont_ignores_par_les_technologies_d_assistance():
    assert 'class="auth-backdrop" aria-hidden="true"' in AUTH_HTML
    assert 'class="console-ambient" aria-hidden="true"' in CONSOLE_HTML


def test_les_animations_respectent_la_reduction_de_mouvement():
    assert "@media(prefers-reduced-motion:reduce)" in AUTH_HTML
    assert "@media(prefers-reduced-motion:reduce)" in CONSOLE_HTML
    assert ".auth-backdrop::before,.auth-backdrop::after{animation:none}" in AUTH_HTML
    assert ".console-node{animation:none}" in CONSOLE_HTML


def test_l_accueil_a_un_ambient_visuel_discret_et_accessible():
    assert 'class="landing-network" aria-hidden="true"' in LANDING_HTML
    assert "@keyframes landing-node" in LANDING_HTML
    assert ".landing-node,.float-card{animation:none}" in LANDING_HTML
    assert "landing-node-f" in LANDING_HTML
    assert "console-node-f" in CONSOLE_HTML


def test_l_accueil_pointe_vers_le_depot_github_officiel():
    assert GITHUB_URL == "https://github.com/Bodichane/monl-compiler"
    assert f'href="{GITHUB_URL}" target="_blank" rel="noopener"' in LANDING_HTML
    assert "Voir le projet sur GitHub" in LANDING_HTML


def test_toutes_les_pages_recoivent_l_ambiance_partagee():
    html = page(title="Test", description="Test", body="<h1>Test</h1>")
    assert 'class="site-ambient" aria-hidden="true"' in html
    assert "ambient-orbit-a" in html and "ambient-orbit-b" in html
    assert "@keyframes ambient-turn" in html
    assert ".ambient-orbit { animation:none !important; }" in html
