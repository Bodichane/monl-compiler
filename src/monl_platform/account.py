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
.oauth-zone:empty,.oauth-zone[hidden]{display:none}.oauth-zone{display:grid;gap:var(--space-3);margin-bottom:var(--space-5)}.oauth-button{width:100%}.oauth-button:disabled{cursor:not-allowed;opacity:.62}.oauth-unavailable{display:block;color:var(--muted);font-size:12px;margin-top:2px}.auth-divider{display:flex;align-items:center;gap:var(--space-3);color:var(--muted);font-size:12px;margin:0 0 var(--space-5)}.auth-divider::before,.auth-divider::after{content:"";height:1px;background:var(--line);flex:1}.oauth-zone:empty+.auth-divider,.oauth-zone[hidden]+.auth-divider{display:none}
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
<div class="auth-story" data-reveal><h2>Vos règles deviennent un backend.</h2><p>Connectez-vous pour retrouver vos spécifications, vérifier leur contrat et livrer un backend reproductible.</p>
<div class="auth-flow" role="list" aria-label="Parcours de compilation">
<div class="auth-step" role="listitem">{icon('code')}<b>Décrire</b><small>Une spec lisible</small></div>
<div class="auth-step" role="listitem">{icon('check')}<b>Vérifier</b><small>Règles et accès</small></div>
<div class="auth-step" role="listitem">{icon('package')}<b>Livrer</b><small>Backend autonome</small></div>
</div></div>
<div class="card auth-card"><p class="auth-kicker">Console Monl</p><h1 id="auth-title">Se connecter</h1><p class="muted auth-intro" id="auth-help">Retrouvez vos projets et poursuivez vos compilations.</p>
<div class="auth-tabs" role="tablist" aria-label="Accès au compte"><button class="active" type="button" role="tab" aria-selected="true" data-mode="login">Connexion</button><button type="button" role="tab" aria-selected="false" data-mode="register">Créer un compte</button></div>
<div class="oauth-zone" id="oauth-zone" role="group" aria-label="Connexion avec un fournisseur"></div><div class="auth-divider"><span>ou avec votre adresse</span></div>
<div class="form-error" id="auth-error" role="alert"></div>
<div class="form-succes" id="auth-succes" role="status" aria-live="polite"></div><form id="auth-form" novalidate>
<div class="form-field"><label for="email">Adresse email</label><input id="email" type="email" autocomplete="email" required></div>
<div class="form-field masque" id="champ-code"><label for="code">Code de secours</label><input id="code" type="text" autocomplete="one-time-code" spellcheck="false"><small class="muted">L’un des huit codes remis à la création de votre compte. Chaque code ne sert qu’une fois.</small></div>
<div class="form-field"><label for="password" id="password-label">Mot de passe</label><div class="password-wrap"><input id="password" type="password" autocomplete="current-password" minlength="10" required><button class="password-toggle" id="password-toggle" type="button" aria-controls="password" aria-pressed="false">Afficher</button></div><small class="muted">10 caractères au minimum.</small></div>
<button class="primary" type="submit">{icon('user')} <span id="submit-label">Se connecter</span></button></form><button class="auth-recovery" id="auth-recovery" type="button" data-mode="recover">Mot de passe oublié ?</button>
<p class="auth-note">{icon('shield')} <span>Monl n’envoie aucun courriel : gardez vos codes de secours, ils sont la seule voie de reprise.</span></p>
<p class="auth-secours" id="auth-secours" hidden>Vos codes ont été affichés une seule fois, à la création du compte. Sans code, personne ne peut rouvrir votre compte à votre place : Monl n’envoie aucun courriel et ne conserve pas de quoi vous identifier autrement. Écrivez à l’exploitant du service, qui seul dispose d’un accès d’administration.</p></div></div></section>
"""

AUTH_SCRIPT = """
<script>
let mode='login';const form=document.querySelector('#auth-form'),error=document.querySelector('#auth-error');
const succes=document.querySelector('#auth-succes'),champCode=document.querySelector('#champ-code');
const aide=document.querySelector('#auth-secours');
const oauthZone=document.querySelector('#oauth-zone'),passwordToggle=document.querySelector('#password-toggle'),recoveryLink=document.querySelector('#auth-recovery');
if(new URLSearchParams(location.search).get('erreur')==='refus'){
 error.textContent='Connexion annulée. Vous pouvez réessayer ou utiliser votre adresse email.';
 error.className='form-error show';
}
/* Un tableau par mode plutôt que des ternaires empilés : à trois modes, la
   forme « login ? a : b » cesse de dire la vérité sans qu'on le voie. */
const MODES={
 login:{titre:'Se connecter',bouton:'Se connecter',
  intro:'Retrouvez vos projets et poursuivez vos compilations.',
  motdepasse:'Mot de passe',autocomplete:'current-password'},
 register:{titre:'Créer votre compte',bouton:'Créer le compte',
  intro:'Vos huit codes de secours vous seront remis une seule fois, juste après.',
  motdepasse:'Mot de passe',autocomplete:'new-password'},
 recover:{titre:'Retrouver votre compte',bouton:'Changer le mot de passe',
  intro:'Entrez un de vos codes de secours et choisissez un nouveau mot de passe.',
  motdepasse:'Nouveau mot de passe',autocomplete:'new-password'}};
function basculer(nouveau){mode=nouveau;const conf=MODES[mode];
 document.querySelectorAll('.auth-tabs [data-mode]').forEach(x=>{const actif=x.dataset.mode===mode;x.classList.toggle('active',actif);x.setAttribute('aria-selected',String(actif));});
 recoveryLink.dataset.mode=mode==='recover'?'login':'recover';recoveryLink.textContent=mode==='recover'?'← Retour à la connexion':'Mot de passe oublié ?';
 document.querySelector('#auth-title').textContent=conf.titre;
 document.querySelector('#auth-help').textContent=conf.intro;
 document.querySelector('#submit-label').textContent=conf.bouton;
 document.querySelector('#password-label').textContent=conf.motdepasse;
 document.querySelector('#password').autocomplete=conf.autocomplete;
 oauthZone.hidden=(mode==='recover');
 champCode.classList.toggle('masque',mode!=='recover');
 /* `required` doit suivre l'AFFICHAGE : un champ obligatoire mais masqué fait
    échouer la validation sur un champ que personne ne peut ni voir ni
    atteindre, et le bouton semble ne rien faire — le défaut que `novalidate`
    a déjà servi à réparer ici. */
 document.querySelector('#code').required=(mode==='recover');
 aide.hidden=(mode!=='recover');
 error.className='form-error';succes.className='form-succes';}
document.querySelectorAll('[data-mode]').forEach(button=>button.onclick=()=>basculer(button.dataset.mode));
document.querySelector('.auth-tabs').onkeydown=event=>{if(!['ArrowLeft','ArrowRight'].includes(event.key))return;const onglets=[...document.querySelectorAll('.auth-tabs [data-mode]')],index=onglets.indexOf(document.activeElement),pas=event.key==='ArrowRight'?1:-1,cible=onglets[(index+pas+onglets.length)%onglets.length];event.preventDefault();cible.focus();basculer(cible.dataset.mode);};
passwordToggle.onclick=()=>{const champ=document.querySelector('#password');const visible=champ.type==='text';champ.type=visible?'password':'text';passwordToggle.textContent=visible?'Afficher':'Masquer';passwordToggle.setAttribute('aria-pressed',String(!visible));champ.focus();};
fetch('/auth/fournisseurs').then(response=>response.ok?response.json():{providers:[]}).then(data=>{
 const fournisseurs=Array.isArray(data.providers)?data.providers:[];
 const githubIcon='<svg class="icon" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M12 2C6.48 2 2 6.58 2 12.24c0 4.52 2.87 8.35 6.84 9.71.5.1.68-.22.68-.49v-1.71c-2.78.62-3.37-1.39-3.37-1.39-.45-1.19-1.11-1.51-1.11-1.51-.91-.64.07-.63.07-.63 1 .08 1.53 1.06 1.53 1.06.9 1.59 2.35 1.13 2.92.86.09-.67.35-1.13.64-1.39-2.22-.26-4.56-1.15-4.56-5.09 0-1.12.39-2.04 1.03-2.76-.1-.26-.45-1.31.1-2.73 0 0 .84-.28 2.75 1.05A9.2 9.2 0 0 1 12 7.9c.85 0 1.71.12 2.5.35 1.91-1.33 2.75-1.05 2.75-1.05.55 1.42.2 2.47.1 2.73.64.72 1.03 1.64 1.03 2.76 0 3.95-2.34 4.83-4.57 5.08.36.32.68.95.68 1.92v2.84c0 .27.18.59.69.49A10.2 10.2 0 0 0 22 12.24C22 6.58 17.52 2 12 2Z"/></svg>';
 const boutons=fournisseurs.map(provider=>`<a class="secondary oauth-button" href="/auth/${encodeURIComponent(provider.name)}">${provider.name==='github'?githubIcon:''}Continuer avec ${provider.label}</a>`);
 oauthZone.innerHTML=boutons.join('');
}).catch(()=>{oauthZone.innerHTML='';});
form.onsubmit=async event=>{event.preventDefault();error.className='form-error';
 /* Le formulaire porte `novalidate` pour que CE code voie l'envoi. Sans lui,
    le navigateur bloquait tout seul sur une adresse sans « @ » : aucune
    requête ne partait, la bannière de la page restait VIDE, et le seul
    message était une bulle native — celle que la fenêtre d'un gestionnaire de
    mots de passe recouvre. Le bouton semblait ne rien faire. Le message n'est
    pas réécrit : on reprend celui du navigateur, déjà traduit. */
 const invalide=[...form.elements].find(champ=>champ.willValidate&&!champ.checkValidity());
 if(invalide){error.textContent=invalide.validationMessage;error.className='form-error show';invalide.focus();return;}
 const button=form.querySelector('button[type=submit]');button.disabled=true;form.setAttribute('aria-busy','true');
 const envoi={email:email.value,password:password.value};
 if(mode==='recover')envoi.code=document.querySelector('#code').value;
 try{const response=await fetch('/api/auth/'+mode,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(envoi)});
 /* La récupération répond 204, SANS corps : demander son JSON lèverait sur le
    seul cas qui réussit, et la personne verrait une erreur après avoir brûlé
    un de ses huit codes. Le refus, lui, porte bien un détail. */
 if(!response.ok){let detail='Impossible de continuer.';
  try{detail=(await response.json()).detail||detail;}catch(_){}
  throw new Error(detail);}
 if(mode==='recover'){const adresse=email.value;basculer('login');email.value=adresse;
  document.querySelector('#code').value='';password.value='';
  succes.textContent='Mot de passe changé, et vos autres sessions ont été fermées. Connectez-vous avec le nouveau mot de passe.';
  succes.className='form-succes show';password.focus();return;}
 const next=new URLSearchParams(location.search).get('next');location.href=next&&next.startsWith('/')&&!next.startsWith('//')?next:'/console';
 }catch(e){error.textContent=e.message;error.className='form-error show';}finally{button.disabled=false;form.removeAttribute('aria-busy');}};
</script>
"""

ACCOUNT_BODY = f"""
<section class="shell account-head"><div><h1>Vos projets.</h1><p class="muted" id="account-email"></p></div>
<button class="secondary" id="logout" type="button">Se déconnecter</button></section>
<section class="shell account-grid"><article class="card account-panel"><div class="panel-head"><div><h2>Projets compilés</h2><p class="muted">Conservés dans votre espace.</p></div><a class="primary" href="/console">{icon('compiler')} Nouveau projet</a></div><div class="item-list" id="projects"></div></article>
<article class="card account-panel" id="panneau-codes">
<div class="panel-head"><div><h2>Codes de secours</h2>
<p class="muted">Le seul moyen de reprendre la main si vous perdez votre mot de passe.</p></div>
<button class="secondary" id="regenerer-codes" type="button">Générer une nouvelle série</button></div>
<p class="muted" id="etat-codes">…</p>
<div id="codes-affiches"></div>
<div class="form-error" id="erreur-codes" role="alert"></div></article>
<article class="zone-rouge">
<h2>Supprimer votre compte</h2>
<p>Efface définitivement votre compte, vos clés d’accès, vos projets et les fichiers
compilés qui leur appartiennent. <b>Cette action est irréversible</b> — téléchargez
ce que vous voulez garder avant de continuer.</p>
<button class="danger" id="ouvrir-suppression" type="button">Supprimer mon compte</button>
<form id="suppression"><div class="form-field"><label for="mdp-suppression">Confirmez avec votre mot de passe</label>
<input id="mdp-suppression" type="password" autocomplete="current-password" required></div>
<button class="danger" type="submit">Supprimer définitivement</button>
<button class="ghost" id="annuler-suppression" type="button">Annuler</button></form>
<div class="form-error" id="erreur-suppression" role="alert"></div></article></section>
"""

ACCOUNT_SCRIPT = """
<script>
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
async function json(url,options){const r=await fetch(url,options);if(r.status===401){location.href='/login?next=/account';throw new Error('session');}const d=r.status===204?{}:await r.json();if(!r.ok)throw new Error(d.detail||'Erreur');return d;}
async function load(){const [me,projects]=await Promise.all([json('/api/auth/me'),json('/api/projects')]);
 document.querySelector('#account-email').textContent=me.email;document.querySelector('#projects').innerHTML=projects.projects.length?projects.projects.map(p=>`<div class="account-item"><div><b>${esc(p.name)}</b><p>Créé le ${new Date(p.created_at*1000).toLocaleDateString('fr-FR')} · expire le ${new Date(p.expires_at*1000).toLocaleDateString('fr-FR')}</p></div><span><a class="secondary" href="/api/projects/${encodeURIComponent(p.project_id)}/download">Télécharger</a><button class="ghost delete-project" data-id="${esc(p.project_id)}" type="button">Supprimer</button></span></div>`).join(''):'<div class="empty-account">Aucun projet. Compilez votre première spec.</div>';
 document.querySelectorAll('.delete-project').forEach(b=>b.onclick=async()=>{if(!b.dataset.confirmed){b.dataset.confirmed='1';b.textContent='Confirmer';b.classList.add('danger');return;}await json('/api/projects/'+b.dataset.id,{method:'DELETE'});load();});}
const etatCodes=document.querySelector('#etat-codes'),affiches=document.querySelector('#codes-affiches'),erreurCodes=document.querySelector('#erreur-codes');
async function chargerCodes(){try{const d=await json('/api/auth/recovery-codes');
 etatCodes.textContent=d.remaining?`${d.remaining} code${d.remaining>1?'s':''} encore utilisable${d.remaining>1?'s':''}. Ils ne sont pas relisibles : générer une nouvelle série remplace l'ancienne.`:"Aucun code utilisable. Sans mot de passe et sans code, ce compte serait définitivement inaccessible — générez une série maintenant.";
 etatCodes.className=d.remaining?'muted':'codes-manquants';}catch(e){etatCodes.textContent='';}}
document.querySelector('#regenerer-codes').onclick=async()=>{erreurCodes.className='form-error';
 try{const d=await json('/api/auth/recovery-codes',{method:'POST'});
  affiches.innerHTML='<p class="codes-avis"><b>Notez-les maintenant.</b> Ils ne seront plus jamais affichés, et l\\'ancienne série ne fonctionne plus. Chaque code ne sert qu\\'une fois.</p><div class="codes-liste">'+d.recovery_codes.map(c=>`<code>${esc(c)}</code>`).join('')+'</div>';
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

AUTH_HTML = page(title="Connexion — MONL", description="Accédez à votre espace Monl.",
                 body=AUTH_BODY, extra_css=CSS, scripts=AUTH_SCRIPT)
ACCOUNT_HTML = page(title="Votre compte — MONL", description="Vos projets compilés avec Monl.",
                    body=ACCOUNT_BODY, active="account", extra_css=CSS, scripts=ACCOUNT_SCRIPT)
