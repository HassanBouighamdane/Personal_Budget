/* ===== Mon Budget — app.js =====
 * Toute la logique frontend : appels API, rendu, graphiques.
 * API_URL = "" quand le frontend est servi par le backend (même origine).
 * Si le frontend est hébergé ailleurs (Next.js, autre port...),
 * mettre par exemple : const API_URL = "http://localhost:8500";
 */
const API_URL = "";

const PALETTE = ['#f2a63c','#55c3ee','#34d399','#a78bfa','#f4726d','#e8d44c','#2dd4bf','#e88f4c','#818cf8','#e879f9','#8d98b4'];
const MOIS_FR = ['Janvier','Février','Mars','Avril','Mai','Juin','Juillet','Août','Septembre','Octobre','Novembre','Décembre'];

if (window.Chart) {
  Chart.defaults.color = '#8d98b4';
  Chart.defaults.borderColor = '#263250';
}

let cats = [], sources = [], paiements = [], paySel = null;
let charts = {};

const $ = id => document.getElementById(id);
// Affichage : jusqu'à 2 décimales (les centimes ne s'affichent que s'ils existent)
const fmt = v => (+v).toLocaleString('fr-FR', { maximumFractionDigits: 2 }) + ' DH';
// Lecture d'un montant saisi : accepte virgule ou point, arrondit à 2 décimales
const lireMontant = id => {
  const brut = $(id).value.trim().replace(/\s/g, '').replace(',', '.');
  const v = parseFloat(brut);
  return isNaN(v) ? NaN : Math.round(v * 100) / 100;
};
// Date du jour en heure LOCALE (toISOString() convertit en UTC et peut décaler d'un jour)
const auj = () => {
  const d = new Date();
  return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0');
};
let moisCour = auj().slice(0, 7);

/* ---------------- Utilitaires ---------------- */
function toast(msg, ok = true) {
  const t = $('toast');
  t.textContent = msg;
  t.style.background = ok ? 'var(--green)' : 'var(--red)';
  t.style.color = ok ? '#052e16' : '#fff';
  t.style.display = 'block';
  setTimeout(() => t.style.display = 'none', 1800);
}

async function api(path, opts) {
  const r = await fetch(API_URL + path, opts);
  if (r.status === 401) {
    afficherLogin(true);
    throw new Error('Non authentifié');
  }
  if (!r.ok) {
    let msg = 'Erreur';
    try { msg = (await r.json()).detail || msg; } catch (e) { }
    toast(msg, false);
    throw new Error('API ' + r.status);
  }
  return r.json();
}

/* ---------------- Authentification ---------------- */
function afficherLogin(afficher) {
  $('ecran-login').style.display = afficher ? '' : 'none';
  $('entete').style.display = afficher ? 'none' : '';
  $('contenu').style.display = afficher ? 'none' : '';
  $('nav-tabs').style.display = afficher ? 'none' : '';
  if (afficher) setTimeout(() => $('l-user').focus(), 100);
}

async function connexion() {
  const utilisateur = $('l-user').value.trim();
  const mot_de_passe = $('l-mdp').value;
  if (!utilisateur || !mot_de_passe) return toast('Utilisateur et mot de passe requis', false);
  try {
    await api('/api/login', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ utilisateur, mot_de_passe })
    });
  } catch (e) { return; }   // le message d'erreur est déjà affiché
  $('l-mdp').value = '';
  demarrerApp();
}

async function deconnexion() {
  await api('/api/logout', { method: 'POST' });
  toast('À bientôt 👋');
  afficherLogin(true);
}

async function changerMdp() {
  const actuel = $('p-mdp-actuel').value, nouveau = $('p-mdp-nouveau').value;
  if (nouveau.length < 6) return toast('6 caractères minimum', false);
  await api('/api/mot_de_passe', {
    method: 'PUT', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ actuel, nouveau })
  });
  $('p-mdp-actuel').value = ''; $('p-mdp-nouveau').value = '';
  toast('Mot de passe changé — reconnecte-toi ✓');
  setTimeout(() => afficherLogin(true), 1200);
}

function demarrerApp() {
  afficherLogin(false);
  montrer('saisie');
  chargerCats().then(chargerTransactions);
}

function montrer(t) {
  for (const x of ['saisie', 'dash', 'bourse', 'params']) {
    $('tab-' + x).style.display = x === t ? '' : 'none';
    $('b-' + x).classList.toggle('active', x === t);
  }
  if (t === 'dash') chargerDashboard();
  if (t==='bourse') chargerBourse();
  if (t === 'params') chargerParams();
  if (t === 'saisie') chargerTransactions();
}

/* ---------------- Configuration (catégories, sources, paiements) ---------------- */
async function chargerCats() {
  const d = await api('/api/categories');
  cats = d.categories;
  sources = d.sources;
  paiements = d.paiements;
  $('p-objectif').value = d.objectif_epargne;

  // Liste déroulante des catégories de dépense
  const sel = $('d-cat');
  const valCat = sel.value;
  sel.innerHTML = '<option value="" disabled selected>— Choisir une catégorie —</option>' +
    cats.map(c => `<option value="${c.nom}">${c.nom}</option>`).join('');
  if (valCat && cats.some(c => c.nom === valCat)) sel.value = valCat;

  // Liste déroulante des sources de revenu + option "Autre" avec champ libre
  const selS = $('r-source');
  const valSrc = selS.value;
  selS.innerHTML = '<option value="" disabled selected>— Choisir une source —</option>' +
    sources.map(s => `<option value="${s.nom}">${s.nom}</option>`).join('') +
    '<option value="__autre__">Autre…</option>';
  if (valSrc && (valSrc === '__autre__' || sources.some(s => s.nom === valSrc))) selS.value = valSrc;
  basculerSourceAutre();

  // Chips des types de paiement (configurables depuis Paramètres)
  if (!paySel || !paiements.some(p => p.nom === paySel)) paySel = paiements[0] ? paiements[0].nom : null;
  const pb = $('d-pays');
  pb.innerHTML = '';
  paiements.forEach(p => {
    const b = document.createElement('button');
    b.className = 'chip' + (p.nom === paySel ? ' sel' : '');
    b.textContent = p.nom;
    b.onclick = () => { paySel = p.nom; majChips(); };
    pb.appendChild(b);
  });
}

function majChips() {
  [...$('d-pays').children].forEach(b => b.classList.toggle('sel', b.textContent === paySel));
}

function basculerSourceAutre() {
  $('r-source-autre').style.display = $('r-source').value === '__autre__' ? '' : 'none';
}

/* ---------------- Saisie ---------------- */
async function ajouterDepense() {
  const montant = lireMontant('d-montant');
  const categorie = $('d-cat').value;
  if (!categorie) return toast('Choisis une catégorie', false);
  if (isNaN(montant) || montant <= 0) return toast('Montant invalide', false);
  if (!paySel) return toast('Choisis un type de paiement', false);
  await api('/api/depenses', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      date: $('d-date').value, categorie,
      description: $('d-desc').value, montant, paiement: paySel
    })
  });
  $('d-montant').value = '';
  $('d-desc').value = '';
  toast('Dépense ajoutée ✓');
  chargerTransactions();
}

async function ajouterRevenu() {
  const montant = lireMontant('r-montant');
  let source = $('r-source').value;
  if (!source) return toast('Choisis une source', false);
  if (source === '__autre__') {
    source = $('r-source-autre').value.trim();
    if (!source) return toast('Précise la source', false);
  }
  if (isNaN(montant) || montant <= 0) return toast('Montant invalide', false);
  await api('/api/revenus', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ date: $('r-date').value, source, montant })
  });
  $('r-montant').value = '';
  $('r-source-autre').value = '';
  toast('Revenu ajouté ✓');
  chargerTransactions();
}

async function suppr(type, id) {
  if (!confirm('Supprimer cette ligne ?')) return;
  await api(`/api/${type}/${id}`, { method: 'DELETE' });
  toast('Supprimé');
  chargerTransactions();
}

async function chargerTransactions() {
  const mois = auj().slice(0, 7);
  const d = await api('/api/transactions?mois=' + mois);
  const lignes = [
    ...d.depenses.map(x => ({ ...x, type: 'depenses', lbl: x.categorie + (x.description ? ' — ' + x.description : ''), cls: 'dep-amt', sg: '−' })),
    ...d.revenus.map(x => ({ ...x, type: 'revenus', lbl: x.source || 'Revenu', cls: 'rev-amt', sg: '+' }))
  ].sort((a, b) => b.date.localeCompare(a.date) || b.id - a.id);

  if (!lignes.length) {
    $('liste-trans').innerHTML = '<div class="vide">Aucune transaction ce mois — commence ta saisie ! 👆</div>';
    return;
  }
  $('liste-trans').innerHTML = '<table><tbody>' + lignes.map(l =>
    `<tr><td style="color:var(--muted);white-space:nowrap">${l.date.slice(8)}/${l.date.slice(5, 7)}</td>
     <td>${l.lbl}</td><td class="num ${l.cls}">${l.sg} ${fmt(l.montant)}</td>
     <td style="width:30px"><button class="del" onclick="suppr('${l.type}',${l.id})">✕</button></td></tr>`
  ).join('') + '</tbody></table>';
}

/* ---------------- Dashboard ---------------- */
/* ---------------- Dashboard : navigation ---------------- */
let vueDash = 'mois';
let anneeCour = new Date().getFullYear();
let jourCour = null;       // initialisé au premier affichage
let semaineCour = null;    // n'importe quel jour de la semaine affichée
const JOURS_FR = ['Lundi', 'Mardi', 'Mercredi', 'Jeudi', 'Vendredi', 'Samedi', 'Dimanche'];

// Décale une date AAAA-MM-JJ de n jours (calcul local, sans UTC)
function decalerDate(dateStr, n) {
  const [a, m, j] = dateStr.split('-').map(Number);
  const d = new Date(a, m - 1, j + n);
  return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0');
}
function dateFr(dateStr, avecAnnee = true) {
  const [a, m, j] = dateStr.split('-').map(Number);
  return j + ' ' + MOIS_FR[m - 1].toLowerCase() + (avecAnnee ? ' ' + a : '');
}

function changerVue(v) {
  vueDash = v;
  for (const x of ['jour', 'semaine', 'mois', 'annee']) {
    $('v-' + x).classList.toggle('active', x === v);
    $('vue-' + x).style.display = x === v ? '' : 'none';
  }
  chargerDashboard();
}

function navDash(delta) {
  if (vueDash === 'annee') { anneeCour += delta; chargerDashAnnee(); }
  else if (vueDash === 'mois') changerMois(delta);
  else if (vueDash === 'semaine') { semaineCour = decalerDate(semaineCour, delta * 7); chargerDashSemaine(); }
  else { jourCour = decalerDate(jourCour, delta); chargerDashJour(); }
}

function chargerDashboard() {
  if (!jourCour) jourCour = auj();
  if (!semaineCour) semaineCour = auj();
  if (vueDash === 'annee') chargerDashAnnee();
  else if (vueDash === 'semaine') chargerDashSemaine();
  else if (vueDash === 'jour') chargerDashJour();
  else chargerDash();
}

function changerMois(delta) {
  let [a, m] = moisCour.split('-').map(Number);
  m += delta;
  if (m === 0) { m = 12; a--; }
  if (m === 13) { m = 1; a++; }
  moisCour = a + '-' + String(m).padStart(2, '0');
  chargerDash();
}

function badge(actuel, precedent, inverse = false) {
  if (!precedent) return '';
  const delta = (actuel - precedent) / precedent * 100;
  if (Math.abs(delta) < 0.5) return '<span class="badge neutre">＝</span>';
  const hausse = delta > 0;
  const bon = inverse ? hausse : !hausse;   // hausse de revenus = bon ; hausse de dépenses = mauvais
  return `<span class="badge ${bon ? 'good' : 'bad'}">${hausse ? '▲' : '▼'} ${Math.abs(delta).toFixed(0)}%</span>`;
}

/* ---------------- Vue mensuelle ---------------- */
async function chargerDash() {
  const r = await api('/api/resume?mois=' + moisCour);
  $('mois-titre').textContent = MOIS_FR[+moisCour.slice(5) - 1] + ' ' + moisCour.slice(0, 4);

  const epC = r.epargne >= r.objectif_epargne ? 'var(--green)' : (r.epargne >= 0 ? '#e8b93c' : 'var(--red)');
  const estMoisCourant = moisCour === auj().slice(0, 7);
  const jourRef = estMoisCourant ? new Date().getDate() : r.nb_jours;
  const resteC = r.reste_budget >= 0 ? 'var(--green)' : 'var(--red)';

  $('kpis').innerHTML = `
    <div class="kpi"><div class="l">Revenus</div>
      <div class="v" style="color:var(--blue)">${fmt(r.total_revenus)}${badge(r.total_revenus, r.revenus_mois_precedent, true)}</div></div>
    <div class="kpi"><div class="l">Dépenses</div>
      <div class="v" style="color:var(--accent)">${fmt(r.total_depenses)}${badge(r.total_depenses, r.depenses_mois_precedent)}</div>
      <div class="h">${fmt(r.total_depenses / Math.max(jourRef, 1))} / jour${
        r.projection_fin_mois ? ' · projection fin de mois : <b>' + fmt(r.projection_fin_mois) + '</b>' : ''}</div></div>
    <div class="kpi"><div class="l">Reste à dépenser</div>
      <div class="v" style="color:${resteC}">${fmt(r.reste_budget)}</div>
      <div class="h">sur un budget de ${fmt(r.budget_total)}</div></div>
    <div class="kpi"><div class="l">Épargne</div>
      <div class="v" style="color:${epC}">${fmt(r.epargne)}</div>
      <div class="h">Objectif : ${fmt(r.objectif_epargne)}</div></div>
    <div class="kpi"><div class="l">Taux d'épargne</div>
      <div class="v" style="color:${epC}">${r.taux_epargne}%</div></div>`;

  $('bars').innerHTML = r.budget_vs_reel.map(b => {
    const c = b.pct <= 80 ? 'var(--green)' : (b.pct <= 100 ? '#e8b93c' : 'var(--red)');
    return `<div class="bar-row"><div class="bar-head"><span>${b.cat}</span>
      <span>${fmt(b.reel)} / ${fmt(b.budget)} · ${b.pct}%</span></div>
      <div class="bar-bg"><div class="bar-fill" style="width:${Math.min(b.pct, 100)}%;background:${c}"></div></div></div>`;
  }).join('') || '<div class="vide">Aucune donnée</div>';

  dessiner('c-donut', {
    type: 'doughnut',
    data: {
      labels: r.donut.map(x => x.cat),
      datasets: [{ data: r.donut.map(x => x.montant), backgroundColor: PALETTE, borderWidth: 0 }]
    },
    options: { plugins: { legend: { position: 'right', labels: { boxWidth: 11, font: { size: 11 } } } } }
  });

  dessiner('c-cumul', {
    type: 'line',
    data: {
      labels: [...Array(r.nb_jours).keys()].map(i => i + 1),
      datasets: [
        { label: 'Cumul dépenses', data: r.cumul_quotidien, borderColor: '#f2a63c',
          backgroundColor: 'rgba(242,166,60,.15)', fill: true, tension: .3, pointRadius: 0 },
        { label: 'Budget total', data: Array(r.nb_jours).fill(r.budget_total),
          borderColor: '#64748b', borderDash: [6, 4], pointRadius: 0 }
      ]
    },
    options: {
      plugins: { legend: { labels: { boxWidth: 11 } } },
      scales: { y: { ticks: { callback: v => v.toLocaleString('fr-FR') } } }
    }
  });

  dessiner('c-evo', {
    type: 'bar',
    data: {
      labels: r.evolution.map(x => x.m),
      datasets: [
        { label: 'Revenus', data: r.evolution.map(x => x.rev), backgroundColor: '#55c3ee', borderRadius: 5 },
        { label: 'Dépenses', data: r.evolution.map(x => x.dep), backgroundColor: '#f2a63c', borderRadius: 5 }
      ]
    },
    options: {
      plugins: { legend: { labels: { boxWidth: 11 } } },
      scales: { y: { ticks: { callback: v => v.toLocaleString('fr-FR') } } }
    }
  });

  $('top').innerHTML = r.top.length
    ? '<table><thead><tr><th>Date</th><th>Catégorie</th><th>Description</th><th style="text-align:right">Montant</th></tr></thead><tbody>' +
      r.top.map(t => `<tr><td>${t.date.slice(8)}/${t.date.slice(5, 7)}</td><td>${t.categorie}</td>
        <td>${t.description || ''}</td><td class="num dep-amt">${fmt(t.montant)}</td></tr>`).join('') +
      '</tbody></table>'
    : '<div class="vide">Aucune dépense ce mois</div>';
}

/* ---------------- Vue journalière ---------------- */
async function chargerDashJour() {
  const r = await api('/api/resume_jour?date=' + jourCour);
  const [a, m, j] = jourCour.split('-').map(Number);
  const nomJour = JOURS_FR[(new Date(a, m - 1, j).getDay() + 6) % 7];
  $('mois-titre').textContent = nomJour + ' ' + dateFr(jourCour);

  const solde = r.total_revenus - r.total_depenses;
  const budgetC = r.total_depenses <= r.budget_jour ? 'var(--green)' : 'var(--red)';

  $('j-kpis').innerHTML = `
    <div class="kpi"><div class="l">Dépenses du jour</div>
      <div class="v" style="color:var(--accent)">${fmt(r.total_depenses)}${badge(r.total_depenses, r.depenses_veille)}</div>
      <div class="h">veille : ${fmt(r.depenses_veille)}</div></div>
    <div class="kpi"><div class="l">Revenus du jour</div>
      <div class="v" style="color:var(--blue)">${fmt(r.total_revenus)}</div></div>
    <div class="kpi"><div class="l">Budget journalier</div>
      <div class="v" style="color:${budgetC}">${fmt(r.budget_jour)}</div>
      <div class="h">${r.total_depenses <= r.budget_jour ? 'dans le budget ✓' : 'dépassé de ' + fmt(r.total_depenses - r.budget_jour)}</div></div>
    <div class="kpi"><div class="l">Moyenne / jour du mois</div>
      <div class="v">${fmt(r.moyenne_jour_mois)}</div></div>
    <div class="kpi"><div class="l">Transactions</div>
      <div class="v">${r.nb_transactions}</div></div>`;

  dessiner('c-j-donut', {
    type: 'doughnut',
    data: {
      labels: r.donut.map(x => x.cat),
      datasets: [{ data: r.donut.map(x => x.montant), backgroundColor: PALETTE, borderWidth: 0 }]
    },
    options: { plugins: { legend: { position: 'right', labels: { boxWidth: 11, font: { size: 11 } } } } }
  });

  const lignes = [
    ...r.depenses.map(x => ({ lbl: x.categorie + (x.description ? ' — ' + x.description : ''), m: x.montant, cls: 'dep-amt', sg: '−', extra: x.paiement })),
    ...r.revenus.map(x => ({ lbl: x.source || 'Revenu', m: x.montant, cls: 'rev-amt', sg: '+', extra: '' }))
  ];
  $('j-trans').innerHTML = lignes.length
    ? '<table><tbody>' + lignes.map(l =>
        `<tr><td>${l.lbl}</td><td style="color:var(--muted);font-size:11px">${l.extra}</td>
         <td class="num ${l.cls}">${l.sg} ${fmt(l.m)}</td></tr>`).join('') + '</tbody></table>'
    : '<div class="vide">Aucune transaction ce jour</div>';
}

/* ---------------- Vue hebdomadaire ---------------- */
async function chargerDashSemaine() {
  const r = await api('/api/resume_semaine?date=' + semaineCour);
  $('mois-titre').textContent = 'Semaine du ' + dateFr(r.lundi, false) + ' au ' + dateFr(r.dimanche);

  const epC = r.epargne >= 0 ? 'var(--green)' : 'var(--red)';
  const resteC = r.reste_budget_hebdo >= 0 ? 'var(--green)' : 'var(--red)';

  $('s-kpis').innerHTML = `
    <div class="kpi"><div class="l">Dépenses</div>
      <div class="v" style="color:var(--accent)">${fmt(r.total_depenses)}${badge(r.total_depenses, r.depenses_semaine_precedente)}</div>
      <div class="h">semaine préc. : ${fmt(r.depenses_semaine_precedente)}</div></div>
    <div class="kpi"><div class="l">Revenus</div>
      <div class="v" style="color:var(--blue)">${fmt(r.total_revenus)}${badge(r.total_revenus, r.revenus_semaine_precedente, true)}</div></div>
    <div class="kpi"><div class="l">Solde de la semaine</div>
      <div class="v" style="color:${epC}">${fmt(r.epargne)}</div></div>
    <div class="kpi"><div class="l">Reste budget hebdo</div>
      <div class="v" style="color:${resteC}">${fmt(r.reste_budget_hebdo)}</div>
      <div class="h">sur ${fmt(r.budget_hebdo)}</div></div>`;

  dessiner('c-s-jours', {
    type: 'bar',
    data: {
      labels: r.par_jour.map((x, i) => JOURS_FR[i].slice(0, 3) + ' ' + x.date.slice(8)),
      datasets: [
        { label: 'Dépenses', data: r.par_jour.map(x => x.dep), backgroundColor: '#f2a63c', borderRadius: 5 },
        { label: 'Revenus', data: r.par_jour.map(x => x.rev), backgroundColor: '#55c3ee', borderRadius: 5 }
      ]
    },
    options: {
      plugins: { legend: { labels: { boxWidth: 11 } } },
      scales: { y: { ticks: { callback: v => v.toLocaleString('fr-FR') } } }
    }
  });

  dessiner('c-s-donut', {
    type: 'doughnut',
    data: {
      labels: r.donut.map(x => x.cat),
      datasets: [{ data: r.donut.map(x => x.montant), backgroundColor: PALETTE, borderWidth: 0 }]
    },
    options: { plugins: { legend: { position: 'right', labels: { boxWidth: 11, font: { size: 11 } } } } }
  });

  $('s-top').innerHTML = r.top.length
    ? '<table><tbody>' + r.top.map(t =>
        `<tr><td style="color:var(--muted);white-space:nowrap">${t.date.slice(8)}/${t.date.slice(5, 7)}</td>
         <td>${t.categorie}${t.description ? ' — ' + t.description : ''}</td>
         <td class="num dep-amt">${fmt(t.montant)}</td></tr>`).join('') + '</tbody></table>'
    : '<div class="vide">Aucune dépense cette semaine</div>';
}

function dessiner(id, cfg) {
  if (!window.Chart) return;   // graphiques indisponibles : le reste de l'app fonctionne
  if (charts[id]) charts[id].destroy();
  charts[id] = new Chart($(id), cfg);
}

/* ---------------- Vue annuelle ---------------- */
async function chargerDashAnnee() {
  const r = await api('/api/resume_annuel?annee=' + anneeCour);
  $('mois-titre').textContent = 'Année ' + anneeCour;

  const epC = r.epargne >= 0 ? 'var(--green)' : 'var(--red)';
  const nomMois = m => MOIS_FR[m - 1];

  $('an-kpis').innerHTML = `
    <div class="kpi"><div class="l">Revenus ${anneeCour}</div>
      <div class="v" style="color:var(--blue)">${fmt(r.total_revenus)}</div></div>
    <div class="kpi"><div class="l">Dépenses ${anneeCour}</div>
      <div class="v" style="color:var(--accent)">${fmt(r.total_depenses)}</div>
      <div class="h">moyenne : ${fmt(r.moyenne_dep_mois)} / mois actif</div></div>
    <div class="kpi"><div class="l">Épargne ${anneeCour}</div>
      <div class="v" style="color:${epC}">${fmt(r.epargne)}</div>
      <div class="h">taux : ${r.taux_epargne}%</div></div>
    <div class="kpi"><div class="l">Objectif atteint</div>
      <div class="v">${r.nb_mois_objectif} / ${r.nb_mois_actifs}</div>
      <div class="h">mois à ≥ ${fmt(r.objectif_epargne)} d'épargne</div></div>
    ${r.meilleur_mois ? `<div class="kpi"><div class="l">Meilleur mois</div>
      <div class="v" style="color:var(--green)">${nomMois(r.meilleur_mois.m)}</div>
      <div class="h">épargne : ${fmt(r.meilleur_mois.ep)}</div></div>` : ''}
    ${r.pire_mois ? `<div class="kpi"><div class="l">Mois le plus difficile</div>
      <div class="v" style="color:var(--red)">${nomMois(r.pire_mois.m)}</div>
      <div class="h">épargne : ${fmt(r.pire_mois.ep)}</div></div>` : ''}`;

  const labels = MOIS_FR.map(m => m.slice(0, 4));

  dessiner('c-an-mois', {
    data: {
      labels,
      datasets: [
        { type: 'bar', label: 'Revenus', data: r.par_mois.map(x => x.rev), backgroundColor: '#55c3ee', borderRadius: 4 },
        { type: 'bar', label: 'Dépenses', data: r.par_mois.map(x => x.dep), backgroundColor: '#f2a63c', borderRadius: 4 },
        { type: 'line', label: 'Épargne', data: r.par_mois.map(x => x.ep), borderColor: '#34d399',
          backgroundColor: '#34d399', tension: .3, pointRadius: 3 }
      ]
    },
    options: {
      plugins: { legend: { labels: { boxWidth: 11 } } },
      scales: { y: { ticks: { callback: v => v.toLocaleString('fr-FR') } } }
    }
  });

  const topCats = r.categories.slice(0, 8);
  dessiner('c-an-cats', {
    type: 'bar',
    data: {
      labels: topCats.map(c => c.cat),
      datasets: [{ label: 'Total ' + anneeCour, data: topCats.map(c => c.total),
                   backgroundColor: PALETTE, borderRadius: 5 }]
    },
    options: {
      indexAxis: 'y',
      plugins: { legend: { display: false } },
      scales: { x: { ticks: { callback: v => v.toLocaleString('fr-FR') } } }
    }
  });

  dessiner('c-an-cumul', {
    type: 'line',
    data: {
      labels,
      datasets: [{ label: 'Épargne cumulée', data: r.epargne_cumulee, borderColor: '#34d399',
                   backgroundColor: 'rgba(52,211,153,.15)', fill: true, tension: .3, pointRadius: 0 }]
    },
    options: {
      plugins: { legend: { labels: { boxWidth: 11 } } },
      scales: { y: { ticks: { callback: v => v.toLocaleString('fr-FR') } } }
    }
  });

  // Grille thermique catégories × mois
  const cats2 = Object.keys(r.grille);
  if (!cats2.length) { $('an-grille').innerHTML = '<div class="vide">Aucune dépense cette année</div>'; return; }
  const maxVal = Math.max(...cats2.flatMap(c => r.grille[c]));
  $('an-grille').innerHTML = '<table><thead><tr><th>Catégorie</th>' +
    labels.map(l => `<th>${l}</th>`).join('') + '<th>Total</th></tr></thead><tbody>' +
    cats2.map(c => {
      const vals = r.grille[c];
      const tot = vals.reduce((a, b) => a + b, 0);
      return `<tr><td>${c}</td>` + vals.map(v => {
        const alpha = maxVal ? (v / maxVal * 0.85) : 0;
        return `<td style="background:rgba(242,166,60,${alpha.toFixed(2)})">${v ? Math.round(v).toLocaleString('fr-FR') : ''}</td>`;
      }).join('') + `<td class="num dep-amt">${fmt(tot)}</td></tr>`;
    }).join('') + '</tbody></table>';
}

/* ---------------- Paramètres ---------------- */
async function chargerParams() {
  await chargerCats();
  $('p-cats').innerHTML = cats.map(c => `
    <div class="cat-row">
      <input type="text" value="${c.nom}" id="pc-nom-${c.id}">
      <input type="number" value="${c.budget}" min="0" id="pc-bud-${c.id}">
      <button class="btn-sm" onclick="sauverCat(${c.id})">💾</button>
      <button class="btn-sm" onclick="supprCat(${c.id})" style="color:var(--red)">✕</button>
    </div>`).join('');

  $('p-sources').innerHTML = sources.map(s => `
    <div class="cat-row">
      <input type="text" value="${s.nom}" id="ps-nom-${s.id}">
      <button class="btn-sm" onclick="sauverSource(${s.id})">💾</button>
      <button class="btn-sm" onclick="supprSource(${s.id})" style="color:var(--red)">✕</button>
    </div>`).join('') || '<div class="vide">Aucune source configurée</div>';

  $('p-paies').innerHTML = paiements.map(p => `
    <div class="cat-row">
      <input type="text" value="${p.nom}" id="pp-nom-${p.id}">
      <button class="btn-sm" onclick="sauverPaiement(${p.id})">💾</button>
      <button class="btn-sm" onclick="supprPaiement(${p.id})" style="color:var(--red)">✕</button>
    </div>`).join('') || '<div class="vide">Aucun type configuré</div>';
}

/* ---- Sources de revenus ---- */
async function ajouterSource() {
  const nom = $('p-new-source').value.trim();
  if (!nom) return toast('Nom requis', false);
  await api('/api/sources', { method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ nom }) });
  $('p-new-source').value = '';
  toast('Source ajoutée ✓');
  chargerParams();
}
async function sauverSource(id) {
  await api('/api/sources/' + id, { method: 'PUT', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ nom: $('ps-nom-' + id).value }) });
  toast('Source mise à jour ✓');
  chargerParams();
}
async function supprSource(id) {
  if (!confirm('Retirer cette source de la liste ? (les revenus existants sont conservés)')) return;
  await api('/api/sources/' + id, { method: 'DELETE' });
  toast('Source retirée');
  chargerParams();
}

/* ---- Types de paiement ---- */
async function ajouterPaiement() {
  const nom = $('p-new-paie').value.trim();
  if (!nom) return toast('Nom requis', false);
  await api('/api/paiements', { method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ nom }) });
  $('p-new-paie').value = '';
  toast('Type ajouté ✓');
  chargerParams();
}
async function sauverPaiement(id) {
  await api('/api/paiements/' + id, { method: 'PUT', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ nom: $('pp-nom-' + id).value }) });
  toast('Type mis à jour ✓');
  chargerParams();
}
async function supprPaiement(id) {
  if (!confirm('Retirer ce type de paiement ? (les dépenses existantes sont conservées)')) return;
  await api('/api/paiements/' + id, { method: 'DELETE' });
  toast('Type retiré');
  chargerParams();
}

async function sauverCat(id) {
  await api('/api/categories/' + id, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ nom: $('pc-nom-' + id).value, budget: parseFloat($('pc-bud-' + id).value) || 0 })
  });
  toast('Catégorie mise à jour ✓');
  chargerParams();
}

async function supprCat(id) {
  if (!confirm('Désactiver cette catégorie ? (les dépenses existantes sont conservées)')) return;
  await api('/api/categories/' + id, { method: 'DELETE' });
  toast('Catégorie désactivée');
  chargerParams();
}

async function ajouterCategorie() {
  const nom = $('p-new-nom').value.trim();
  if (!nom) return toast('Nom requis', false);
  await api('/api/categories', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ nom, budget: parseFloat($('p-new-budget').value) || 0 })
  });
  $('p-new-nom').value = '';
  $('p-new-budget').value = '';
  toast('Catégorie ajoutée ✓');
  chargerParams();
}

async function sauverObjectif() {
  await api('/api/objectif', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ objectif: parseFloat($('p-objectif').value) || 0 })
  });
  toast('Objectif enregistré ✓');
}

/* ---------------- Thème jour / nuit ---------------- */
function appliquerTheme(t) {
  document.documentElement.setAttribute('data-theme', t);
  localStorage.setItem('theme', t);
  $('btn-theme').textContent = t === 'light' ? '🌙' : '☀️';
  // Adapter les couleurs des graphiques Chart.js au thème
  if (window.Chart) {
    Chart.defaults.color = t === 'light' ? '#64708c' : '#8d98b4';
    Chart.defaults.borderColor = t === 'light' ? '#dfe4ee' : '#263250';
  }
  // Redessiner le dashboard s'il est affiché
  if ($('tab-dash').style.display !== 'none') chargerDashboard();
}

function basculerTheme() {
  const actuel = document.documentElement.getAttribute('data-theme') === 'light' ? 'dark' : 'light';
  appliquerTheme(actuel);
}

/* ---------------- Init ---------------- */
(async function init() {
  appliquerTheme(localStorage.getItem('theme') || 'dark');
  $('d-date').value = auj();
  $('r-date').value = auj();
  $('jour').textContent = new Date().toLocaleDateString('fr-FR', { weekday: 'long', day: 'numeric', month: 'long' });
  try {
    await api('/api/me');    // session valide ?
    demarrerApp();
  } catch (e) {
    afficherLogin(true);     // sinon, écran de connexion
  }
})();