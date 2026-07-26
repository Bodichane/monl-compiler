// AtelierVélo — interface écrite contre le contrat monl (frontend_contract.json).
//
// Toutes les routes appelées ici figurent dans le contrat :
//   GET    /product          (public, paginé)      GET  /product/{id}   (public)
//   POST   /product          (JWT Admin)           PUT  /product/{id}   (JWT Admin)
//   DELETE /product/{id}     (JWT Admin)
//   GET    /order            (JWT)                 POST /order          (JWT Customer)
//   PUT    /order/{id}       (JWT Customer)        DELETE /order/{id}   (JWT Customer)
//   POST   /register (rôles 'selfRegister' seulement) · POST /login · POST /logout
//
// Le rôle vient du jeton, jamais de la page : l'interface ne fait que MASQUER
// ce que le serveur refuserait de toute façon. Aucun script externe (contrat).
"use strict";

const API = ""; // même origine : servi sur /site par « monl run »

const etat = {
  jeton: null,
  utilisateur: null,
  role: null,
  rolesInscriptibles: ["Customer"], // aligné sur le contrat, corrigé à la volée
  modeCompte: "connexion",
  produits: [],
  rayon: null,
  panier: new Map(), // id produit -> quantité
  commandes: [],
  produitEnEdition: null,
};

const $ = (id) => document.getElementById(id);
const euros = (n) => Number(n || 0).toLocaleString("fr-FR", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + " €";

/** Référence catalogue lisible, dérivée de l'identifiant réel : ATV-007 · SÉC */
function reference(produit) {
  const rayon = (produit.category || "GEN").normalize("NFD").replace(/[^A-Za-z]/g, "").slice(0, 3).toUpperCase();
  return `ATV-${String(produit.id).padStart(3, "0")} · ${rayon}`;
}

async function api(methode, chemin, corps) {
  const entetes = {};
  if (corps) entetes["Content-Type"] = "application/json";
  if (etat.jeton) entetes["Authorization"] = "Bearer " + etat.jeton;
  let reponse;
  try {
    reponse = await fetch(API + chemin, {
      method: methode, headers: entetes,
      body: corps ? JSON.stringify(corps) : undefined,
    });
  } catch (_erreur) {
    return { statut: 0, donnees: {}, detail: "Le serveur n'a pas répondu." };
  }
  let donnees = {};
  try { donnees = await reponse.json(); } catch (_e) { /* corps non-JSON toléré */ }
  return { statut: reponse.status, donnees, detail: donnees && donnees.detail };
}

/* ------------------------------------------------------------------ vues */

function afficherVue(nom) {
  for (const vue of document.querySelectorAll(".vue")) {
    vue.hidden = vue.id !== "vue-" + nom;
  }
  for (const lien of document.querySelectorAll(".lien[data-vue]")) {
    if (lien.dataset.vue === nom) lien.setAttribute("aria-current", "page");
    else lien.removeAttribute("aria-current");
  }
  if (nom === "commandes") chargerCommandes();
  if (nom === "atelier") rendreTableAtelier();
  window.scrollTo({ top: 0, behavior: "auto" });
}

/* ------------------------------------------------------------- catalogue */

async function chargerCatalogue() {
  const etatCatalogue = $("etat-catalogue");
  const { statut, donnees } = await api("GET", "/product?limit=100");
  if (statut !== 200) {
    etatCatalogue.hidden = false;
    etatCatalogue.textContent = "Le catalogue n'a pas pu être chargé. Rechargez la page dans un instant.";
    return;
  }
  etatCatalogue.hidden = true;
  etat.produits = donnees.data || [];
  $("stat-references").textContent = donnees.total != null ? donnees.total : etat.produits.length;
  const rayons = [...new Set(etat.produits.map((p) => p.category).filter(Boolean))];
  $("stat-rayons").textContent = rayons.length;
  rendreIndex(rayons);
  rendreGrille();
}

function rendreIndex(rayons) {
  const liste = $("index-rayons");
  liste.textContent = "";
  const entrees = [{ nom: null, libelle: "Tout le catalogue" }]
    .concat(rayons.map((r) => ({ nom: r, libelle: r })));
  for (const entree of entrees) {
    const li = document.createElement("li");
    const bouton = document.createElement("button");
    bouton.type = "button";
    bouton.setAttribute("aria-pressed", String(etat.rayon === entree.nom));
    const compte = entree.nom
      ? etat.produits.filter((p) => p.category === entree.nom).length
      : etat.produits.length;
    const libelle = document.createElement("span");
    libelle.textContent = entree.libelle;
    const puce = document.createElement("span");
    puce.className = "index__puce";
    puce.textContent = String(compte).padStart(2, "0");
    bouton.append(libelle, puce);
    bouton.addEventListener("click", () => {
      etat.rayon = entree.nom;
      rendreIndex(rayons);
      rendreGrille();
    });
    li.append(bouton);
    liste.append(li);
  }
}

function produitsAffiches() {
  return etat.rayon ? etat.produits.filter((p) => p.category === etat.rayon) : etat.produits;
}

function rendreGrille() {
  const grille = $("grille-produits");
  grille.textContent = "";
  const liste = produitsAffiches();
  $("titre-rayon").textContent = etat.rayon || "Toutes les références";
  $("compte-affiche").textContent = liste.length + (liste.length > 1 ? " références" : " référence");

  if (!liste.length) {
    const vide = document.createElement("p");
    vide.className = "vide";
    vide.textContent = "Aucune référence dans ce rayon pour le moment.";
    grille.append(vide);
    return;
  }

  for (const produit of liste) {
    const carte = document.createElement("article");
    carte.className = "fiche";

    const figure = document.createElement("figure");
    figure.className = "fiche__figure";
    const coin = document.createElement("span");
    coin.className = "fiche__coin";
    const image = document.createElement("img");
    image.src = produit.imageUrl || "diagrammes/outils.svg";
    image.alt = "Diagramme technique — " + produit.name;
    image.loading = "lazy";
    figure.append(image, coin);

    const corps = document.createElement("div");
    corps.className = "fiche__corps";

    const ref = document.createElement("p");
    ref.className = "fiche__ref";
    ref.textContent = reference(produit);

    const nom = document.createElement("h3");
    nom.className = "fiche__nom";
    nom.textContent = produit.name;

    const desc = document.createElement("p");
    desc.className = "fiche__desc";
    desc.textContent = produit.description || "";

    const ligne = document.createElement("div");
    ligne.className = "fiche__ligne";
    const prix = document.createElement("span");
    prix.className = "fiche__prix";
    prix.textContent = euros(produit.price);
    const stock = document.createElement("span");
    stock.className = "fiche__stock" + (produit.stock <= 10 ? " fiche__stock--bas" : "");
    stock.textContent = produit.stock > 0 ? `${produit.stock} en stock` : "sur commande";
    ligne.append(prix, stock);

    const ajouter = document.createElement("button");
    ajouter.type = "button";
    ajouter.className = "bouton bouton--primaire bouton--bloc";
    ajouter.textContent = "Ajouter à la commande";
    ajouter.addEventListener("click", () => ajouterAuPanier(produit.id));

    corps.append(ref, nom, desc, ligne, ajouter);
    carte.append(figure, corps);
    grille.append(carte);
  }
}

/* ------------------------------------------------------- commande en cours */

function ajouterAuPanier(id) {
  etat.panier.set(id, (etat.panier.get(id) || 0) + 1);
  rendrePanier();
  ouvrirTiroir("panier");
}

function totalPanier() {
  let total = 0;
  for (const [id, quantite] of etat.panier) {
    const produit = etat.produits.find((p) => p.id === id);
    if (produit) total += Number(produit.price) * quantite;
  }
  return Math.round(total * 100) / 100;
}

function rendrePanier() {
  const corps = $("corps-panier");
  corps.textContent = "";
  $("panier-compte").textContent = [...etat.panier.values()].reduce((a, b) => a + b, 0);
  $("total-panier").textContent = euros(totalPanier());

  if (!etat.panier.size) {
    const vide = document.createElement("p");
    vide.className = "vide";
    vide.textContent = "Aucun article. Ajoutez une référence depuis le catalogue.";
    corps.append(vide);
    $("valider-panier").disabled = true;
    return;
  }
  $("valider-panier").disabled = false;

  for (const [id, quantite] of etat.panier) {
    const produit = etat.produits.find((p) => p.id === id);
    if (!produit) continue;
    const ligne = document.createElement("div");
    ligne.className = "ligne-panier";

    const nom = document.createElement("span");
    nom.className = "ligne-panier__nom";
    nom.textContent = produit.name;

    const prix = document.createElement("span");
    prix.className = "ligne-panier__prix";
    prix.textContent = euros(Number(produit.price) * quantite);

    const reglage = document.createElement("div");
    reglage.className = "ligne-panier__reglage";
    const moins = document.createElement("button");
    moins.type = "button"; moins.textContent = "−";
    moins.setAttribute("aria-label", "Retirer un " + produit.name);
    moins.addEventListener("click", () => {
      const nouvelle = quantite - 1;
      if (nouvelle <= 0) etat.panier.delete(id); else etat.panier.set(id, nouvelle);
      rendrePanier();
    });
    const compte = document.createElement("span");
    compte.className = "ligne-panier__quantite";
    compte.textContent = String(quantite);
    const plus = document.createElement("button");
    plus.type = "button"; plus.textContent = "+";
    plus.setAttribute("aria-label", "Ajouter un " + produit.name);
    plus.addEventListener("click", () => ajouterAuPanier(id));
    reglage.append(moins, compte, plus);

    ligne.append(nom, prix, reglage);
    corps.append(ligne);
  }
}

async function envoyerCommande() {
  const message = $("message-panier");
  if (!etat.jeton) {
    afficherMessage(message, "Connectez-vous pour envoyer la commande.", "erreur");
    ouvrirTiroir("compte");
    return;
  }
  const lignes = [...etat.panier.entries()].map(([id, quantite]) => {
    const produit = etat.produits.find((p) => p.id === id);
    return `${quantite} × ${produit ? produit.name : "réf. " + id}`;
  });
  const note = ($("note-panier").value || "").trim();
  const { statut, detail } = await api("POST", "/order", {
    total: totalPanier(),
    status: "À préparer",
    note: [lignes.join(" · "), note].filter(Boolean).join("\n"),
  });
  if (statut === 200) {
    etat.panier.clear();
    $("note-panier").value = "";
    rendrePanier();
    afficherMessage(message, "Commande envoyée. L'atelier la prépare sous 48 h.", "ok");
    chargerCommandes();
  } else if (statut === 403) {
    afficherMessage(message, "Ce compte ne peut pas passer commande : le rôle client est requis.", "erreur");
  } else {
    afficherMessage(message, detail || "La commande n'a pas pu être envoyée.", "erreur");
  }
}

/* ------------------------------------------------------------- commandes */

async function chargerCommandes() {
  if (!etat.jeton) return;
  const zone = $("liste-commandes");
  const { statut, donnees } = await api("GET", "/order?limit=50");
  if (statut !== 200) {
    $("etat-commandes").hidden = false;
    $("etat-commandes").textContent = "Les commandes n'ont pas pu être chargées.";
    return;
  }
  $("etat-commandes").hidden = true;
  etat.commandes = donnees.data || [];
  zone.textContent = "";

  if (!etat.commandes.length) {
    const vide = document.createElement("p");
    vide.className = "vide";
    vide.textContent = "Aucune commande pour l'instant. Le catalogue vous attend.";
    zone.append(vide);
    return;
  }

  for (const commande of etat.commandes) {
    const carte = document.createElement("article");
    carte.className = "commande";

    const gauche = document.createElement("div");
    const ref = document.createElement("p");
    ref.className = "commande__ref";
    ref.textContent = `COMMANDE N° ${String(commande.id).padStart(4, "0")}`;
    const total = document.createElement("p");
    total.className = "commande__total";
    total.textContent = euros(commande.total);
    const statutEtiquette = document.createElement("span");
    statutEtiquette.className = "etiquette" + (commande.status === "À préparer" ? " etiquette--vif" : "");
    statutEtiquette.textContent = commande.status || "—";
    const note = document.createElement("p");
    note.className = "commande__note";
    note.textContent = commande.note || "";
    gauche.append(ref, total, statutEtiquette, note);

    const actions = document.createElement("div");
    actions.className = "commande__actions";
    if (etat.role !== "Admin") {
      const modifier = document.createElement("button");
      modifier.type = "button";
      modifier.className = "bouton bouton--discret";
      modifier.textContent = "Modifier la note";
      modifier.addEventListener("click", () => modifierNote(commande));
      const annuler = document.createElement("button");
      annuler.type = "button";
      annuler.className = "bouton bouton--discret bouton--danger";
      annuler.textContent = "Annuler";
      annuler.addEventListener("click", () => annulerCommande(commande));
      actions.append(modifier, annuler);
    }

    carte.append(gauche, actions);
    zone.append(carte);
  }
}

async function modifierNote(commande) {
  const nouvelle = window.prompt("Note pour l'atelier :", commande.note || "");
  if (nouvelle === null) return;
  const { statut } = await api("PUT", `/order/${commande.id}`, {
    total: commande.total, status: commande.status, note: nouvelle,
  });
  if (statut === 200) chargerCommandes();
}

async function annulerCommande(commande) {
  if (!window.confirm(`Annuler la commande n° ${commande.id} ?`)) return;
  const { statut } = await api("DELETE", `/order/${commande.id}`);
  if (statut === 200) chargerCommandes();
}

/* ------------------------------------------------ gestion du catalogue */

function rendreTableAtelier() {
  const zone = $("table-atelier");
  zone.textContent = "";
  for (const produit of etat.produits) {
    const rangee = document.createElement("div");
    rangee.className = "rangee";

    const nom = document.createElement("div");
    nom.className = "rangee__nom";
    nom.textContent = produit.name;
    const ref = document.createElement("div");
    ref.className = "rangee__meta";
    ref.textContent = reference(produit);
    const stock = document.createElement("div");
    stock.className = "rangee__meta";
    stock.textContent = `${produit.stock} en stock · ${euros(produit.price)}`;

    const actions = document.createElement("div");
    actions.className = "commande__actions";
    const modifier = document.createElement("button");
    modifier.type = "button";
    modifier.className = "bouton bouton--discret";
    modifier.textContent = "Modifier";
    modifier.addEventListener("click", () => chargerProduitDansFormulaire(produit));
    const supprimer = document.createElement("button");
    supprimer.type = "button";
    supprimer.className = "bouton bouton--discret bouton--danger";
    supprimer.textContent = "Retirer";
    supprimer.addEventListener("click", () => supprimerProduit(produit));
    actions.append(modifier, supprimer);

    rangee.append(nom, ref, stock, actions);
    zone.append(rangee);
  }
}

function chargerProduitDansFormulaire(produit) {
  const formulaire = $("form-produit");
  etat.produitEnEdition = produit.id;
  for (const champ of ["name", "price", "category", "stock", "description", "imageUrl"]) {
    formulaire.elements[champ].value = produit[champ] != null ? produit[champ] : "";
  }
  $("titre-form-produit").textContent = `Modifier « ${produit.name} »`;
  $("bouton-produit").textContent = "Enregistrer les modifications";
  $("annuler-produit").hidden = false;
  formulaire.scrollIntoView({ block: "start" });
}

function reinitialiserFormulaireProduit() {
  etat.produitEnEdition = null;
  $("form-produit").reset();
  $("titre-form-produit").textContent = "Ajouter une référence";
  $("bouton-produit").textContent = "Ajouter au catalogue";
  $("annuler-produit").hidden = true;
}

async function soumettreProduit(evenement) {
  evenement.preventDefault();
  const formulaire = $("form-produit");
  const message = $("message-produit");
  const corps = {
    name: formulaire.elements.name.value.trim(),
    price: Number(formulaire.elements.price.value),
    description: formulaire.elements.description.value.trim(),
    imageUrl: formulaire.elements.imageUrl.value.trim() || "diagrammes/outils.svg",
    category: formulaire.elements.category.value.trim(),
    stock: parseInt(formulaire.elements.stock.value, 10),
  };
  if (!corps.name || !corps.category || Number.isNaN(corps.price) || Number.isNaN(corps.stock)) {
    afficherMessage(message, "Nom, rayon, prix et stock sont nécessaires.", "erreur");
    return;
  }
  const { statut, detail } = etat.produitEnEdition
    ? await api("PUT", `/product/${etat.produitEnEdition}`, corps)
    : await api("POST", "/product", corps);

  if (statut === 200) {
    afficherMessage(message, etat.produitEnEdition ? "Référence mise à jour." : "Référence ajoutée au catalogue.", "ok");
    reinitialiserFormulaireProduit();
    await chargerCatalogue();
    rendreTableAtelier();
  } else if (statut === 403) {
    afficherMessage(message, "Seul le compte atelier peut modifier le catalogue.", "erreur");
  } else {
    afficherMessage(message, detail || "L'enregistrement a échoué.", "erreur");
  }
}

async function supprimerProduit(produit) {
  if (!window.confirm(`Retirer « ${produit.name} » du catalogue ?`)) return;
  const { statut, detail } = await api("DELETE", `/product/${produit.id}`);
  if (statut === 200) {
    await chargerCatalogue();
    rendreTableAtelier();
  } else {
    afficherMessage($("message-produit"), detail || "La suppression a échoué.", "erreur");
  }
}

/* ------------------------------------------------------------------ compte */

function afficherMessage(element, texte, ton) {
  element.hidden = false;
  element.textContent = texte;
  element.className = "message" + (ton ? " message--" + ton : "");
}

function basculerModeCompte() {
  etat.modeCompte = etat.modeCompte === "connexion" ? "inscription" : "connexion";
  const inscription = etat.modeCompte === "inscription";
  $("titre-compte").textContent = inscription ? "Créer un compte client" : "Se connecter";
  $("bouton-compte").textContent = inscription ? "Créer le compte" : "Se connecter";
  $("bascule-texte").textContent = inscription ? "Vous avez déjà un compte ?" : "Pas encore de compte ?";
  $("bascule-compte").textContent = inscription ? "Se connecter" : "Créer un compte client";
  $("aide-compte").textContent = inscription
    ? "8 caractères minimum. L'inscription crée un compte client ; le compte atelier est créé sur le serveur."
    : "8 caractères minimum.";
  $("message-compte").hidden = true;
}

async function soumettreCompte(evenement) {
  evenement.preventDefault();
  const formulaire = $("form-compte");
  const message = $("message-compte");
  const identifiant = formulaire.elements.username.value.trim();
  const motDePasse = formulaire.elements.password.value;
  if (identifiant.length < 3 || motDePasse.length < 8) {
    afficherMessage(message, "Identifiant de 3 caractères et mot de passe de 8 caractères minimum.", "erreur");
    return;
  }

  if (etat.modeCompte === "inscription") {
    const role = etat.rolesInscriptibles[0];
    if (!role) {
      afficherMessage(message, "L'inscription en ligne est fermée : demandez un compte à l'atelier.", "erreur");
      return;
    }
    const inscription = await api("POST", "/register", { username: identifiant, password: motDePasse, actor: role });
    if (inscription.statut === 409) {
      afficherMessage(message, "Cet identifiant est déjà pris.", "erreur");
      return;
    }
    if (inscription.statut === 403) {
      afficherMessage(message, "Ce rôle n'est pas ouvert à l'inscription en ligne.", "erreur");
      return;
    }
    if (inscription.statut === 429) {
      afficherMessage(message, "Trop de tentatives. Réessayez dans une minute.", "erreur");
      return;
    }
    if (inscription.statut !== 200) {
      afficherMessage(message, inscription.detail || "La création du compte a échoué.", "erreur");
      return;
    }
  }

  const connexion = await api("POST", "/login", { username: identifiant, password: motDePasse });
  if (connexion.statut === 429) {
    afficherMessage(message, "Trop de tentatives. Réessayez dans une minute.", "erreur");
    return;
  }
  if (connexion.statut !== 200 || !connexion.donnees.access_token) {
    afficherMessage(message, "Identifiant ou mot de passe incorrect.", "erreur");
    return;
  }

  etat.jeton = connexion.donnees.access_token;
  etat.utilisateur = identifiant;
  etat.role = lireRole(etat.jeton);
  formulaire.reset();
  majEtatConnexion();
  afficherMessage(message, "Connexion établie.", "ok");
}

/** Lit le rôle porté par le jeton — pour ADAPTER l'affichage seulement :
 *  toute autorisation réelle est vérifiée côté serveur, à chaque appel. */
function lireRole(jeton) {
  try {
    const charge = jeton.split(".")[1].replace(/-/g, "+").replace(/_/g, "/");
    return JSON.parse(decodeURIComponent(escape(atob(charge)))).actor;
  } catch (_erreur) {
    return null;
  }
}

function majEtatConnexion() {
  const connecte = Boolean(etat.jeton);
  $("lien-commandes").hidden = !connecte;
  $("lien-atelier").hidden = etat.role !== "Admin";
  $("form-compte").hidden = connecte;
  $("compte-connecte").hidden = !connecte;
  document.querySelector(".bascule").hidden = connecte;
  $("lien-compte").textContent = connecte ? etat.utilisateur : "Se connecter";
  $("titre-compte").textContent = connecte ? "Votre compte" : (etat.modeCompte === "inscription" ? "Créer un compte client" : "Se connecter");
  if (connecte) {
    $("compte-nom").textContent = etat.utilisateur;
    $("compte-role").textContent = etat.role === "Admin" ? "atelier" : "client";
  }
}

async function seDeconnecter() {
  await api("POST", "/logout");
  etat.jeton = null;
  etat.utilisateur = null;
  etat.role = null;
  etat.commandes = [];
  majEtatConnexion();
  afficherVue("catalogue");
  fermerTiroirs();
}

/* ------------------------------------------------------------------ tiroirs */

function ouvrirTiroir(nom) {
  fermerTiroirs();
  $("tiroir-" + nom).hidden = false;
  $("voile").hidden = false;
  if (nom === "panier") $("panier-bouton").setAttribute("aria-expanded", "true");
}

function fermerTiroirs() {
  $("tiroir-panier").hidden = true;
  $("tiroir-compte").hidden = true;
  $("voile").hidden = true;
  $("panier-bouton").setAttribute("aria-expanded", "false");
}

/* -------------------------------------------------------------- démarrage */

function brancherEvenements() {
  for (const lien of document.querySelectorAll(".lien[data-vue]")) {
    lien.addEventListener("click", () => afficherVue(lien.dataset.vue));
  }
  $("lien-compte").addEventListener("click", () => ouvrirTiroir("compte"));
  $("panier-bouton").addEventListener("click", () => ouvrirTiroir("panier"));
  $("fermer-panier").addEventListener("click", fermerTiroirs);
  $("fermer-compte").addEventListener("click", fermerTiroirs);
  $("voile").addEventListener("click", fermerTiroirs);
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") fermerTiroirs(); });

  $("valider-panier").addEventListener("click", envoyerCommande);
  $("form-compte").addEventListener("submit", soumettreCompte);
  $("bascule-compte").addEventListener("click", basculerModeCompte);
  $("bouton-deconnexion").addEventListener("click", seDeconnecter);
  $("form-produit").addEventListener("submit", soumettreProduit);
  $("annuler-produit").addEventListener("click", reinitialiserFormulaireProduit);
}

function demarrer() {
  brancherEvenements();
  rendrePanier();
  majEtatConnexion();
  chargerCatalogue();
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", demarrer);
} else {
  demarrer();
}
