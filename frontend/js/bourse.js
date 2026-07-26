/* ==========================================================================
   Module Bourse v2 — réutilise $(), fmt(), lireMontant(id), toast(), api()
   déjà définis dans app.js (chargé avant ce fichier).
   ========================================================================== */

let vueBourse = 'transactions';

const LABELS_FRAIS = {
  courtage: 'Courtage', reglement_livraison: 'Règlement/livraison', impot_bourse: 'Impôt de bourse',
  tva: 'TVA', commission_fixe: 'Commission fixe', droits_entree: "Droits d'entrée",
  droits_sortie: 'Droits de sortie', commission_souscription: 'Commission de souscription',
};

function changerVueBourse(v) {
  vueBourse = v;
  for (const x of ['transactions', 'positions', 'gains', 'dashboard', 'parametres']) {
    $('vb-' + x).classList.toggle('active', x === v);
    $('vue-bourse-' + x).style.display = x === v ? '' : 'none';
  }
  chargerVueBourseActive();
}

function chargerVueBourseActive() {
  if (vueBourse === 'transactions') chargerTransactionsBourse();
  else if (vueBourse === 'positions') chargerPositionsBourse();
  else if (vueBourse === 'gains') chargerGainsBourse();
  else if (vueBourse === 'dashboard') chargerDashboardBourse();
  else if (vueBourse === 'parametres') chargerParametresBourse();
}

/* ---------------- Formulaire : bascule des champs selon l'instrument ---------------- */
function basculerChampsInstrument() {
  const instrument = $('b-instrument').value;
  $('b-champ-opcvm').style.display = instrument === 'OPCVM' ? '' : 'none';
  $('b-champ-ipo').style.display = instrument === 'IPO' ? '' : 'none';
  $('b-prix-label').textContent = instrument === 'OPCVM' ? 'Valeur liquidative (DH)' : 'Cours unitaire (DH)';
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
  if (isNaN(prix) || prix <= 0) return toast('Cours invalide', false);

  const corps = {
    date_operation: $('b-date').value,
    titre, type_instrument: instrument, type_operation: $('b-type').value,
    quantite: qte, cours_unitaire: prix, autres_frais: isNaN(frais) ? 0 : frais,
  };
  if (instrument === 'IPO') {
    corps.structure_ipo = $('b-structure-ipo').value;
  }
  if (instrument === 'OPCVM' && $('b-taux-opcvm').value) {
    const t = lireMontant('b-taux-opcvm');
    if (!isNaN(t)) corps.taux_droits_opcvm = t / 100;
  }

  await api('/api/bourse/transactions', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(corps),
  });
  $('b-titre').value = ''; $('b-qte').value = ''; $('b-prix').value = '';
  $('b-frais').value = ''; $('b-taux-opcvm').value = '';
  toast('Transaction ajoutée ✓');
  chargerTransactionsBourse();
}

async function supprTransactionBourse(id) {
  if (!confirm('Supprimer cette transaction ?')) return;
  await api(`/api/bourse/transactions/${id}`, { method: 'DELETE' });
  toast('Supprimé');
  chargerTransactionsBourse();
}

function totalFraisDetail(t) {
  return Object.values(t.detail_frais || {}).reduce((a, b) => a + b, 0);
}

function resumeFrais(t) {
  return Object.entries(t.detail_frais || {})
    .map(([k, v]) => `${LABELS_FRAIS[k] || k} : ${fmt(v)}`).join(' · ');
}

async function chargerTransactionsBourse() {
  const liste = await api('/api/bourse/transactions');
  if (!liste.length) {
    $('b-liste-trans').innerHTML = '<div class="vide">Aucune transaction — ajoute ton premier achat ci-dessus 👆</div>';
    return;
  }
  $('b-liste-trans').innerHTML = '<div style="overflow-x:auto;-webkit-overflow-scrolling:touch"><table><thead><tr>' +
    '<th>Date</th><th>Titre</th><th>Instrument</th><th>Type</th><th class="num">Qté</th>' +
    '<th class="num">Cours</th><th class="num">Frais</th><th class="num">Net</th><th></th>' +
    '</tr></thead><tbody>' + liste.map(t => `
    <tr>
      <td style="color:var(--muted);white-space:nowrap">${t.date_operation.slice(8)}/${t.date_operation.slice(5,7)}</td>
      <td>${t.titre}</td>
      <td style="color:var(--muted);font-size:11px">${t.type_instrument}${t.type_instrument === 'IPO' ? (t.structure_ipo === 'action' ? ' (Action)' : ' (Souscription)') : ''}</td>
      <td style="color:${t.type_operation === 'Achat' ? 'var(--blue)' : 'var(--accent)'}">${t.type_operation}</td>
      <td class="num">${t.quantite}</td>
      <td class="num">${fmt(t.cours_unitaire)}</td>
      <td class="num" title="${resumeFrais(t)}">${fmt(totalFraisDetail(t) + t.autres_frais)}</td>
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

async function chargerPositionsBourse() {
  const liste = (await api('/api/bourse/positions')).filter(p => p.quantite_detenue > 0);
  if (!liste.length) {
    $('b-liste-positions').innerHTML = '<div class="vide">Aucune position ouverte pour le moment.</div>';
    return;
  }
  $('b-liste-positions').innerHTML = '<div style="overflow-x:auto;-webkit-overflow-scrolling:touch"><table><thead><tr>' +
    '<th>Titre</th><th class="num">Qté détenue</th><th class="num">PRU</th><th class="num">Cours actuel</th>' +
    '<th class="num">Valeur marché</th><th class="num">+/- value latente</th><th class="num">Perf.</th>' +
    '</tr></thead><tbody>' + liste.map(p => `
    <tr>
      <td>${p.titre}</td>
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

/* ---------------- Dashboard ---------------- */
async function chargerDashboardBourse() {
  const d = await api('/api/bourse/dashboard');
  const cLatente = d.plus_value_latente >= 0 ? 'var(--green)' : 'var(--red)';
  const cRealise = d.gains_nets_realises >= 0 ? 'var(--green)' : 'var(--red)';
  const cGlobal = d.resultat_net_global >= 0 ? 'var(--green)' : 'var(--red)';
  $('b-kpis').innerHTML = `
    <div class="kpi"><div class="l">Valeur de marché</div><div class="v" style="color:var(--blue)">${fmt(d.valeur_marche)}</div>
      <div class="h">coût d'acquisition : ${fmt(d.cout_acquisition)}</div></div>
    <div class="kpi"><div class="l">Plus/moins-value latente</div><div class="v" style="color:${cLatente}">${fmt(d.plus_value_latente)}</div>
      <div class="h">${(d.performance_latente*100).toFixed(2)} %</div></div>
    <div class="kpi"><div class="l">Gains nets réalisés</div><div class="v" style="color:${cRealise}">${fmt(d.gains_nets_realises)}</div>
      <div class="h">TPCVM : ${fmt(d.tpcvm_total)}</div></div>
    <div class="kpi"><div class="l">Frais de transaction totaux</div><div class="v" style="color:var(--accent)">${fmt(d.frais_totaux)}</div>
      <div class="h">dont commissions : ${fmt(d.commissions_totales)} · TVA : ${fmt(d.tva_totale)}</div></div>
    <div class="kpi"><div class="l">Droits de garde (trimestre en cours)</div><div class="v" style="color:var(--accent)">${fmt(d.droits_garde_trimestriel_estime)}</div>
      <div class="h">estimation sur encours actuel</div></div>
    <div class="kpi"><div class="l">Résultat net global</div><div class="v" style="color:${cGlobal}">${fmt(d.resultat_net_global)}</div></div>`;
}

/* ---------------- Paramètres ---------------- */
function pct(v) { return (v * 100).toFixed(3).replace(/\.?0+$/, '').replace('.', ',') || '0'; }

async function chargerParametresBourse() {
  const p = await api('/api/bourse/parametres');
  $('bp-courtage').value = pct(p.taux_courtage_action);
  $('bp-reglement').value = pct(p.taux_reglement_livraison);
  $('bp-impot-action').value = pct(p.taux_impot_bourse_action);
  $('bp-tva').value = pct(p.taux_tva);
  $('bp-commission-obligation').value = String(p.commission_fixe_obligation).replace('.', ',');
  $('bp-impot-obligation').value = pct(p.taux_impot_bourse_obligation);
  $('bp-opcvm-entree').value = pct(p.droits_entree_opcvm_defaut);
  $('bp-opcvm-sortie').value = pct(p.droits_sortie_opcvm_defaut);
  $('bp-ipo-taux').value = pct(p.taux_souscription_ipo);
  $('bp-ipo-min').value = String(p.min_souscription_ipo).replace('.', ',');
  $('bp-garde-taux').value = pct(p.taux_droit_garde_annuel);
  $('bp-garde-min').value = String(p.droit_garde_min_trimestriel).replace('.', ',');
  $('bp-tpcvm').value = pct(p.taux_tpcvm);
}

async function sauverParametresBourse() {
  const champs = {
    taux_courtage_action: 'bp-courtage', taux_reglement_livraison: 'bp-reglement',
    taux_impot_bourse_action: 'bp-impot-action', taux_tva: 'bp-tva',
    droits_entree_opcvm_defaut: 'bp-opcvm-entree', droits_sortie_opcvm_defaut: 'bp-opcvm-sortie',
    taux_souscription_ipo: 'bp-ipo-taux', taux_droit_garde_annuel: 'bp-garde-taux',
    taux_impot_bourse_obligation: 'bp-impot-obligation', taux_tpcvm: 'bp-tpcvm',
  };
  const corps = {};
  for (const [cle, id] of Object.entries(champs)) {
    const v = lireMontant(id);
    if (isNaN(v) || v < 0) return toast('Taux invalide : ' + id, false);
    corps[cle] = v / 100;
  }
  corps.commission_fixe_obligation = lireMontant('bp-commission-obligation');
  corps.min_souscription_ipo = lireMontant('bp-ipo-min');
  corps.droit_garde_min_trimestriel = lireMontant('bp-garde-min');
  if ([corps.commission_fixe_obligation, corps.min_souscription_ipo, corps.droit_garde_min_trimestriel].some(v => isNaN(v) || v < 0)) {
    return toast('Montant invalide', false);
  }

  await api('/api/bourse/parametres', {
    method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(corps),
  });
  toast('Paramètres enregistrés ✓');
}

/* ---------------- Référentiel des titres (Bourse de Casablanca) ---------------- */
async function chargerTitresBourse() {
  const liste = await api('/api/bourse/titres');
  $('b-titres-liste').innerHTML = liste.map(t => `<option value="${t.code}">${t.code} — ${t.nom}</option>`).join('');
}

/* ---------------- Point d'entrée de l'onglet ---------------- */
function chargerBourse() {
  basculerChampsInstrument();
  chargerTitresBourse();
  changerVueBourse(vueBourse);
}