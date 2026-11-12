/* Vues du dashboard budget — mêmes KPI, graphiques et tableaux que l'ancien app.js */
import { Box, Group, Progress, Skeleton, Stack, Table, Text, Tooltip } from '@mantine/core';
import {
  IconAlertTriangle, IconArrowDownLeft, IconArrowUpRight, IconChartBar, IconChartLine, IconPigMoney, IconReceipt, IconScale, IconTarget, IconTrophy, IconWallet,
} from '@tabler/icons-react';

import {
  dateFr, decalerDate, fmt, JOURS_FR, jjmm, jjmmaa, libelleMois, MOIS_FR, moisCourt, nombreFr, nomJour,
} from '../../lib/format';
import { C, PALETTE, regrouperAutres, signe, T } from '../../lib/palette';
import type { DashboardBourse } from '../../lib/types';
import {
  useEcheances, usePatrimoineSilencieux, useResumeAnnee, useResumeBourseSilencieux, useResumeGlobal, useResumeJour, useResumeMois, useResumeSemaine, useTags,
} from '../../lib/queries';
import { Donut, Graphique, optionsSeries } from '../../components/Graphique';
import { Carte, Grille2, GrilleKpi, Kpi, Tableau, Variation, Vide } from '../../components/ui';
import { EnTetePeriode, type NavDashboard } from './Dashboard';
import { aProvisionner } from '../carnet/Echeances';

/* ---------- Pièces communes ---------- */
function Squelette({ nav, titre }: { nav: NavDashboard; titre: string }) {
  return (
    <>
      <EnTetePeriode nav={nav} titre={titre} />
      <GrilleKpi>{Array.from({ length: 4 }, (_, i) => <Skeleton key={i} h={108} radius="lg" />)}</GrilleKpi>
      <Grille2><Skeleton h={320} radius="lg" /><Skeleton h={320} radius="lg" /></Grille2>
    </>
  );
}

const fmtSigne = (v: number) => (v >= 0 ? '+' : '') + fmt(v);

/** Résultat réalisé sur la période ; la valeur du portefeuille (photo du jour) n'est affichée que dans la vue globale */
function KpiResultatBourse({ bourse, libelle }: { bourse: DashboardBourse | null | undefined; libelle: string | number }) {
  if (!bourse) return null;
  return (
    <Kpi label={`Résultat Bourse ${libelle}`} icone={IconChartLine} teinte="emeraude" valeur={fmt(bourse.resultat_net_periode)}
         couleur={signe(bourse.resultat_net_periode)} aide="gains nets + dividendes − frais de compte" />
  );
}

type Top = { date: string; categorie: string; description: string; montant: number };
function TableTop({ top, vide, format = jjmm }: { top: Top[]; vide: string; format?: (d: string) => string }) {
  if (!top.length) return <Vide>{vide}</Vide>;
  return (
    <Tableau minWidth={420}>
      <Table.Thead>
        <Table.Tr><Table.Th>Date</Table.Th><Table.Th>Catégorie</Table.Th><Table.Th>Description</Table.Th><Table.Th className="num">Montant</Table.Th></Table.Tr>
      </Table.Thead>
      <Table.Tbody>
        {top.map((t, i) => (
          <Table.Tr key={i}>
            <Table.Td c="dimmed" style={{ whiteSpace: 'nowrap' }}>{format(t.date)}</Table.Td>
            <Table.Td>{t.categorie}</Table.Td>
            <Table.Td>{t.description}</Table.Td>
            <Table.Td className="num chiffre" c={T.dep} fw={600}>{fmt(t.montant)}</Table.Td>
          </Table.Tr>
        ))}
      </Table.Tbody>
    </Tableau>
  );
}

const donutCategories = (donut: { cat: string; montant: number }[]) =>
  regrouperAutres(donut.map(x => x.cat), donut.map(x => x.montant));

function RepartitionCats({ donut, vide = 'Aucune dépense' }: { donut: { cat: string; montant: number }[]; vide?: string }) {
  if (!donut.length) return <Vide>{vide}</Vide>;
  return <Donut {...donutCategories(donut)} />;
}

const seriesRevDepEp = (par: { rev: number; dep: number; ep: number }[], labels: string[]) => ({
  labels,
  datasets: [
    { type: 'bar' as const, label: 'Revenus', data: par.map(x => x.rev), backgroundColor: C.rev, borderRadius: 4 },
    { type: 'bar' as const, label: 'Dépenses', data: par.map(x => x.dep), backgroundColor: C.dep, borderRadius: 4 },
    { type: 'line' as const, label: 'Épargne', data: par.map(x => x.ep), borderColor: C.ep, backgroundColor: C.ep, tension: .3, pointRadius: 3 },
  ],
});

const serieEpargneCumulee = (labels: string[], data: number[]) => ({
  labels,
  datasets: [{ label: 'Épargne cumulée', data, borderColor: C.ep, backgroundColor: 'rgba(16,185,129,.14)', fill: true, tension: .3, pointRadius: 0 }],
});

/* ---------- Vue mensuelle ---------- */
export function VueMois({ nav }: { nav: NavDashboard }) {
  const { data: r } = useResumeMois(nav.mois);
  const { data: bourse } = useResumeBourseSilencieux('mois=' + nav.mois);
  const { data: echeances } = useEcheances();
  const titre = libelleMois(nav.mois);
  if (!r) return <Squelette nav={nav} titre={titre} />;

  const epC = r.epargne >= r.objectif_epargne ? T.ep : (r.epargne >= 0 ? T.warn : T.neg);
  const now = new Date();
  const estMoisCourant = nav.mois === `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`;
  const jourRef = estMoisCourant ? now.getDate() : r.nb_jours;
  // Mois en cours : le mois précédent est pris jusqu'au même jour (cf. jour_comparaison)
  const vsMoisPrec = (precedent: number, total: number) => r.jour_comparaison
    ? `vs ${fmt(precedent)} du 1er au ${r.jour_comparaison} le mois dernier (mois entier : ${fmt(total)})`
    : `vs ${fmt(precedent)} le mois dernier`;
  // Même mois l'an dernier (saisonnalité), sur la même durée pour le mois en cours
  const [annee, numMois] = nav.mois.split('-').map(Number);
  const moisAnPasse = `${MOIS_FR[numMois - 1].toLowerCase()} ${annee - 1}`;
  const vsAnPrec = (precedent: number, total: number) => r.jour_comparaison_annee
    ? `vs ${fmt(precedent)} du 1er au ${r.jour_comparaison_annee} ${moisAnPasse} (mois entier : ${fmt(total)})`
    : `vs ${fmt(precedent)} en ${moisAnPasse}`;

  return (
    <>
      <EnTetePeriode nav={nav} titre={titre} />
      <GrilleKpi>
        <Kpi label="Revenus" icone={IconArrowDownLeft} teinte="bleu" valeur={fmt(r.total_revenus)} couleur={T.rev}
             badge={<>
               <Variation actuel={r.total_revenus} precedent={r.revenus_mois_precedent} inverse
                          libelle={vsMoisPrec(r.revenus_mois_precedent, r.revenus_mois_precedent_total)} />
               <Variation actuel={r.total_revenus} precedent={r.revenus_annee_precedente} inverse prefixe="N−1"
                          libelle={vsAnPrec(r.revenus_annee_precedente, r.revenus_annee_precedente_total)} />
             </>} />
        <Kpi label="Dépenses" icone={IconArrowUpRight} teinte="rose" valeur={fmt(r.total_depenses)} couleur={T.dep}
             badge={<>
               <Variation actuel={r.total_depenses} precedent={r.depenses_mois_precedent}
                          libelle={vsMoisPrec(r.depenses_mois_precedent, r.depenses_mois_precedent_total)} />
               <Variation actuel={r.total_depenses} precedent={r.depenses_annee_precedente} prefixe="N−1"
                          libelle={vsAnPrec(r.depenses_annee_precedente, r.depenses_annee_precedente_total)} />
             </>}
             aide={<>{fmt(r.depenses_variables / Math.max(jourRef, 1))} / jour{r.charges_fixes ? ' hors charges fixes' : ''}
               {r.projection_fin_mois ? <> · projection fin de mois : <b>{fmt(r.projection_fin_mois)}</b></> : null}</>} />
        <Kpi label="Reste à dépenser" icone={IconWallet} teinte="emeraude" valeur={fmt(r.reste_budget)} couleur={signe(r.reste_budget)}
             aide={`sur un budget de ${fmt(r.budget_total)}`} />
        <Kpi label="Épargne" icone={IconPigMoney} teinte="emeraude" valeur={fmt(r.epargne)} couleur={epC}
             aide={`objectif : ${fmt(r.objectif_epargne)} · taux : ${r.epargne >= 0 ? r.taux_epargne + '%' : '—'}`
               + (estMoisCourant && aProvisionner(echeances).nb ? ` · à provisionner ce mois : ${fmt(aProvisionner(echeances).total)}` : '')} />
        <KpiResultatBourse bourse={bourse} libelle="du mois" />
      </GrilleKpi>

      <Grille2>
        <Carte titre="Budget vs Réel" description="Dépensé par rapport au budget de chaque catégorie · survole un nom souligné pour l'an dernier">
          {r.budget_vs_reel.length ? (
            <Stack gap="md">
              {r.budget_vs_reel.map(b => {
                const couleur = b.pct <= 80 ? T.ep : (b.pct <= 100 ? T.warn : T.neg);
                return (
                  <Box key={b.cat}>
                    <Group justify="space-between" mb={6} wrap="nowrap" gap="xs">
                      {b.an_dernier > 0 ? (
                        <Tooltip label={`${moisAnPasse}${r.jour_comparaison_annee ? ` (au ${r.jour_comparaison_annee})` : ''} : ${fmt(b.an_dernier)}`}>
                          <Text fz="sm" fw={600} truncate style={{ textDecoration: 'underline dotted', textUnderlineOffset: 3 }}>{b.cat}</Text>
                        </Tooltip>
                      ) : <Text fz="sm" fw={600} truncate>{b.cat}</Text>}
                      <Group gap={8} wrap="nowrap">
                        <Text fz="xs" c="dimmed" className="chiffre" style={{ whiteSpace: 'nowrap' }}>
                          {fmt(b.reel)} <Text span inherit opacity={0.6}>/ {fmt(b.budget)}</Text>
                        </Text>
                        <Text fz="xs" fw={700} className="chiffre" c={couleur} w={40} ta="right">{b.pct}%</Text>
                      </Group>
                    </Group>
                    <Progress value={Math.min(b.pct, 100)} color={couleur} size={8} radius="xl" transitionDuration={400} />
                  </Box>
                );
              })}
            </Stack>
          ) : <Vide>Aucune donnée</Vide>}
        </Carte>
        <Carte titre="Répartition" description="Dépenses du mois par catégorie"><RepartitionCats donut={r.donut} /></Carte>
      </Grille2>

      <Grille2>
        <Carte titre="Dépenses cumulées" description="Comparées au budget total du mois">
          <Graphique type="line" options={optionsSeries()} data={{
            labels: Array.from({ length: r.nb_jours }, (_, i) => i + 1),
            datasets: [
              { label: 'Cumul dépenses', data: r.cumul_quotidien, borderColor: C.dep, backgroundColor: 'rgba(244,63,94,.14)', fill: true, tension: .3, pointRadius: 0 },
              { label: 'Budget total', data: Array(r.nb_jours).fill(r.budget_total), borderColor: C.budget, borderDash: [6, 4], pointRadius: 0 },
            ],
          }} />
        </Carte>
        <Carte titre="Évolution sur 6 mois" description="Revenus et dépenses">
          <Graphique type="bar" options={optionsSeries()} data={{
            labels: r.evolution.map(x => x.m),
            datasets: [
              { label: 'Revenus', data: r.evolution.map(x => x.rev), backgroundColor: C.rev, borderRadius: 5 },
              { label: 'Dépenses', data: r.evolution.map(x => x.dep), backgroundColor: C.dep, borderRadius: 5 },
            ],
          }} />
        </Carte>
      </Grille2>

      <Carte titre="Top dépenses du mois"><TableTop top={r.top} vide="Aucune dépense ce mois" /></Carte>

    </>
  );
}

/* ---------- Vue journalière ---------- */
export function VueJour({ nav }: { nav: NavDashboard }) {
  const { data: r } = useResumeJour(nav.jour);
  const titre = nomJour(nav.jour) + ' ' + dateFr(nav.jour);
  if (!r) return <Squelette nav={nav} titre={titre} />;

  // Les charges fixes (loyer, factures) ne sont pas réparties au jour : seules les dépenses variables comptent
  const dansBudget = r.depenses_variables <= r.budget_jour;
  const horsFixes = r.charges_fixes ? ' · hors charges fixes' : '';
  const lignes = [
    ...r.depenses.map(x => ({ lbl: x.categorie + (x.description ? ' — ' + x.description : ''), m: x.montant, dep: true })),
    ...r.revenus.map(x => ({ lbl: (x.source || 'Revenu') + (x.description ? ' — ' + x.description : ''), m: x.montant, dep: false })),
  ];

  return (
    <>
      <EnTetePeriode nav={nav} titre={titre} />
      <GrilleKpi>
        <Kpi label="Dépenses du jour" icone={IconArrowUpRight} teinte="rose" valeur={fmt(r.total_depenses)} couleur={T.dep}
             badge={<Variation actuel={r.total_depenses} precedent={r.depenses_veille} />}
             aide={`veille : ${fmt(r.depenses_veille)}`} />
        <Kpi label="Revenus du jour" icone={IconArrowDownLeft} teinte="bleu" valeur={fmt(r.total_revenus)} couleur={T.rev} />
        <Kpi label="Budget journalier" icone={IconTarget} teinte="marque" valeur={fmt(r.budget_jour)} couleur={dansBudget ? T.ep : T.neg}
             aide={(dansBudget ? 'dans le budget ✓' : 'dépassé de ' + fmt(r.depenses_variables - r.budget_jour)) + horsFixes} />
        <Kpi label="Moyenne / jour du mois" icone={IconChartBar} teinte="gray" valeur={fmt(r.moyenne_jour_mois)}
             aide={r.charges_fixes ? 'hors charges fixes' : undefined} />
        <Kpi label="Transactions" icone={IconReceipt} teinte="gray" valeur={r.nb_transactions} />
      </GrilleKpi>
      <Grille2>
        <Carte titre="Répartition du jour"><RepartitionCats donut={r.donut} vide="Aucune dépense ce jour" /></Carte>
        <Carte titre="Transactions du jour">
          {lignes.length ? (
            <Tableau>
              <Table.Tbody>
                {lignes.map((l, i) => (
                  <Table.Tr key={i}>
                    <Table.Td>{l.lbl}</Table.Td>
                    <Table.Td className="num chiffre" c={l.dep ? T.dep : T.rev} fw={600}>{l.dep ? '−' : '+'} {fmt(l.m)}</Table.Td>
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Tableau>
          ) : <Vide>Aucune transaction ce jour</Vide>}
        </Carte>
      </Grille2>
    </>
  );
}

/* ---------- Vue hebdomadaire ---------- */
export function VueSemaine({ nav }: { nav: NavDashboard }) {
  const { data: r } = useResumeSemaine(nav.semaine);
  // Titre calculé localement (lundi → dimanche) pour s'afficher avant la réponse
  const [a, m, j] = nav.semaine.split('-').map(Number);
  const lundi = decalerDate(nav.semaine, -((new Date(a, m - 1, j).getDay() + 6) % 7));
  const titre = 'Semaine du ' + dateFr(lundi, false) + ' au ' + dateFr(decalerDate(lundi, 6));
  if (!r) return <Squelette nav={nav} titre={titre} />;
  // Semaine en cours : la semaine précédente est prise jusqu'au même jour
  const vsSemPrec = r.comparaison_partielle ? 'par rapport à la semaine dernière au même jour' : 'par rapport à la semaine précédente';

  return (
    <>
      <EnTetePeriode nav={nav} titre={titre} />
      <GrilleKpi>
        <Kpi label="Dépenses" icone={IconArrowUpRight} teinte="rose" valeur={fmt(r.total_depenses)} couleur={T.dep}
             badge={<Variation actuel={r.total_depenses} precedent={r.depenses_semaine_precedente} libelle={vsSemPrec} />}
             aide={r.comparaison_partielle
               ? `sem. préc. au même jour : ${fmt(r.depenses_semaine_precedente)} · entière : ${fmt(r.depenses_semaine_precedente_totale)}`
               : `semaine préc. : ${fmt(r.depenses_semaine_precedente)}`} />
        <Kpi label="Revenus" icone={IconArrowDownLeft} teinte="bleu" valeur={fmt(r.total_revenus)} couleur={T.rev}
             badge={<Variation actuel={r.total_revenus} precedent={r.revenus_semaine_precedente} inverse libelle={vsSemPrec} />} />
        <Kpi label="Solde de la semaine" icone={IconScale} teinte="emeraude" valeur={fmt(r.epargne)} couleur={signe(r.epargne)} />
        <Kpi label="Reste budget hebdo" icone={IconWallet} teinte="marque" valeur={fmt(r.reste_budget_hebdo)} couleur={signe(r.reste_budget_hebdo)}
             aide={`sur ${fmt(r.budget_hebdo)}${r.charges_fixes ? ' · hors charges fixes' : ''}`} />
      </GrilleKpi>
      <Carte titre="Dépenses et revenus par jour">
        <Graphique type="bar" hauteur={320} options={optionsSeries()} data={{
          labels: r.par_jour.map((x, i) => JOURS_FR[i].slice(0, 3) + ' ' + x.date.slice(8)),
          datasets: [
            { label: 'Dépenses', data: r.par_jour.map(x => x.dep), backgroundColor: C.dep, borderRadius: 5 },
            { label: 'Revenus', data: r.par_jour.map(x => x.rev), backgroundColor: C.rev, borderRadius: 5 },
          ],
        }} />
      </Carte>
      <Grille2>
        <Carte titre="Répartition de la semaine"><RepartitionCats donut={r.donut} vide="Aucune dépense cette semaine" /></Carte>
        <Carte titre="Top dépenses de la semaine">
          {r.top.length ? (
            <Tableau>
              <Table.Tbody>
                {r.top.map((t, i) => (
                  <Table.Tr key={i}>
                    <Table.Td c="dimmed" style={{ whiteSpace: 'nowrap' }}>{jjmm(t.date)}</Table.Td>
                    <Table.Td>{t.categorie}{t.description ? ' — ' + t.description : ''}</Table.Td>
                    <Table.Td className="num chiffre" c={T.dep} fw={600}>{fmt(t.montant)}</Table.Td>
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Tableau>
          ) : <Vide>Aucune dépense cette semaine</Vide>}
        </Carte>
      </Grille2>
    </>
  );
}

/* ---------- Vue annuelle ---------- */
export function VueAnnee({ nav }: { nav: NavDashboard }) {
  const { data: r } = useResumeAnnee(nav.annee);
  const { data: bourse } = useResumeBourseSilencieux('annee=' + nav.annee);
  const titre = 'Année ' + nav.annee;
  if (!r) return <Squelette nav={nav} titre={titre} />;

  const labels = MOIS_FR.map(m => m.slice(0, 4));
  const topCats = r.categories.slice(0, 8);
  const cats = Object.keys(r.grille);
  const maxVal = cats.length ? Math.max(...cats.flatMap(c => r.grille[c])) : 0;

  return (
    <>
      <EnTetePeriode nav={nav} titre={titre} />
      <GrilleKpi>
        <Kpi label={`Revenus ${nav.annee}`} icone={IconArrowDownLeft} teinte="bleu" valeur={fmt(r.total_revenus)} couleur={T.rev} />
        <Kpi label={`Dépenses ${nav.annee}`} icone={IconArrowUpRight} teinte="rose" valeur={fmt(r.total_depenses)} couleur={T.dep}
             aide={r.nb_mois_actifs ? `moyenne : ${fmt(r.moyenne_dep_mois)} / mois terminé` : 'aucun mois terminé'} />
        <Kpi label={`Épargne ${nav.annee}`} icone={IconPigMoney} teinte="emeraude" valeur={fmt(r.epargne)} couleur={signe(r.epargne)} aide={`taux : ${r.taux_epargne}%`} />
        <Kpi label="Objectif atteint" icone={IconTarget} teinte="marque" valeur={`${r.nb_mois_objectif} / ${r.nb_mois_actifs}`}
             aide={`mois terminés à ≥ ${fmt(r.objectif_epargne)} d'épargne`} />
        {r.meilleur_mois && <Kpi label="Meilleur mois" icone={IconTrophy} teinte="emeraude" valeur={MOIS_FR[r.meilleur_mois.m - 1]} couleur={T.ep}
                                 aide={`épargne : ${fmt(r.meilleur_mois.ep)}`} />}
        {r.pire_mois && <Kpi label="Mois le plus difficile" icone={IconAlertTriangle} teinte="rouge" valeur={MOIS_FR[r.pire_mois.m - 1]} couleur={T.neg}
                             aide={`épargne : ${fmt(r.pire_mois.ep)}`} />}
        <KpiResultatBourse bourse={bourse} libelle={nav.annee} />
      </GrilleKpi>

      <Carte titre="Revenus, dépenses et épargne par mois">
        <Graphique type="bar" hauteur={320} options={optionsSeries()} data={seriesRevDepEp(r.par_mois, labels)} />
      </Carte>
      <Grille2>
        <Carte titre="Dépenses par catégorie (année)">
          {topCats.length ? (
            <Graphique type="bar" options={optionsSeries(true)} data={{
              labels: topCats.map(c => c.cat),
              datasets: [{ label: 'Total ' + nav.annee, data: topCats.map(c => c.total), backgroundColor: PALETTE, borderRadius: 5 }],
            }} />
          ) : <Vide>Aucune dépense cette année</Vide>}
        </Carte>
        <Carte titre="Épargne cumulée">
          <Graphique type="line" options={optionsSeries()} data={serieEpargneCumulee(labels, r.epargne_cumulee)} />
        </Carte>
      </Grille2>

      <Carte titre="Grille thermique — catégories × mois">
        {!cats.length ? <Vide>Aucune dépense cette année</Vide> : (
          <Table.ScrollContainer minWidth={760}>
            <Table className="grille" withRowBorders={false}>
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>Catégorie</Table.Th>
                  {labels.map(l => <Table.Th key={l}>{l}</Table.Th>)}
                  <Table.Th className="num">Total</Table.Th>
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {cats.map(c => {
                  const vals = r.grille[c];
                  const tot = vals.reduce((x, y) => x + y, 0);
                  return (
                    <Table.Tr key={c}>
                      <Table.Td fw={600}>{c}</Table.Td>
                      {vals.map((v, i) => (
                        <Table.Td key={i} className="chiffre"
                                  style={{ background: `rgba(244,63,94,${(maxVal ? v / maxVal * 0.85 : 0).toFixed(2)})`, borderRadius: 4 }}>
                          {v ? nombreFr(Math.round(v)) : ''}
                        </Table.Td>
                      ))}
                      <Table.Td className="num chiffre" c={T.dep} fw={600}>{fmt(tot)}</Table.Td>
                    </Table.Tr>
                  );
                })}
              </Table.Tbody>
            </Table>
          </Table.ScrollContainer>
        )}
      </Carte>
    </>
  );
}

/* ---------- Vue globale (tout l'historique) ---------- */
export function VueGlobal({ nav }: { nav: NavDashboard }) {
  const { data: r } = useResumeGlobal();
  const { data: bourse } = useResumeBourseSilencieux('');   // sans filtre = tout l'historique Bourse
  const { data: patrimoine } = usePatrimoineSilencieux();
  if (!r) return <Squelette nav={nav} titre="Tout l’historique" />;

  const titre = r.premier_mois
    ? 'Depuis ' + MOIS_FR[+r.premier_mois.slice(5) - 1].toLowerCase() + ' ' + r.premier_mois.slice(0, 4)
    : 'Tout l’historique';
  const labels = r.par_mois.map(x => moisCourt(x.m));
  // Liquidités = épargne du budget − argent versé sur le compte Bourse ;
  // le patrimoine net y ajoute le patrimoine Bourse à sa valeur de marché (titres + espèces).
  // (repli si le détail du patrimoine — autres actifs, dettes, solde de départ — n'a pas pu être chargé)
  const liquidites = patrimoine?.liquidites ?? r.epargne - (bourse?.apports_nets ?? 0);
  const patrimoineNet = patrimoine?.total ?? liquidites + (bourse?.patrimoine_total ?? 0);
  const autres = patrimoine ? patrimoine.autres_actifs + patrimoine.creances - patrimoine.dettes : 0;
  // Performance globale = plus-value latente + résultat réalisé sur tout l'historique
  const perfBourse = (bourse?.plus_value_latente ?? 0) + (bourse?.resultat_net_periode ?? 0);

  return (
    <>
      <EnTetePeriode nav={nav} titre={titre} />
      <GrilleKpi>
        <Kpi label="Revenus totaux" icone={IconArrowDownLeft} teinte="bleu" valeur={fmt(r.total_revenus)} couleur={T.rev} aide={r.nb_mois_actifs ? `moyenne : ${fmt(r.moyenne_rev_mois)} / mois terminé` : undefined} />
        <Kpi label="Dépenses totales" icone={IconArrowUpRight} teinte="rose" valeur={fmt(r.total_depenses)} couleur={T.dep} aide={r.nb_mois_actifs ? `moyenne : ${fmt(r.moyenne_dep_mois)} / mois terminé` : undefined} />
        {bourse
          ? <Kpi label="Patrimoine net" icone={IconPigMoney} teinte="emeraude" valeur={fmt(patrimoineNet)} couleur={signe(patrimoineNet)}
                 aide={`liquidités : ${fmt(liquidites)} · Bourse : ${fmt(bourse.patrimoine_total)}${autres ? ` · autres : ${fmt(autres)}` : ''}`} />
          : <Kpi label="Épargne totale" icone={IconPigMoney} teinte="emeraude" valeur={fmt(r.epargne)} couleur={signe(r.epargne)} aide={`taux : ${r.taux_epargne}%`} />}
        <Kpi label="Objectif atteint" icone={IconTarget} teinte="marque" valeur={`${r.nb_mois_objectif} / ${r.nb_mois_actifs}`}
             aide={`mois terminés à ≥ ${fmt(r.objectif_epargne)} d'épargne`} />
        {r.meilleur_mois && <Kpi label="Meilleur mois" icone={IconTrophy} teinte="emeraude" valeur={moisCourt(r.meilleur_mois.m)} couleur={T.ep}
                                 aide={`épargne : ${fmt(r.meilleur_mois.ep)}`} />}
        {r.pire_mois && <Kpi label="Mois le plus difficile" icone={IconAlertTriangle} teinte="rouge" valeur={moisCourt(r.pire_mois.m)} couleur={T.neg}
                             aide={`épargne : ${fmt(r.pire_mois.ep)}`} />}
        {bourse && <Kpi label="Performance Bourse" icone={IconChartLine} teinte="emeraude" valeur={fmtSigne(perfBourse)} couleur={signe(perfBourse)}
                        aide={`latent : ${fmtSigne(bourse.plus_value_latente)} · réalisé : ${fmtSigne(bourse.resultat_net_periode)}`} />}
      </GrilleKpi>

      <Carte titre="Revenus, dépenses et épargne par mois">
        <Graphique type="bar" hauteur={320} options={optionsSeries()} data={seriesRevDepEp(r.par_mois, labels)} />
      </Carte>
      <Grille2>
        <Carte titre="Répartition des dépenses"><RepartitionCats donut={r.donut} /></Carte>
        <Carte titre="Épargne cumulée">
          <Graphique type="line" options={optionsSeries()} data={serieEpargneCumulee(labels, r.epargne_cumulee)} />
        </Carte>
      </Grille2>

      <Carte titre="Bilan par année">
        {r.par_annee.length ? (
          <Tableau minWidth={420}>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>Année</Table.Th><Table.Th className="num">Revenus</Table.Th><Table.Th className="num">Dépenses</Table.Th>
                <Table.Th className="num">Épargne</Table.Th><Table.Th className="num">Taux</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {r.par_annee.map(a => (
                <Table.Tr key={a.annee}>
                  <Table.Td fw={600}>{a.annee}</Table.Td>
                  <Table.Td className="num chiffre" c={T.rev}>{fmt(a.rev)}</Table.Td>
                  <Table.Td className="num chiffre" c={T.dep}>{fmt(a.dep)}</Table.Td>
                  <Table.Td className="num chiffre" c={signe(a.ep)}>{fmt(a.ep)}</Table.Td>
                  <Table.Td className="num chiffre">{a.taux_epargne}%</Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Tableau>
        ) : <Vide>Aucune donnée</Vide>}
      </Carte>

      <TableTags />

      <Carte titre="Top dépenses (tout l'historique)">
        <TableTop top={r.top} vide="Aucune dépense enregistrée" format={jjmmaa} />
      </Carte>
    </>
  );
}

/** Coût de chaque tag (« combien a coûté ce voyage ? ») ; le détail se cherche dans Saisie avec #tag */
function TableTags() {
  const { data: tags } = useTags();
  if (!tags?.length) return null;
  return (
    <Carte titre="Tags" description="Total de chaque tag, toutes catégories confondues. Le détail : recherche « #tag » dans Saisie.">
      <Tableau minWidth={520}>
        <Table.Thead>
          <Table.Tr>
            <Table.Th>Tag</Table.Th><Table.Th className="num">Opérations</Table.Th><Table.Th className="num">Dépenses</Table.Th>
            <Table.Th className="num">Revenus</Table.Th><Table.Th>Période</Table.Th>
          </Table.Tr>
        </Table.Thead>
        <Table.Tbody>
          {tags.map(t => (
            <Table.Tr key={t.tag}>
              <Table.Td fw={600}>#{t.tag}</Table.Td>
              <Table.Td className="num chiffre">{t.nb}</Table.Td>
              <Table.Td className="num chiffre" c={T.dep}>{t.depenses ? fmt(t.depenses) : '—'}</Table.Td>
              <Table.Td className="num chiffre" c={T.rev}>{t.revenus ? fmt(t.revenus) : '—'}</Table.Td>
              <Table.Td c="dimmed" fz="xs" style={{ whiteSpace: 'nowrap' }}>
                {t.premier === t.dernier ? jjmmaa(t.premier) : `${jjmmaa(t.premier)} → ${jjmmaa(t.dernier)}`}
              </Table.Td>
            </Table.Tr>
          ))}
        </Table.Tbody>
      </Tableau>
    </Carte>
  );
}
