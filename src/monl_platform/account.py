"""Authentication and account interfaces for the platform."""

from __future__ import annotations

from .theme import icon, page

CSS = """
.auth-stage{position:relative;isolation:isolate;overflow:hidden;min-height:calc(100vh - 69px);display:grid;align-items:center;padding:var(--space-7) 0 var(--space-8)}
.auth-backdrop{position:absolute;inset:0;z-index:-2;overflow:hidden;pointer-events:none;background-image:linear-gradient(color-mix(in srgb,var(--line) 35%,transparent) 1px,transparent 1px),linear-gradient(90deg,color-mix(in srgb,var(--line) 35%,transparent) 1px,transparent 1px);background-size:56px 56px;mask-image:linear-gradient(to bottom,black,transparent 88%)}
.auth-network{position:absolute;inset:0;opacity:.7}.auth-network::before,.auth-network::after{content:"";position:absolute;border-top:1px dashed var(--line-strong);transform-origin:left center}.auth-network::before{width:360px;left:9%;top:32%;transform:rotate(-14deg)}.auth-network::after{width:420px;right:3%;top:67%;transform:rotate(17deg)}
.auth-network i{position:absolute;width:7px;height:7px;border-radius:50%;background:var(--brand);box-shadow:0 0 0 5px color-mix(in srgb,var(--brand) 10%,transparent)}.auth-network .n1{left:12%;top:29%}.auth-network .n2{left:33%;top:24%;background:var(--accent)}.auth-network .n3{right:18%;top:20%;background:var(--accent)}.auth-network .n4{right:8%;top:72%}
.auth-backdrop::before,.auth-backdrop::after{content:"";position:absolute;width:460px;aspect-ratio:1;border-radius:50%;filter:blur(2px);opacity:.55}
.auth-backdrop::before{left:-180px;top:4%;background:radial-gradient(circle,color-mix(in srgb,var(--accent) 20%,transparent),transparent 68%);animation:auth-drift 12s ease-in-out infinite alternate}
.auth-backdrop::after{right:-150px;bottom:-180px;background:radial-gradient(circle,color-mix(in srgb,var(--brand) 18%,transparent),transparent 68%);animation:auth-drift 15s ease-in-out -5s infinite alternate-reverse}
.auth-layout{display:grid;grid-template-columns:minmax(0,.95fr) minmax(400px,.75fr);gap:clamp(40px,7vw,96px);align-items:center}
.auth-story{max-width:570px;padding:var(--space-5) 0}.auth-story h2{font-size:clamp(42px,6vw,72px);max-width:10ch;margin-bottom:var(--space-5)}
.auth-story>p{font-size:18px;color:var(--muted);max-width:53ch}
.auth-flow{position:relative;display:grid;grid-template-columns:repeat(3,1fr);gap:var(--space-3);margin-top:var(--space-7)}
.auth-flow::before{content:"";position:absolute;left:12%;right:12%;top:25px;border-top:1px dashed var(--line-strong);z-index:-1}
.auth-step{background:color-mix(in srgb,var(--surface) 84%,transparent);border:1px solid var(--line);border-radius:var(--radius);padding:var(--space-4);box-shadow:0 12px 30px color-mix(in srgb,var(--brand) 7%,transparent);animation:auth-step-in .55s both cubic-bezier(.2,.75,.25,1)}
.auth-step:nth-child(2){animation-delay:.09s}.auth-step:nth-child(3){animation-delay:.18s}.auth-step .icon{color:var(--accent);margin-bottom:var(--space-3)}
.auth-step b{display:block;font-size:14px}.auth-step small{display:block;color:var(--muted);margin-top:3px}
.auth-card{width:100%;padding:clamp(24px,4vw,40px);background:color-mix(in srgb,var(--surface) 94%,transparent);box-shadow:var(--shadow),0 0 0 1px color-mix(in srgb,var(--surface) 60%,transparent);backdrop-filter:blur(14px);animation:auth-card-in .5s both cubic-bezier(.2,.75,.25,1)}
.auth-card h1{font-size:clamp(32px,4vw,42px);margin-bottom:var(--space-3)}.auth-card .auth-intro{margin-bottom:var(--space-5)}
.auth-kicker{display:flex;align-items:center;gap:8px;color:var(--accent);font:600 12px var(--mono);letter-spacing:.1em;text-transform:uppercase;margin-bottom:var(--space-3)}
.auth-kicker::before{content:"";width:20px;height:2px;background:currentColor}
.auth-tabs{display:grid;grid-template-columns:1fr 1fr;background:var(--surface-2);padding:4px;border-radius:12px;margin-bottom:var(--space-5)}
.auth-tabs button{border:0;background:transparent;min-height:44px;border-radius:9px;cursor:pointer;color:var(--muted);transition:background .18s ease,color .18s ease,box-shadow .18s ease}.auth-tabs button.active{background:var(--surface);color:var(--ink);font-weight:700;box-shadow:var(--shadow)}
.form-field{display:grid;gap:7px;margin-bottom:var(--space-4)}.form-field label{font-weight:650;font-size:14px}.form-field input{width:100%;min-height:48px;border:1px solid var(--line-strong);border-radius:11px;background:var(--bg);padding:0 13px;transition:border-color .18s ease,box-shadow .18s ease}.form-field input:focus{border-color:var(--brand);box-shadow:0 0 0 3px color-mix(in srgb,var(--brand) 12%,transparent)}
.password-wrap{position:relative}.password-wrap input{padding-right:88px}.password-toggle{position:absolute;right:5px;top:4px;min-width:76px;min-height:40px;border:0;border-radius:8px;background:transparent;color:var(--muted);cursor:pointer;font-size:13px;font-weight:650}.password-toggle:hover{background:var(--surface-2);color:var(--ink)}
.auth-card .primary{width:100%}.auth-recovery{display:block;width:100%;min-height:44px;margin-top:var(--space-3);border:0;background:transparent;color:var(--muted);cursor:pointer;font-size:13px;text-decoration:underline;text-underline-offset:3px}.auth-recovery:hover{color:var(--ink)}.form-error{display:none;color:var(--danger);background:var(--danger-bg);border:1px solid var(--danger-line);padding:var(--space-3);border-radius:10px;margin-bottom:var(--space-4)}.form-error.show{display:block}
.oauth-zone:empty,.oauth-zone[hidden]{display:none}.oauth-zone{display:grid;gap:var(--space-3);margin-bottom:var(--space-5)}.oauth-button{width:100%}.oauth-button:disabled{cursor:not-allowed;opacity:.62}.auth-divider{display:flex;align-items:center;gap:var(--space-3);color:var(--muted);font-size:12px;margin:0 0 var(--space-5)}.auth-divider::before,.auth-divider::after{content:"";height:1px;background:var(--line);flex:1}.oauth-zone:empty+.auth-divider,.oauth-zone[hidden]+.auth-divider{display:none}
.auth-note{display:flex;align-items:flex-start;gap:9px;color:var(--muted);font-size:13px;margin:var(--space-4) 0 0}.auth-note .icon{width:16px;height:16px;margin-top:2px;color:var(--accent)}
.account-head{padding:var(--space-7) 0 var(--space-5);display:flex;justify-content:space-between;align-items:end;gap:var(--space-4)}.account-head h1{font-size:clamp(34px,5vw,50px);margin-bottom:var(--space-2)}
.account-grid{padding-bottom:var(--space-8)}.account-panel h2{font-size:22px;margin-bottom:var(--space-2)}
.panel-head{display:flex;justify-content:space-between;align-items:center;gap:var(--space-3);margin-bottom:var(--space-5)}.item-list{display:grid;gap:var(--space-2)}
.account-item{display:flex;justify-content:space-between;align-items:center;gap:var(--space-3);padding:var(--space-4);background:var(--surface-2);border:1px solid var(--line);border-radius:12px}.account-item p{margin:2px 0 0;color:var(--muted);font-size:13px}.account-item code{font-size:12px}
.empty-account{padding:var(--space-7) var(--space-4);text-align:center;border:1px dashed var(--line);border-radius:12px;color:var(--muted)}
.delete-project.danger{color:var(--danger);background:var(--danger-bg)}
.codes-liste{display:grid;grid-template-columns:repeat(auto-fill,minmax(190px,1fr));gap:var(--space-2);margin:var(--space-4) 0}
.codes-liste code{font-size:14px;padding:11px 13px;background:var(--surface-2);border:1px solid var(--line);border-radius:10px;text-align:center;user-select:all}
.codes-avis{border-left:3px solid var(--brand);padding-left:var(--space-4);color:var(--ink);margin-bottom:var(--space-3)}
.codes-manquants{color:var(--danger)}
.auth-tabs.trois{grid-template-columns:1fr 1fr 1fr}
.auth-tabs button{font-size:14px;padding:0 6px}
.form-succes{display:none;border-left:3px solid var(--brand);padding-left:var(--space-4);margin-bottom:var(--space-4);color:var(--ink)}.form-succes.show{display:block}
.form-field.masque{display:none}
.auth-secours{margin-top:var(--space-4);color:var(--muted);font-size:13px;max-width:52ch}
.zone-rouge{margin-top:var(--space-5);border:1px solid var(--danger-line);background:var(--danger-bg);border-radius:var(--radius);padding:var(--space-5)}
.zone-rouge h2{font-size:19px;margin-bottom:var(--space-2)}.zone-rouge p{color:var(--muted);margin-bottom:var(--space-4);max-width:62ch}
.zone-rouge form{display:none;gap:var(--space-2);align-items:end;flex-wrap:wrap}.zone-rouge form.show{display:flex}
.zone-rouge input{min-height:44px;border:1px solid var(--danger-line);border-radius:10px;background:var(--surface);padding:0 12px;color:var(--ink)}
.zone-rouge .danger{min-height:44px;color:var(--danger);background:transparent;border:1px solid var(--danger-line);border-radius:10px;padding:0 16px;cursor:pointer;font-weight:600}
@keyframes auth-card-in{from{opacity:0;transform:translateY(18px) scale(.985)}}
@keyframes auth-step-in{from{opacity:0;transform:translateY(12px)}}
@keyframes auth-drift{to{transform:translate3d(35px,24px,0) scale(1.08)}}
@media(max-width:900px){.auth-layout{grid-template-columns:1fr;max-width:620px}.auth-story{padding:0}.auth-story h2{font-size:clamp(38px,10vw,58px);max-width:13ch}.auth-flow{margin-top:var(--space-5)}.account-head{align-items:start;flex-direction:column}}
@media(max-width:560px){.auth-stage{padding-top:var(--space-5)}.auth-layout{width:min(100% - 24px,620px)}.auth-story>p{font-size:16px}.auth-flow{grid-template-columns:1fr}.auth-flow::before{display:none}.auth-step{display:grid;grid-template-columns:24px 1fr;gap:0 var(--space-3)}.auth-step .icon{grid-row:1/span 2;margin:2px 0 0}.auth-step small{grid-column:2}.auth-tabs{grid-template-columns:1fr 1fr}.auth-card{padding:var(--space-5)}}
@media(prefers-reduced-motion:reduce){.auth-card,.auth-step,.auth-backdrop::before,.auth-backdrop::after{animation:none}}
"""

AUTH_BODY = f"""
<section class="auth-stage"><div class="auth-backdrop" aria-hidden="true"><div class="auth-network"><i class="n1"></i><i class="n2"></i><i class="n3"></i><i class="n4"></i></div></div><div class="shell auth-layout">
<div class="auth-story" data-reveal><h2>Your rules become a backend.</h2><p>Sign in to find your specifications, check their contract and ship a reproducible backend.</p>
<div class="auth-flow" role="list" aria-label="Compilation path">
<div class="auth-step" role="listitem">{icon('code')}<b>Describe</b><small>A readable spec</small></div>
<div class="auth-step" role="listitem">{icon('check')}<b>Check</b><small>Rules and access</small></div>
<div class="auth-step" role="listitem">{icon('package')}<b>Ship</b><small>Self-contained backend</small></div>
</div></div>
<div class="card auth-card"><p class="auth-kicker">Monl console</p><h1 id="auth-title">Sign in</h1><p class="muted auth-intro" id="auth-help">Find your projects and carry on with your compilations.</p>
<div class="auth-tabs" role="tablist" aria-label="Account access"><button class="active" type="button" role="tab" aria-selected="true" data-mode="login">Sign in</button><button type="button" role="tab" aria-selected="false" data-mode="register">Create an account</button></div>
<div class="oauth-zone" id="oauth-zone" role="group" aria-label="Sign in with a provider"></div><div class="auth-divider"><span>or with your address</span></div>
<div class="form-error" id="auth-error" role="alert"></div>
<div class="form-succes" id="auth-succes" role="status" aria-live="polite"></div><form id="auth-form" novalidate>
<div class="form-field"><label for="email">Email address</label><input id="email" type="email" autocomplete="email" required></div>
<div class="form-field masque" id="champ-code"><label for="code">Recovery code</label><input id="code" type="text" autocomplete="one-time-code" spellcheck="false"><small class="muted">One of the eight codes given when your account was created. Each code works only once.</small></div>
<div class="form-field"><label for="password" id="password-label">Password</label><div class="password-wrap"><input id="password" type="password" autocomplete="current-password" minlength="10" required><button class="password-toggle" id="password-toggle" type="button" aria-controls="password" aria-pressed="false">Show</button></div><small class="muted">At least 10 characters.</small></div>
<button class="primary" type="submit">{icon('user')} <span id="submit-label">Sign in</span></button></form><button class="auth-recovery" id="auth-recovery" type="button" data-mode="recover">Forgot your password?</button>
<p class="auth-note">{icon('shield')} <span>Monl sends no email: keep your recovery codes, they are the only way back in.</span></p>
<p class="auth-secours" id="auth-secours" hidden>Your codes were shown only once, when the account was created. Without a code, nobody can reopen your account for you: Monl sends no email and keeps nothing else to identify you. Write to the service operator, who alone has administrative access.</p></div></div></section>
"""

AUTH_SCRIPT = """
<script>
let mode='login';const form=document.querySelector('#auth-form'),error=document.querySelector('#auth-error');
const succes=document.querySelector('#auth-succes'),champCode=document.querySelector('#champ-code');
const aide=document.querySelector('#auth-secours');
const oauthZone=document.querySelector('#oauth-zone'),passwordToggle=document.querySelector('#password-toggle'),recoveryLink=document.querySelector('#auth-recovery');
if(new URLSearchParams(location.search).get('erreur')==='refus'){
 error.textContent='Sign-in cancelled. You can try again or use your email address.';
 error.className='form-error show';
}
/* One table per mode rather than stacked ternaries: with three modes, the
   form "login ? a : b" stops telling the truth without anyone seeing it. */
const MODES={
 login:{titre:'Sign in',bouton:'Sign in',
  intro:'Find your projects and carry on with your compilations.',
  motdepasse:'Password',autocomplete:'current-password'},
 register:{titre:'Create your account',bouton:'Create the account',
  intro:'Your eight recovery codes will be given to you only once, right after.',
  motdepasse:'Password',autocomplete:'new-password'},
 recover:{titre:'Recover your account',bouton:'Change the password',
  intro:'Enter one of your recovery codes and choose a new password.',
  motdepasse:'New password',autocomplete:'new-password'}};
function basculer(nouveau){mode=nouveau;const conf=MODES[mode];
 document.querySelectorAll('.auth-tabs [data-mode]').forEach(x=>{const actif=x.dataset.mode===mode;x.classList.toggle('active',actif);x.setAttribute('aria-selected',String(actif));});
 recoveryLink.dataset.mode=mode==='recover'?'login':'recover';recoveryLink.textContent=mode==='recover'?'← Back to sign in':'Forgot your password?';
 document.querySelector('#auth-title').textContent=conf.titre;
 document.querySelector('#auth-help').textContent=conf.intro;
 document.querySelector('#submit-label').textContent=conf.bouton;
 document.querySelector('#password-label').textContent=conf.motdepasse;
 document.querySelector('#password').autocomplete=conf.autocomplete;
 oauthZone.hidden=(mode==='recover');
 champCode.classList.toggle('masque',mode!=='recover');
 /* `required` must follow what is DISPLAYED: a required but hidden field makes
    validation fail on a field nobody can see or reach, and the button seems
    to do nothing — the defect `novalidate` already served to repair here. */
 document.querySelector('#code').required=(mode==='recover');
 aide.hidden=(mode!=='recover');
 error.className='form-error';succes.className='form-succes';}
document.querySelectorAll('[data-mode]').forEach(button=>button.onclick=()=>basculer(button.dataset.mode));
document.querySelector('.auth-tabs').onkeydown=event=>{if(!['ArrowLeft','ArrowRight'].includes(event.key))return;const onglets=[...document.querySelectorAll('.auth-tabs [data-mode]')],index=onglets.indexOf(document.activeElement),pas=event.key==='ArrowRight'?1:-1,cible=onglets[(index+pas+onglets.length)%onglets.length];event.preventDefault();cible.focus();basculer(cible.dataset.mode);};
passwordToggle.onclick=()=>{const champ=document.querySelector('#password');const visible=champ.type==='text';champ.type=visible?'password':'text';passwordToggle.textContent=visible?'Show':'Hide';passwordToggle.setAttribute('aria-pressed',String(!visible));champ.focus();};
fetch('/auth/fournisseurs').then(response=>response.ok?response.json():{providers:[]}).then(data=>{
 const fournisseurs=Array.isArray(data.providers)?data.providers:[];
 const githubIcon='<svg class="icon" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M12 2C6.48 2 2 6.58 2 12.24c0 4.52 2.87 8.35 6.84 9.71.5.1.68-.22.68-.49v-1.71c-2.78.62-3.37-1.39-3.37-1.39-.45-1.19-1.11-1.51-1.11-1.51-.91-.64.07-.63.07-.63 1 .08 1.53 1.06 1.53 1.06.9 1.59 2.35 1.13 2.92.86.09-.67.35-1.13.64-1.39-2.22-.26-4.56-1.15-4.56-5.09 0-1.12.39-2.04 1.03-2.76-.1-.26-.45-1.31.1-2.73 0 0 .84-.28 2.75 1.05A9.2 9.2 0 0 1 12 7.9c.85 0 1.71.12 2.5.35 1.91-1.33 2.75-1.05 2.75-1.05.55 1.42.2 2.47.1 2.73.64.72 1.03 1.64 1.03 2.76 0 3.95-2.34 4.83-4.57 5.08.36.32.68.95.68 1.92v2.84c0 .27.18.59.69.49A10.2 10.2 0 0 0 22 12.24C22 6.58 17.52 2 12 2Z"/></svg>';
 /* The button is built through the DOM, never through innerHTML: the name goes
    into the address ENCODED, the label goes into the text, and only the icon —
    a constant of this page — is markup. Name and label come from a server
    table today; a defense that assumes its source is safe stops defending the
    day the source changes (issue #75). */
 oauthZone.replaceChildren(...fournisseurs.map(provider=>{
  const bouton=document.createElement('a');bouton.className='secondary oauth-button';
  bouton.setAttribute('href','/auth/'+encodeURIComponent(provider.name));
  if(provider.name==='github')bouton.innerHTML=githubIcon;
  bouton.append('Continue with '+provider.label);return bouton;}));
}).catch(()=>{oauthZone.replaceChildren();});
form.onsubmit=async event=>{event.preventDefault();error.className='form-error';
 /* The form carries `novalidate` so that THIS code sees the submission.
    Without it, the browser blocked on its own on an address without "@": no
    request left, the page banner stayed EMPTY, and the only message was a
    native bubble — the one a password manager's window covers. The button
    seemed to do nothing. The message is not rewritten: the browser's own,
    already translated, is reused. */
 const invalide=[...form.elements].find(champ=>champ.willValidate&&!champ.checkValidity());
 if(invalide){error.textContent=invalide.validationMessage;error.className='form-error show';invalide.focus();return;}
 const button=form.querySelector('button[type=submit]');button.disabled=true;form.setAttribute('aria-busy','true');
 const envoi={email:email.value,password:password.value};
 if(mode==='recover')envoi.code=document.querySelector('#code').value;
 try{const response=await fetch('/api/auth/'+mode,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(envoi)});
 /* Recovery answers 204, WITHOUT a body: asking for its JSON would throw on
    the only case that succeeds, and the person would see an error after
    burning one of their eight codes. The refusal, for its part, does carry a
    detail. */
 if(!response.ok){let detail='Unable to continue.';
  try{detail=(await response.json()).detail||detail;}catch(_){}
  throw new Error(detail);}
 if(mode==='recover'){const adresse=email.value;basculer('login');email.value=adresse;
  document.querySelector('#code').value='';password.value='';
  succes.textContent='Password changed, every session closed and every MCP key revoked. Sign in with the new password.';
  succes.className='form-succes show';password.focus();return;}
 const next=new URLSearchParams(location.search).get('next');location.href=next&&next.startsWith('/')&&!next.startsWith('//')?next:'/console';
 }catch(e){error.textContent=e.message;error.className='form-error show';}finally{button.disabled=false;form.removeAttribute('aria-busy');}};
</script>
"""

ACCOUNT_BODY = f"""
<section class="shell account-head"><div><h1>Your projects.</h1><p class="muted" id="account-email"></p></div>
<button class="secondary" id="logout" type="button">Sign out</button></section>
<section class="shell account-grid"><article class="card account-panel"><div class="panel-head"><div><h2>Compiled projects</h2><p class="muted">Kept in your space.</p></div><a class="primary" href="/console">{icon('compiler')} New project</a></div><div class="item-list" id="projects"></div></article>
<article class="card account-panel" id="panneau-codes">
<div class="panel-head"><div><h2>Recovery codes</h2>
<p class="muted">The only way to regain control if you lose your password.</p></div>
<input id="mdp-codes" type="password" autocomplete="current-password" aria-label="Current password" placeholder="Current password">
<button class="secondary" id="regenerer-codes" type="button">Generate a new set</button></div>
<p class="muted">Current password required. Other sessions will be closed; MCP keys stay valid. Unavailable for OAuth accounts.</p>
<p class="muted" id="etat-codes">…</p>
<div id="codes-affiches"></div>
<div class="form-error" id="erreur-codes" role="alert"></div></article>
<article class="zone-rouge">
<h2>Delete your account</h2>
<p>Permanently erases your account, your access keys, your projects and the compiled
files that belong to them. <b>This action is irreversible</b> — download
what you want to keep before continuing.</p>
<p id="suppression-oauth" class="muted" hidden>For an OAuth account, sign in again with your provider, then delete your account within ten minutes. No local password is needed.</p>
<button class="danger" id="ouvrir-suppression" type="button">Delete my account</button>
<form id="suppression"><div class="form-field"><label for="mdp-suppression">Confirm with your password</label>
<input id="mdp-suppression" type="password" autocomplete="current-password" required></div>
<button class="danger" type="submit">Delete permanently</button>
<button class="ghost" id="annuler-suppression" type="button">Cancel</button></form>
<div class="form-error" id="erreur-suppression" role="alert"></div></article></section>
"""

ACCOUNT_SCRIPT = """
<script>
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
async function json(url,options){const r=await fetch(url,options);if(r.status===401){location.href='/login?next=/account';throw new Error('session');}const d=r.status===204?{}:await r.json();if(!r.ok)throw new Error(d.detail||'Error');return d;}
async function load(){const [me,projects]=await Promise.all([json('/api/auth/me'),json('/api/projects')]);
 const oauth=Boolean(me.auth_provider);document.querySelector('#suppression-oauth').hidden=!oauth;document.querySelector('#mdp-suppression').required=!oauth;document.querySelector('#mdp-suppression').parentElement.hidden=oauth;
 document.querySelector('#account-email').textContent=me.email;document.querySelector('#projects').innerHTML=projects.projects.length?projects.projects.map(p=>`<div class="account-item"><div><b>${esc(p.name)}</b><p>Created ${new Date(p.created_at*1000).toLocaleDateString('en-GB')} · expires ${new Date(p.expires_at*1000).toLocaleDateString('en-GB')}</p></div><span><a class="secondary" href="/api/projects/${encodeURIComponent(p.project_id)}/download">Download</a><button class="ghost delete-project" data-id="${esc(p.project_id)}" type="button">Delete</button></span></div>`).join(''):'<div class="empty-account">No projects. Compile your first spec.</div>';
 document.querySelectorAll('.delete-project').forEach(b=>b.onclick=async()=>{if(!b.dataset.confirmed){b.dataset.confirmed='1';b.textContent='Confirm';b.classList.add('danger');return;}await json('/api/projects/'+b.dataset.id,{method:'DELETE'});load();});}
const etatCodes=document.querySelector('#etat-codes'),affiches=document.querySelector('#codes-affiches'),erreurCodes=document.querySelector('#erreur-codes');
async function chargerCodes(){try{const d=await json('/api/auth/recovery-codes');
 etatCodes.textContent=d.remaining?`${d.remaining} code${d.remaining>1?'s':''} still usable. They cannot be read again: generating a new set replaces the old one.`:"No usable code. Without a password and without a code, this account would be permanently inaccessible — generate a set now.";
 etatCodes.className=d.remaining?'muted':'codes-manquants';}catch(e){etatCodes.textContent='';}}
document.querySelector('#regenerer-codes').onclick=async()=>{erreurCodes.className='form-error';
 try{const d=await json('/api/auth/recovery-codes',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({password:document.querySelector('#mdp-codes').value})});
  document.querySelector('#mdp-codes').value='';
  affiches.innerHTML='<p class="codes-avis"><b>Write them down now.</b> They will never be shown again, and the old set no longer works. Each code works only once.</p><div class="codes-liste">'+d.recovery_codes.map(c=>`<code>${esc(c)}</code>`).join('')+'</div>';
  chargerCodes();}catch(e){erreurCodes.textContent=e.message;erreurCodes.className='form-error show';}};
document.querySelector('#logout').onclick=async()=>{await fetch('/api/auth/logout',{method:'POST'});location.href='/';};
const zone=document.querySelector('#suppression'),erreur=document.querySelector('#erreur-suppression');
document.querySelector('#ouvrir-suppression').onclick=()=>{zone.classList.add('show');document.querySelector('#mdp-suppression').focus();};
document.querySelector('#annuler-suppression').onclick=()=>{zone.classList.remove('show');erreur.className='form-error';};
zone.onsubmit=async event=>{event.preventDefault();erreur.className='form-error';
 try{await json('/api/auth/account',{method:'DELETE',headers:{'Content-Type':'application/json'},body:JSON.stringify({password:document.querySelector('#mdp-suppression').value})});location.href='/';}
 catch(e){erreur.textContent=e.message;erreur.className='form-error show';}};
load();
</script>
"""

AUTH_HTML = page(title="Sign in — MONL", description="Access your Monl space.",
                 body=AUTH_BODY, extra_css=CSS, scripts=AUTH_SCRIPT)
ACCOUNT_HTML = page(title="Your account — MONL", description="Your projects compiled with Monl.",
                    body=ACCOUNT_BODY, active="account", extra_css=CSS, scripts=ACCOUNT_SCRIPT)
