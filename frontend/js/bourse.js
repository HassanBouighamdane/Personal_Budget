/* ==========================================================================
   Module Bourse — réutilise $(), fmt(), lireMontant(id), toast(), api(), auj(),
   MOIS_FR déjà définis dans app.js (chargé avant ce fichier).

   Simplifié : aucun frais n'est calculé automatiquement sur les transactions
   ni sur les dividendes — l'utilisateur saisit directement le prix net et le
   montant net reçu. Les frais de courtage se saisissent manuellement (par
   transaction, ou via le journal séparé des frais de compte).
   ========================================================================== */

let vueBourse = 'transactions';

function changerVueBourse(v) {
  vueBourse = v;
  for (const x of ['transactions', 'positions', 'gains', 'dividendes', 'frais', 'dashboard', 'parametres']) {
    $('vb-' + x).classList.toggle('active', x === v);
    $('vue-bourse-' + x).style.display = x === v ? '' : 'none';
  }
  chargerVueBourseActive();
}

function chargerVueBourseActive() {
  if (vueBourse === 'transactions') chargerTransactionsBourse();
  else if (vueBourse === 'positions') chargerPositionsBourse();
  else if (vueBourse === 'gains') chargerGainsBourse();
  else if (vueBourse === 'dividendes') chargerDividendesBourse();
  else if (vueBourse === 'frais') chargerFraisBourse();
  else if (vueBourse === 'dashboard') chargerDashboardBourse();
  else if (vueBourse === 'parametres') chargerParametresBourse();
}

/* ---------------- Formulaire : libellé du prix selon l'instrument (cosmétique uniquement) ---------------- */
function basculerChampsInstrument() {
  const instrument = $('b-instrument').value;
  $('b-prix-label').textContent = instrument === 'OPCVM' ? 'Valeur liquidative nette (DH)' : 'Prix unitaire net (DH)';
}

/* ---------------- Transactions ---------------- */
async function ajouterTransactionBourse() {
  const titre = $('b-titre').value.trim().toUpperCase();
  const instrument = $('b-instrument').value;
  const qte = parseFloat($('b-qte').value);
  const prix = lireMontant('b-prix');
  const frais = $('b-frais').value ? lireMontant('b-frais') : 0;

  if (!titre) return toast('Indique le titre', false);
  if (!qte || qte <= 0) return toast('Quantité invalide', false);
  if (isNaN(prix) || prix <= 0) return toast('Prix invalide', false);

  const corps = {
    date_operation: $('b-date').value,
    titre, type_instrument: instrument, type_operation: $('b-type').value,
    quantite: qte, cours_unitaire: prix, autres_frais: isNaN(frais) ? 0 : frais,
  };

  await api('/api/bourse/transactions', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(corps),
  });
  $('b-titre').value = ''; $('b-qte').value = ''; $('b-prix').value = ''; $('b-frais').value = '';
  toast('Transaction ajoutée ✓');
  chargerTransactionsBourse();
}

async function supprTransactionBourse(id) {
  if (!confirm('Supprimer cette transaction ?')) return;
  await api(`/api/bourse/transactions/${id}`, { method: 'DELETE' });
  toast('Supprimé');
  chargerTransactionsBourse();
}

async function chargerTransactionsBourse() {
  const liste = await api('/api/bourse/transactions');
  if (!liste.length) {
    $('b-liste-trans').innerHTML = '<div class="vide">Aucune transaction — ajoute ton premier achat ci-dessus 👆</div>';
    return;
  }
  $('b-liste-trans').innerHTML = '<div style="overflow-x:auto;-webkit-overflow-scrolling:touch"><table><thead><tr>' +
    '<th>Date</th><th>Titre</th><th>Instrument</th><th>Type</th><th class="num">Qté</th>' +
    '<th class="num">Prix</th><th class="num">Frais</th><th class="num">Net</th><th></th>' +
    '</tr></thead><tbody>' + liste.map(t => `
    <tr>
      <td style="color:var(--muted);white-space:nowrap">${t.date_operation.slice(8)}/${t.date_operation.slice(5,7)}</td>
      <td>${t.titre}</td>
      <td style="color:var(--muted);font-size:11px">${t.type_instrument}</td>
      <td style="color:${t.type_operation === 'Achat' ? 'var(--blue)' : 'var(--accent)'}">${t.type_operation}</td>
      <td class="num">${t.quantite}</td>
      <td class="num">${fmt(t.cours_unitaire)}</td>
      <td class="num">${fmt(t.autres_frais)}</td>
      <td class="num" style="color:${t.type_operation === 'Achat' ? 'var(--accent)' : 'var(--blue)'}">${t.type_operation === 'Achat' ? '−' : '+'} ${fmt(t.montant_net)}</td>
      <td style="width:30px"><button class="del" onclick="supprTransactionBourse(${t.id})">✕</button></td>
    </tr>`).join('') + '</tbody></table></div>';
}

/* ---------------- Positions ---------------- */
async function majCoursBourse(titre, valeur) {
  const cours = parseFloat(valeur.replace(',', '.'));
  if (isNaN(cours) || cours < 0) return toast('Cours invalide', false);
  await api(`/api/bourse/prix/${encodeURIComponent(titre)}`, {
    method: 'PUT', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ cours_actuel: cours }),
  });
  chargerPositionsBourse();
  if (vueBourse === 'dashboard') chargerDashboardBourse();
}

// optionsDonutPourcentage(), regrouperAutres() et paletteActuelle() sont définis dans app.js.
function dessinerRepartitionBourse(liste) {
  const parTitre = regrouperAutres(liste.map(p => p.titre), liste.map(p => p.valeur_marche));
  dessiner('c-b-titre', {
    type: 'doughnut',
    data: { labels: parTitre.labels, datasets: [{ data: parTitre.valeurs, backgroundColor: parTitre.couleurs, borderWidth: 0 }] },
    options: optionsDonutPourcentage()
  });

  const parSecteurMap = {};
  liste.forEach(p => {
    const s = p.secteur || 'Non classé';
    parSecteurMap[s] = (parSecteurMap[s] || 0) + p.valeur_marche;
  });
  const parSecteur = regrouperAutres(Object.keys(parSecteurMap), Object.values(parSecteurMap));
  dessiner('c-b-secteur', {
    type: 'doughnut',
    data: { labels: parSecteur.labels, datasets: [{ data: parSecteur.valeurs, backgroundColor: parSecteur.couleurs, borderWidth: 0 }] },
    options: optionsDonutPourcentage()
  });
}

async function chargerPositionsBourse() {
  const liste = (await api('/api/bourse/positions')).filter(p => p.quantite_detenue > 0);
  dessinerRepartitionBourse(liste);
  if (!liste.length) {
    $('b-liste-positions').innerHTML = '<div class="vide">Aucune position ouverte pour le moment.</div>';
    return;
  }
  $('b-liste-positions').innerHTML = '<div style="overflow-x:auto;-webkit-overflow-scrolling:touch"><table><thead><tr>' +
    '<th>Titre</th><th>Secteur</th><th class="num">Qté détenue</th><th class="num">PRU</th><th class="num">Cours actuel</th>' +
    '<th class="num">Valeur marché</th><th class="num">+/- value latente</th><th class="num">Perf.</th>' +
    '</tr></thead><tbody>' + liste.map(p => `
    <tr>
      <td>${p.titre}</td>
      <td style="color:var(--muted);font-size:11px">${p.secteur}</td>
      <td class="num">${p.quantite_detenue}</td>
      <td class="num">${fmt(p.pru)}</td>
      <td class="num"><input type="text" inputmode="decimal" value="${p.cours_actuel || ''}"
             style="width:80px;text-align:right" onchange="majCoursBourse('${p.titre}', this.value)"></td>
      <td class="num">${fmt(p.valeur_marche)}</td>
      <td class="num" style="color:${p.plus_value_latente >= 0 ? 'var(--green)' : 'var(--red)'}">${fmt(p.plus_value_latente)}</td>
      <td class="num" style="color:${p.performance_latente >= 0 ? 'var(--green)' : 'var(--red)'}">${(p.performance_latente*100).toFixed(2)} %</td>
    </tr>`).join('') + '</tbody></table></div>';
}

/* ---------------- Gains réalisés ---------------- */
async function chargerGainsBourse() {
  const liste = await api('/api/bourse/gains');
  if (!liste.length) {
    $('b-liste-gains').innerHTML = '<div class="vide">Aucune vente enregistrée pour le moment.</div>';
    return;
  }
  $('b-liste-gains').innerHTML = '<div style="overflow-x:auto;-webkit-overflow-scrolling:touch"><table><thead><tr>' +
    '<th>Date</th><th>Titre</th><th>Instrument</th><th class="num">Qté</th>' +
    '<th class="num">Gain brut</th><th class="num">TPCVM</th><th class="num">Gain net</th>' +
    '</tr></thead><tbody>' + liste.map(g => `
    <tr>
      <td style="color:var(--muted);white-space:nowrap">${g.date_operation.slice(8)}/${g.date_operation.slice(5,7)}</td>
      <td>${g.titre}</td>
      <td style="color:var(--muted);font-size:11px">${g.type_instrument}</td>
      <td class="num">${g.quantite}</td>
      <td class="num">${fmt(g.gain_brut)}</td>
      <td class="num">${fmt(g.tpcvm)}</td>
      <td class="num" style="color:${g.gain_net >= 0 ? 'var(--green)' : 'var(--red)'}">${fmt(g.gain_net)}</td>
    </tr>`).join('') + '</tbody></table></div>';
}

/* ---------------- Dividendes ---------------- */
async function ajouterDividendeBourse() {
  const titre = $('bd-titre').value.trim().toUpperCase();
  const montant = lireMontant('bd-montant');

  if (!titre) return toast('Indique le titre', false);
  if (isNaN(montant) || montant <= 0) return toast('Montant invalide', false);

  await api('/api/bourse/dividendes', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ date_operation: $('bd-date').value, titre, montant }),
  });
  $('bd-titre').value = ''; $('bd-montant').value = '';
  toast('Dividende ajouté ✓');
  chargerDividendesBourse();
}

async function supprDividendeBourse(id) {
  if (!confirm('Supprimer ce dividende ?')) return;
  await api(`/api/bourse/dividendes/${id}`, { method: 'DELETE' });
  toast('Supprimé');
  chargerDividendesBourse();
}

async function chargerDividendesBourse() {
  const liste = await api('/api/bourse/dividendes');
  if (!liste.length) {
    $('b-liste-dividendes').innerHTML = '<div class="vide">Aucun dividende — ajoute le premier ci-dessus 👆</div>';
    return;
  }
  $('b-liste-dividendes').innerHTML = '<div style="overflow-x:auto;-webkit-overflow-scrolling:touch"><table><thead><tr>' +
    '<th>Date</th><th>Titre</th><th class="num">Montant net</th><th></th>' +
    '</tr></thead><tbody>' + liste.map(d => `
    <tr>
      <td style="color:var(--muted);white-space:nowrap">${d.date_operation.slice(8)}/${d.date_operation.slice(5,7)}</td>
      <td>${d.titre}</td>
      <td class="num rev-amt">${fmt(d.montant)}</td>
      <td style="width:30px"><button class="del" onclick="supprDividendeBourse(${d.id})">✕</button></td>
    </tr>`).join('') + '</tbody></table></div>';
}

/* ---------------- Frais de compte ---------------- */
async function ajouterFraisBourse() {
  const libelle = $('bf-libelle').value.trim();
  const montant = lireMontant('bf-montant');
  if (isNaN(montant) || montant <= 0) return toast('Montant invalide', false);

  await api('/api/bourse/frais', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ date_operation: $('bf-date').value, libelle, montant }),
  });
  $('bf-libelle').value = ''; $('bf-montant').value = '';
  toast('Frais ajouté ✓');
  chargerFraisBourse();
}

async function supprFraisBourse(id) {
  if (!confirm('Supprimer ce frais ?')) return;
  await api(`/api/bourse/frais/${id}`, { method: 'DELETE' });
  toast('Supprimé');
  chargerFraisBourse();
}

async function chargerFraisBourse() {
  const liste = await api('/api/bourse/frais');
  if (!liste.length) {
    $('b-liste-frais').innerHTML = '<div class="vide">Aucun frais enregistré — ajoute le premier ci-dessus 👆</div>';
    return;
  }
  $('b-liste-frais').innerHTML = '<div style="overflow-x:auto;-webkit-overflow-scrolling:touch"><table><thead><tr>' +
    '<th>Date</th><th>Libellé</th><th class="num">Montant</th><th></th>' +
    '</tr></thead><tbody>' + liste.map(f => `
    <tr>
      <td style="color:var(--muted);white-space:nowrap">${f.date_operation.slice(8)}/${f.date_operation.slice(5,7)}</td>
      <td>${f.libelle || ''}</td>
      <td class="num dep-amt">${fmt(f.montant)}</td>
      <td style="width:30px"><button class="del" onclick="supprFraisBourse(${f.id})">✕</button></td>
    </tr>`).join('') + '</tbody></table></div>';
}

/* ---------------- Dashboard : navigation Global / Mois / Année ---------------- */
let vueDashBourse = 'global';   // par défaut : tout l'historique, comme au tout début
let moisCourBourse = auj().slice(0, 7);
let anneeCourBourse = new Date().getFullYear();

function changerVueDashBourse(v) {
  vueDashBourse = v;
  for (const x of ['global', 'mois', 'annee']) $('bv-' + x).classList.toggle('active', x === v);
  $('b-periode-prev').style.visibility = v === 'global' ? 'hidden' : '';
  $('b-periode-next').style.visibility = v === 'global' ? 'hidden' : '';
  chargerDashboardBourse();
}

function navDashBourse(delta) {
  if (vueDashBourse === 'global') return;
  if (vueDashBourse === 'annee') {
    anneeCourBourse += delta;
  } else {
    let [a, m] = moisCourBourse.split('-').map(Number);
    m += delta;
    if (m === 0) { m = 12; a--; }
    if (m === 13) { m = 1; a++; }
    moisCourBourse = a + '-' + String(m).padStart(2, '0');
  }
  chargerDashboardBourse();
}

function libellePeriodeBourse() {
  if (vueDashBourse === 'global') return 'Tout l’historique';
  return vueDashBourse === 'annee'
    ? 'Année ' + anneeCourBourse
    : MOIS_FR[+moisCourBourse.slice(5) - 1] + ' ' + moisCourBourse.slice(0, 4);
}

/* ---------------- Dashboard ---------------- */
async function chargerDashboardBourse() {
  const q = vueDashBourse === 'global' ? '' : vueDashBourse === 'annee' ? 'annee=' + anneeCourBourse : 'mois=' + moisCourBourse;
  const d = await api('/api/bourse/dashboard' + (q ? '?' + q : ''));

  $('b-periode-titre').textContent = libellePeriodeBourse();
  $('b-kpis-periode-titre').textContent = '💰 Résultat — ' + libellePeriodeBourse();

  const cLatente = d.plus_value_latente >= 0 ? 'var(--green)' : 'var(--red)';
  const cRealise = d.gains_nets_realises >= 0 ? 'var(--green)' : 'var(--red)';
  const cPeriode = d.resultat_net_periode >= 0 ? 'var(--green)' : 'var(--red)';

  $('b-kpis-actuel').innerHTML = `
    <div class="kpi"><div class="l">Valeur de marché</div><div class="v" style="color:var(--blue)">${fmt(d.valeur_marche)}</div>
      <div class="h">coût d'acquisition : ${fmt(d.cout_acquisition)}</div></div>
    <div class="kpi"><div class="l">Plus/moins-value latente</div><div class="v" style="color:${cLatente}">${fmt(d.plus_value_latente)}</div>
      <div class="h">${(d.performance_latente*100).toFixed(2)} %</div></div>`;

  $('b-kpis-periode').innerHTML = `
    <div class="kpi"><div class="l">Gains nets réalisés</div><div class="v" style="color:${cRealise}">${fmt(d.gains_nets_realises)}</div>
      <div class="h">TPCVM : ${fmt(d.tpcvm_total)}</div></div>
    <div class="kpi"><div class="l">Dividendes nets</div><div class="v" style="color:var(--green)">${fmt(d.dividendes_nets)}</div></div>
    <div class="kpi"><div class="l">Frais de transactions</div><div class="v" style="color:var(--accent)">${fmt(d.frais_transactions_totaux)}</div>
      <div class="h">déjà déduits du gain net ci-dessus — pour info</div></div>
    <div class="kpi"><div class="l">Frais de compte</div><div class="v" style="color:var(--accent)">${fmt(d.frais_compte_totaux)}</div></div>
    <div class="kpi"><div class="l">Résultat net de la période</div><div class="v" style="color:${cPeriode}">${fmt(d.resultat_net_periode)}</div>
      <div class="h">gains nets + dividendes − frais de compte</div></div>`;
}

/* ---------------- Paramètres ---------------- */
function pct(v) { return (v * 100).toFixed(3).replace(/\.?0+$/, '').replace('.', ',') || '0'; }

async function chargerParametresBourse() {
  const p = await api('/api/bourse/parametres');
  $('bp-tpcvm').value = pct(p.taux_tpcvm);
  chargerTitresManagement();
}

async function sauverParametresBourse() {
  const tauxTpcvm = lireMontant('bp-tpcvm');
  if (isNaN(tauxTpcvm) || tauxTpcvm < 0) return toast('Taux invalide', false);

  await api('/api/bourse/parametres', {
    method: 'PUT', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ taux_tpcvm: tauxTpcvm / 100 }),
  });
  toast('Paramètres enregistrés ✓');
}

/* ---------------- Référentiel des titres (Bourse de Casablanca) ---------------- */
async function chargerTitresBourse() {
  const liste = await api('/api/bourse/titres');
  $('b-titres-liste').innerHTML = liste.map(t => `<option value="${t.code}">${t.code} — ${t.nom}</option>`).join('');
}

/* ---- Gestion des titres (Paramètres > Bourse) ---- */
async function chargerTitresManagement() {
  const liste = await api('/api/bourse/titres');
  $('p-titres').innerHTML = liste.map(t => `
    <div class="cat-row">
      <input type="text" value="${t.code}" id="pt-code-${t.id}" style="flex:1">
      <input type="text" value="${t.nom}" id="pt-nom-${t.id}" style="flex:2">
      <input type="text" value="${t.secteur}" id="pt-secteur-${t.id}" style="flex:1">
      <button class="btn-sm" onclick="sauverTitreBourse(${t.id})">💾</button>
      <button class="btn-sm" onclick="supprTitreBourse(${t.id})" style="color:var(--red)">✕</button>
    </div>`).join('') || '<div class="vide">Aucun titre configuré</div>';
}

async function ajouterTitreBourse() {
  const code = $('p-new-titre-code').value.trim();
  const nom = $('p-new-titre-nom').value.trim();
  const secteur = $('p-new-titre-secteur').value.trim();
  if (!code || !nom) return toast('Code et nom requis', false);

  await api('/api/bourse/titres', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ code, nom, secteur }),
  });
  $('p-new-titre-code').value = ''; $('p-new-titre-nom').value = ''; $('p-new-titre-secteur').value = '';
  toast('Titre ajouté ✓');
  chargerTitresManagement();
  chargerTitresBourse();
}

async function sauverTitreBourse(id) {
  const code = $('pt-code-' + id).value.trim();
  const nom = $('pt-nom-' + id).value.trim();
  const secteur = $('pt-secteur-' + id).value.trim();
  if (!code || !nom) return toast('Code et nom requis', false);

  await api('/api/bourse/titres/' + id, {
    method: 'PUT', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ code, nom, secteur }),
  });
  toast('Titre mis à jour ✓');
  chargerTitresManagement();
  chargerTitresBourse();
}

async function supprTitreBourse(id) {
  if (!confirm('Retirer ce titre de la liste ? (les transactions déjà saisies sont conservées)')) return;
  await api('/api/bourse/titres/' + id, { method: 'DELETE' });
  toast('Titre retiré');
  chargerTitresManagement();
  chargerTitresBourse();
}

/* ---------------- Résumé silencieux pour le Dashboard principal ---------------- */
// Ne montre pas de toast d'erreur : un souci ici ne doit jamais casser le dashboard budget.
async function resumeBourseSilencieux(requete) {
  try {
    const r = await fetch(API_URL + '/api/bourse/dashboard?' + requete);
    if (!r.ok) return null;
    return await r.json();
  } catch (e) { return null; }
}

function kpisBourseHTML(bourse, libellePeriode) {
  if (!bourse) return '';
  const cLatente = bourse.plus_value_latente >= 0 ? 'var(--green)' : 'var(--red)';
  const cPeriode = bourse.resultat_net_periode >= 0 ? 'var(--green)' : 'var(--red)';
  return `
    <div class="kpi"><div class="l">Portefeuille Bourse</div>
      <div class="v" style="color:var(--blue)">${fmt(bourse.valeur_marche)}</div>
      <div class="h" style="color:${cLatente}">${bourse.plus_value_latente >= 0 ? '+' : ''}${fmt(bourse.plus_value_latente)} (${(bourse.performance_latente*100).toFixed(2)} %)</div></div>
    <div class="kpi"><div class="l">Résultat Bourse${libellePeriode ? ' ' + libellePeriode : ''}</div>
      <div class="v" style="color:${cPeriode}">${fmt(bourse.resultat_net_periode)}</div>
      <div class="h">gains nets + dividendes − frais de compte</div></div>`;
}

/* ---------------- Point d'entrée de l'onglet ---------------- */
function chargerBourse() {
  basculerChampsInstrument();
  chargerTitresBourse();
  changerVueBourse(vueBourse);
}
