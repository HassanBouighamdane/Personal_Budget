/* ==========================================================================
   Module Bourse — réutilise $(), fmt(), lireMontant(id), toast(), api()
   déjà définis dans app.js (chargé avant ce fichier).
   ========================================================================== */

let vueBourse = 'transactions';

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

/* ---------------- Transactions ---------------- */
async function ajouterTransactionBourse() {
  const titre = $('b-titre').value.trim().toUpperCase();
  const qte = parseFloat($('b-qte').value);
  const prix = lireMontant('b-prix');
  const frais = $('b-frais').value ? lireMontant('b-frais') : 0;

  if (!titre) return toast('Indique le titre', false);
  if (!qte || qte <= 0) return toast('Quantité invalide', false);
  if (isNaN(prix) || prix <= 0) return toast('Cours invalide', false);

  await api('/api/bourse/transactions', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      date_operation: $('b-date').value,
      titre, type_operation: $('b-type').value,
      quantite: qte, cours_unitaire: prix, autres_frais: isNaN(frais) ? 0 : frais,
    }),
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
  $('b-liste-trans').innerHTML = '<table><tbody>' + liste.map(t => `
    <tr>
      <td style="color:var(--muted);white-space:nowrap">${t.date_operation.slice(8)}/${t.date_operation.slice(5,7)}</td>
      <td>${t.titre}</td>
      <td style="color:${t.type_operation === 'Achat' ? 'var(--blue)' : 'var(--accent)'}">${t.type_operation}</td>
      <td class="num">${t.quantite}</td>
      <td class="num">${fmt(t.cours_unitaire)}</td>
      <td class="num">${fmt(t.commission + t.tva_commission)}</td>
      <td class="num" style="color:${t.type_operation === 'Achat' ? 'var(--accent)' : 'var(--blue)'}">${t.type_operation === 'Achat' ? '−' : '+'} ${fmt(t.montant_net)}</td>
      <td style="width:30px"><button class="del" onclick="supprTransactionBourse(${t.id})">✕</button></td>
    </tr>`).join('') + '</tbody></table>';
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
}

async function chargerPositionsBourse() {
  const liste = (await api('/api/bourse/positions')).filter(p => p.quantite_detenue > 0);
  if (!liste.length) {
    $('b-liste-positions').innerHTML = '<div class="vide">Aucune position ouverte pour le moment.</div>';
    return;
  }
  $('b-liste-positions').innerHTML = '<table><tbody>' + liste.map(p => `
    <tr>
      <td>${p.titre}</td>
      <td class="num">${p.quantite_detenue}</td>
      <td class="num">${fmt(p.pru)}</td>
      <td class="num"><input type="text" inputmode="decimal" value="${p.cours_actuel || ''}"
             style="width:80px;text-align:right" onchange="majCoursBourse('${p.titre}', this.value)"></td>
      <td class="num">${fmt(p.valeur_marche)}</td>
      <td class="num" style="color:${p.plus_value_latente >= 0 ? 'var(--green)' : 'var(--red)'}">${fmt(p.plus_value_latente)}</td>
      <td class="num" style="color:${p.performance_latente >= 0 ? 'var(--green)' : 'var(--red)'}">${(p.performance_latente*100).toFixed(2)} %</td>
    </tr>`).join('') + '</tbody></table>';
}

/* ---------------- Gains réalisés ---------------- */
async function chargerGainsBourse() {
  const liste = await api('/api/bourse/gains');
  if (!liste.length) {
    $('b-liste-gains').innerHTML = '<div class="vide">Aucune vente enregistrée pour le moment.</div>';
    return;
  }
  $('b-liste-gains').innerHTML = '<table><tbody>' + liste.map(g => `
    <tr>
      <td style="color:var(--muted);white-space:nowrap">${g.date_operation.slice(8)}/${g.date_operation.slice(5,7)}</td>
      <td>${g.titre}</td>
      <td class="num">${g.quantite}</td>
      <td class="num">${fmt(g.gain_brut)}</td>
      <td class="num">${fmt(g.tpcvm)}</td>
      <td class="num" style="color:${g.gain_net >= 0 ? 'var(--green)' : 'var(--red)'}">${fmt(g.gain_net)}</td>
    </tr>`).join('') + '</tbody></table>';
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
    <div class="kpi"><div class="l">Frais totaux payés</div><div class="v" style="color:var(--accent)">${fmt(d.frais_totaux)}</div>
      <div class="h">commissions + TVA + autres</div></div>
    <div class="kpi"><div class="l">Résultat net global</div><div class="v" style="color:${cGlobal}">${fmt(d.resultat_net_global)}</div></div>`;
}

/* ---------------- Paramètres ---------------- */
async function chargerParametresBourse() {
  const p = await api('/api/bourse/parametres');
  $('bp-commission').value = (p.taux_commission * 100).toFixed(2).replace('.', ',');
  $('bp-tva').value = (p.taux_tva * 100).toFixed(2).replace('.', ',');
  $('bp-tpcvm').value = (p.taux_tpcvm * 100).toFixed(2).replace('.', ',');
}

async function sauverParametresBourse() {
  const comm = lireMontant('bp-commission');
  const tva = lireMontant('bp-tva');
  const tpcvm = lireMontant('bp-tpcvm');
  if ([comm, tva, tpcvm].some(v => isNaN(v) || v < 0)) return toast('Taux invalide', false);
  await api('/api/bourse/parametres', {
    method: 'PUT', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ taux_commission: comm / 100, taux_tva: tva / 100, taux_tpcvm: tpcvm / 100 }),
  });
  toast('Paramètres enregistrés ✓');
}

/* ---------------- Point d'entrée de l'onglet ---------------- */
function chargerBourse() {
  changerVueBourse(vueBourse);
}