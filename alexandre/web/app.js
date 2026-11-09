// Interface d'Alexandre. Protocole WebSocket décrit dans boulangerie/serveur.py.
// Règle de sécurité : aucun texte reçu n'est inséré comme HTML (textContent uniquement).
"use strict";

const $ = (id) => document.getElementById(id);
const el = (balise, classe, texte) => {
  const n = document.createElement(balise);
  if (classe) n.className = classe;
  if (texte !== undefined && texte !== null) n.textContent = String(texte);
  return n;
};

const SUGGESTIONS = [
  ["Combien de beurre ?", "Il me reste combien de beurre ? Faut que je commande ?"],
  ["Urgences", "Y a-t-il des trucs à commander en urgence ?"],
  ["Baguettes demain", "Combien de baguettes je dois pétrir demain matin ?"],
  ["Ventes de la semaine", "Combien de croissants j'ai vendu la semaine dernière ?"],
];
const LIBELLES_OUTILS = {
  consulter_boulangerie: "Je consulte tes données",
  prevoir_production: "Je calcule la prévision",
  passer_commande: "J'envoie la commande",
};

const nombre = new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 2 });
const euros = new Intl.NumberFormat("fr-FR", { style: "currency", currency: "EUR" });
const fmt = (v) => (v === null || v === undefined ? "—" : nombre.format(v));
const fmtEuros = (v) => (v === null || v === undefined ? "—" : euros.format(v));
const avecUnite = (v, unite) => (unite ? `${fmt(v)} ${unite}` : fmt(v));

// --- État ---------------------------------------------------------------------
let socket = null;
let occupe = false;
let tentatives = 0;
let minuterieHumeur = null;
let etapesEnCours = [];

// --- Avatar -------------------------------------------------------------------
async function chargerAvatar() {
  try {
    const reponse = await fetch("/static/avatar.svg");
    const svg = new DOMParser().parseFromString(await reponse.text(), "image/svg+xml").documentElement;
    $("avatar").replaceChildren(document.importNode(svg, true));
  } catch {
    /* sans avatar, l'interface reste utilisable */
  }
}

function humeur(valeur) {
  const avatar = $("avatar");
  clearTimeout(minuterieHumeur);
  avatar.classList.remove("humeur-repos", "humeur-petrit", "humeur-pret");
  void avatar.offsetWidth; // relance l'animation
  avatar.classList.add(`humeur-${valeur}`);
  if (valeur === "pret") minuterieHumeur = setTimeout(() => humeur("repos"), 2400);
}

// --- Rendu du texte : paragraphes, listes, **gras** ---------------------------
function ajouterEnLigne(parent, texte) {
  texte.split(/(\*\*[^*]+\*\*)/g).forEach((morceau) => {
    if (!morceau) return;
    if (morceau.startsWith("**") && morceau.endsWith("**") && morceau.length > 4) {
      parent.append(el("strong", null, morceau.slice(2, -2)));
    } else {
      parent.append(document.createTextNode(morceau.replace(/\*\*/g, "")));
    }
  });
}

function rendreTexte(conteneur, texte) {
  let liste = null;
  String(texte).split("\n").forEach((brute) => {
    const ligne = brute.trim();
    if (!ligne) { liste = null; return; }
    const puce = ligne.match(/^([-*•]|\d+[.)])\s+(.*)$/);
    if (puce) {
      if (!liste) { liste = el("ul"); conteneur.append(liste); }
      const li = el("li");
      ajouterEnLigne(li, puce[2]);
      liste.append(li);
    } else {
      liste = null;
      const p = el("p");
      ajouterEnLigne(p, ligne);
      conteneur.append(p);
    }
  });
}

// --- Fil de conversation ------------------------------------------------------
function defiler() {
  requestAnimationFrame(() => { $("fil").scrollTop = $("fil").scrollHeight; });
}

function messageMadeleine(texte) {
  const m = el("div", "message madeleine");
  m.append(el("div", "bulle", texte));
  $("messages").append(m);
  defiler();
}

function messageBot(texte, { cartes = [], outils = [], erreur = false } = {}) {
  const m = el("div", "message bot");
  if (outils.length) {
    const liste = el("ul", "outils-utilises");
    liste.setAttribute("aria-label", "Outils utilisés");
    outils.forEach((nom) => {
      const li = el("li", null, LIBELLES_OUTILS[nom] || "Outil");
      li.append(el("code", null, nom));
      liste.append(li);
    });
    m.append(liste);
  }
  if (texte) {
    const bulle = el("div", erreur ? "bulle erreur" : "bulle");
    rendreTexte(bulle, texte);
    m.append(bulle);
  }
  cartes.forEach((carte) => { const c = rendreCarte(carte); if (c) m.append(c); });
  $("messages").append(m);
  defiler();
  return m;
}

// --- Cartes -------------------------------------------------------------------
function jauge(part, classe) {
  const piste = el("div", "jauge");
  const barre = el("div", classe || "");
  barre.style.width = `${Math.max(0, Math.min(1, part || 0)) * 100}%`;
  piste.append(barre);
  return piste;
}

function ligneJauge(libelle, valeur, part, classe) {
  const ligne = el("div", "ligne");
  const titre = el("div", "ligne-titre");
  titre.append(el("span", null, libelle), el("span", null, valeur));
  ligne.append(titre, jauge(part, classe));
  return ligne;
}

function entete(titre, note) {
  const e = el("div", "carte-entete");
  e.append(el("h2", null, titre));
  if (note) e.append(el("span", "note", note));
  return e;
}

function chiffre(valeur, legende) {
  const c = el("div", "chiffre");
  c.append(el("strong", null, valeur), el("span", null, legende));
  return c;
}

function boutonAction(libelle, message) {
  const b = el("button", "bouton principal", libelle);
  b.type = "button";
  b.addEventListener("click", () => { if (envoyer(message)) b.disabled = true; });
  return b;
}

function carteStock(c) {
  const carte = el("section", "carte");
  carte.append(entete(c.titre));
  if (c.items.length === 1) {
    const i = c.items[0];
    carte.append(chiffre(avecUnite(i.quantite, i.unite), `seuil d'alerte : ${avecUnite(i.seuil_alerte, i.unite)}`));
    carte.append(jauge(i.niveau, i.sous_seuil ? "alerte" : ""));
    if (i.fournisseur) carte.append(el("span", "note", `Fournisseur : ${i.fournisseur}`));
  } else {
    c.items.forEach((i) => carte.append(
      ligneJauge(i.ingredient, `${fmt(i.quantite)} / ${avecUnite(i.seuil_alerte, i.unite)}`, i.niveau, i.sous_seuil ? "alerte" : "")
    ));
  }
  if (c.action) {
    const actions = el("div", "actions");
    actions.append(boutonAction(c.action.libelle, c.action.message));
    carte.append(actions);
  }
  return carte;
}

function carteVentes(c) {
  const carte = el("section", "carte");
  carte.append(entete(c.titre));
  carte.append(chiffre(fmt(c.total_quantite), `articles vendus · ${fmtEuros(c.total_ca)}`));
  c.barres.forEach((b) => carte.append(ligneJauge(b.libelle, fmt(b.valeur), b.part, "accent")));
  return carte;
}

function carteMarge(c) {
  const carte = el("section", "carte");
  carte.append(entete(c.titre));
  c.items.forEach((p) => {
    if (c.items.length > 1) carte.append(el("span", "note", p.produit));
    carte.append(chiffre(fmtEuros(p.marge_unitaire), `par pièce · ${fmt(p.marge_pct)} %`));
    const d = el("dl", "details");
    d.append(el("dt", null, "Prix de vente"), el("dd", null, fmtEuros(p.prix_vente_ttc)));
    d.append(el("dt", null, "Coût de revient"), el("dd", null, fmtEuros(p.cout_revient)));
    carte.append(d);
  });
  return carte;
}

function cartePrevision(c) {
  const carte = el("section", "carte");
  carte.append(entete(c.titre, "moyenne + 10 %"));
  carte.append(chiffre(fmt(c.principal.recommandation), c.principal.produit));
  if (c.fragile) {
    const obs = c.principal.observations;
    carte.append(el("span", "etiquette", `Estimation fragile · ${obs} observation${obs > 1 ? "s" : ""}`));
  }
  if (c.barres.length > 1) c.barres.forEach((b) => carte.append(ligneJauge(b.libelle, fmt(b.valeur), b.part, "accent")));
  return carte;
}

function carteCommande(c) {
  const carte = el("section", c.partielle ? "carte partielle" : "carte confirmation");
  carte.append(entete(c.partielle ? "Email parti, commande gardée de côté" : "Commande envoyée", c.reference));
  const d = el("dl", "details");
  d.append(el("dt", null, "Fournisseur"), el("dd", null, c.fournisseur || "—"));
  d.append(el("dt", null, "Envoyée à"), el("dd", null, c.destinataire || "—"));
  carte.append(d);
  return carte;
}

function rendreCarte(c) {
  const rendus = { stock: carteStock, ventes: carteVentes, marge: carteMarge, prevision: cartePrevision, commande: carteCommande };
  return rendus[c.type] ? rendus[c.type](c) : null;
}

// --- Validation des commandes -------------------------------------------------
function afficherValidations(demandes) {
  const decisions = new Array(demandes.length).fill(null);
  const m = el("div", "message bot");
  const intro = el("div", "bulle");
  rendreTexte(intro, demandes.length > 1
    ? `J'ai préparé **${demandes.length} commandes**. Dis-moi lesquelles j'envoie.`
    : "Voici le mail que je m'apprête à envoyer. **Je l'envoie ?**");
  m.append(intro);

  demandes.forEach((d, index) => {
    const carte = el("section", "carte alerte");
    carte.append(entete("Brouillon de commande", "rien ne part sans ton accord"));
    const details = el("dl", "details");
    details.append(el("dt", null, "À"), el("dd", null, d.destinataire ? `${d.fournisseur} (${d.destinataire})` : `${d.fournisseur} — adresse introuvable dans tes fiches`));
    details.append(el("dt", null, "Objet"), el("dd", null, d.objet));
    details.append(el("dt", null, "Commande"), el("dd", null, d.produits));
    if (d.montant_estime !== null && d.montant_estime !== undefined) {
      details.append(el("dt", null, "Montant estimé"), el("dd", null, fmtEuros(d.montant_estime)));
    }
    carte.append(details, el("pre", "brouillon", d.corps));

    const actions = el("div", "actions");
    const oui = el("button", "bouton principal", "Envoyer");
    const non = el("button", "bouton secondaire", "Ne pas envoyer");
    oui.type = non.type = "button";
    const decider = (valeur) => {
      decisions[index] = valeur;
      actions.replaceChildren(el("span", "choix-fait", valeur ? "✓ Validé" : "✋ Pas envoyé"));
      if (decisions.every((x) => x !== null)) envoyerTrame({ type: "validation", decisions });
    };
    oui.addEventListener("click", () => decider(true));
    non.addEventListener("click", () => decider(false));
    actions.append(oui, non);
    carte.append(actions);
    m.append(carte);
  });
  $("messages").append(m);
  defiler();
}

// --- Indicateur de travail ----------------------------------------------------
function demarrerTravail() {
  occupe = true;
  document.body.classList.add("occupe");
  etapesEnCours = [];
  $("etapes").replaceChildren();
  $("frappe").hidden = false;
  humeur("petrit");
  defiler();
}

function finirTravail() {
  occupe = false;
  document.body.classList.remove("occupe");
  $("frappe").hidden = true;
  const outils = etapesEnCours.map((e) => e.nom);
  etapesEnCours = [];
  return outils;
}

function etapeOutil(nom, etat) {
  if (etat === "debut") {
    const li = el("li", null, LIBELLES_OUTILS[nom] || "Je consulte");
    li.append(el("code", null, nom));
    $("etapes").append(li);
    etapesEnCours.push({ nom, li });
  } else {
    const etape = etapesEnCours.find((e) => e.nom === nom && !e.li.classList.contains("fait"));
    if (etape) etape.li.classList.add("fait");
  }
  defiler();
}

// --- WebSocket ----------------------------------------------------------------
function statut(enLigne, texte) {
  document.querySelector(".statut").classList.toggle("en-ligne", enLigne);
  $("statut").textContent = texte;
}

function envoyerTrame(trame) {
  if (!socket || socket.readyState !== WebSocket.OPEN) return false;
  socket.send(JSON.stringify(trame));
  return true;
}

function envoyer(texte) {
  const propre = (texte || "").trim();
  if (!propre || occupe) return false;
  if (!envoyerTrame({ type: "message", texte: propre })) return false;
  messageMadeleine(propre);
  return true;
}

function recevoir(evenement) {
  switch (evenement.type) {
    case "bienvenue": {
      $("messages").replaceChildren();
      $("date").textContent = `Aujourd'hui · ${evenement.date}`;
      $("date").hidden = false;
      messageBot("Bonjour Madeleine ! Je regarde tes **stocks**, tes **ventes** et tes **produits**, et je prépare tes commandes. Qu'est-ce que je peux faire pour toi ?");
      if (evenement.alerte) {
        const m = messageBot("J'ai jeté un œil à tes stocks avant ton arrivée : ces ingrédients sont sous leur seuil.", { cartes: [evenement.alerte] });
        const carte = m.querySelector(".carte");
        if (carte) {
          carte.classList.add("alerte");
          const actions = carte.querySelector(".actions") || carte.appendChild(el("div", "actions"));
          const plusTard = el("button", "bouton secondaire", "Plus tard");
          plusTard.type = "button";
          plusTard.addEventListener("click", () => actions.replaceChildren(el("span", "choix-fait", "D'accord, on verra plus tard.")));
          actions.append(plusTard);
        }
      }
      humeur("repos");
      break;
    }
    case "humeur":
      demarrerTravail();
      break;
    case "outil":
      etapeOutil(evenement.nom, evenement.etat);
      break;
    case "validation":
      finirTravail();
      humeur("repos");
      afficherValidations(evenement.demandes);
      break;
    case "reponse": {
      const outils = finirTravail();
      messageBot(evenement.texte, { cartes: evenement.cartes || [], outils });
      humeur("pret");
      break;
    }
    case "erreur":
      finirTravail();
      messageBot(evenement.texte, { erreur: true });
      humeur("repos");
      break;
    default:
      break;
  }
}

function connecter() {
  const protocole = location.protocol === "https:" ? "wss" : "ws";
  socket = new WebSocket(`${protocole}://${location.host}/ws`);
  socket.addEventListener("open", () => { tentatives = 0; statut(true, "Fournil ouvert · en ligne"); });
  socket.addEventListener("message", (e) => {
    try { recevoir(JSON.parse(e.data)); } catch { /* trame illisible ignorée */ }
  });
  socket.addEventListener("close", () => {
    if (occupe) { finirTravail(); humeur("repos"); }
    statut(false, "Fournil fermé · reconnexion…");
    const delai = Math.min(1000 * 2 ** tentatives, 10000);
    tentatives += 1;
    setTimeout(connecter, delai);
  });
}

// --- Démarrage ----------------------------------------------------------------
function initialiser() {
  chargerAvatar();
  SUGGESTIONS.forEach(([libelle, message]) => {
    const puce = el("button", "puce", libelle);
    puce.type = "button";
    puce.addEventListener("click", () => envoyer(message));
    $("puces").append(puce);
  });
  $("formulaire").addEventListener("submit", (e) => {
    e.preventDefault();
    if (envoyer($("champ").value)) $("champ").value = "";
  });
  $("nouvelle").addEventListener("click", () => {
    if (socket) socket.close(); // le serveur ouvre une nouvelle conversation à la reconnexion
  });
  connecter();
}

initialiser();
