"""Dedicated MCP connection and access-key interface."""

from __future__ import annotations

from .theme import icon, page

CSS = """
.mcp-hero{padding:var(--space-7) 0 var(--space-5);max-width:760px}.mcp-hero h1{font-size:clamp(38px,6vw,64px);line-height:1.02;margin:var(--space-3) 0}.mcp-hero p{font-size:18px;max-width:680px}
.mcp-grid{display:grid;grid-template-columns:minmax(0,1fr) minmax(360px,.82fr);gap:var(--space-4);padding-bottom:var(--space-8);align-items:start}.mcp-panel{padding:var(--space-5)}
.mcp-panel h2{font-size:23px;margin-bottom:var(--space-2)}.mcp-panel h3{font-size:16px;margin:var(--space-5) 0 var(--space-2)}.mcp-panel>.muted{margin-bottom:var(--space-5)}
.endpoint{display:flex;align-items:center;justify-content:space-between;gap:var(--space-3);padding:var(--space-3) var(--space-4);border:1px solid var(--line);background:var(--surface-2);border-radius:12px}.endpoint code{overflow-wrap:anywhere}
.tool-list{display:grid;grid-template-columns:1fr 1fr;gap:8px}.tool-list span{padding:10px 12px;border:1px solid var(--line);border-radius:10px;font:13px var(--mono);color:var(--ink)}
.panel-head{display:flex;justify-content:space-between;align-items:center;gap:var(--space-3);margin-bottom:var(--space-5)}.item-list{display:grid;gap:var(--space-2)}
.key-item{display:flex;justify-content:space-between;align-items:center;gap:var(--space-3);padding:var(--space-4);background:var(--surface-2);border:1px solid var(--line);border-radius:12px}.key-item p{margin:3px 0 0;color:var(--muted);font-size:13px}.key-item code{font-size:12px}
.empty-keys{padding:var(--space-7) var(--space-4);text-align:center;border:1px dashed var(--line);border-radius:12px;color:var(--muted)}
.key-secret{display:none;margin-bottom:var(--space-4);padding:var(--space-4);background:var(--soft);border:1px solid var(--brand);border-radius:12px}.key-secret.show{display:block}.key-secret code{display:block;overflow-wrap:anywhere;margin:var(--space-2) 0}.key-secret p{font-size:13px;margin:var(--space-2) 0 0}
.key-create{display:none;grid-template-columns:1fr auto;gap:var(--space-2);margin-bottom:var(--space-4)}.key-create.show{display:grid}.key-create input{min-height:44px;border:1px solid var(--line);border-radius:10px;background:var(--bg);padding:0 12px;color:var(--ink)}
@media(max-width:850px){.mcp-grid{grid-template-columns:1fr}}@media(max-width:520px){.panel-head,.key-item,.endpoint{align-items:flex-start;flex-direction:column}.key-create{grid-template-columns:1fr}.tool-list{grid-template-columns:1fr}}
"""

BODY = f"""
<section class="shell mcp-hero"><h1>Reliez votre agent au compilateur.</h1>
<p class="muted">Créez une clé ici, configurez-la une fois dans votre agent, puis validez et compilez des backends Monl sans installer le projet.</p></section>
<section class="shell mcp-grid">
<article class="card mcp-panel"><h2>Configurer la connexion</h2><p class="muted">Votre agent appelle le compilateur distant avec une clé personnelle. La spec reste le contrat d’entrée.</p>
<h3>Adresse du serveur</h3><div class="endpoint"><code id="mcp-endpoint">/mcp</code><button class="secondary copy-endpoint" type="button">Copier</button></div>
<h3>Outils disponibles</h3><div class="tool-list"><span>monl_list_templates</span><span>monl_validate_spec</span><span>monl_compile_backend</span><span>monl_list_projects</span><span>monl_inspect_contract</span><span>monl_diff_spec</span><span>monl_update_backend</span></div>
<p class="muted" style="margin-top:var(--space-5)">Utilisez la clé comme jeton Bearer. Une clé par appareil permet de révoquer un accès sans interrompre les autres.</p>
<a class="secondary" href="/docs">Lire la syntaxe des specs</a></article>
<article class="card mcp-panel"><div class="panel-head"><div><h2>Clés d’accès</h2><p class="muted">Gérez les accès de vos agents.</p></div><button class="primary" id="new-key" type="button">{icon('key')} Créer une clé</button></div>
<form class="key-create" id="key-create"><label class="skip" for="key-name">Nom de la clé</label><input id="key-name" placeholder="Ex. Codex portable" maxlength="80" required><button class="primary" type="submit">Générer</button></form>
<div class="key-secret" id="key-secret"><b>Copiez cette clé maintenant</b><code></code><button class="secondary copy-secret" type="button">Copier la clé</button><p>Elle ne sera plus affichée après avoir quitté cette page.</p></div>
<div class="item-list" id="keys"></div></article></section>
"""

SCRIPT = """
<script>
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
async function json(url,options){const r=await fetch(url,options);if(r.status===401){location.href='/login?next=/mcp';throw new Error('session');}const d=r.status===204?{}:await r.json();if(!r.ok)throw new Error(d.detail||'Erreur');return d;}
async function copy(value,button,label){await navigator.clipboard.writeText(value);button.textContent='Copié';setTimeout(()=>button.textContent=label,1400);}
async function load(){await json('/api/auth/me');const keys=await json('/api/keys');document.querySelector('#keys').innerHTML=keys.keys.length?keys.keys.map(k=>`<div class="key-item"><div><b>${esc(k.name)}</b><p><code>${esc(k.prefix)}…</code> · ${k.revoked_at?'révoquée':k.last_used_at?'utilisée':'jamais utilisée'}</p></div>${k.revoked_at?'':`<button class="ghost revoke" data-id="${esc(k.id)}" type="button">Révoquer</button>`}</div>`).join(''):'<div class="empty-keys">Aucune clé. Créez-en une pour connecter votre premier agent.</div>';document.querySelectorAll('.revoke').forEach(b=>b.onclick=async()=>{await json('/api/keys/'+b.dataset.id,{method:'DELETE'});load();});}
document.querySelector('#new-key').onclick=()=>{const form=document.querySelector('#key-create');form.classList.toggle('show');if(form.classList.contains('show'))document.querySelector('#key-name').focus();};
document.querySelector('#key-create').onsubmit=async e=>{e.preventDefault();const input=document.querySelector('#key-name');const key=await json('/api/keys',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:input.value})});const box=document.querySelector('#key-secret');box.querySelector('code').textContent=key.key;box.className='key-secret show';box.querySelector('.copy-secret').onclick=event=>copy(key.key,event.currentTarget,'Copier la clé');input.value='';document.querySelector('#key-create').classList.remove('show');load();};
document.querySelector('.copy-endpoint').onclick=event=>copy(location.origin+'/mcp',event.currentTarget,'Copier');load();
</script>
"""

MCP_HTML = page(title="MCP — monl compiler", description="Connectez votre agent au serveur MCP Monl.", body=BODY, active="mcp", extra_css=CSS, scripts=SCRIPT)
