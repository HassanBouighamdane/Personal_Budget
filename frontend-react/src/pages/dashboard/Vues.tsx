/* Vues du dashboard budget — mêmes KPI, graphiques et tableaux que l'ancien app.js */
import { Box, Group, Progress, Skeleton, Stack, Table, Text } from '@mantine/core';
import {
  IconAlertTriangle, IconArrowDownLeft, IconArrowUpRight, IconBriefcase, IconChartBar, IconChartLine, IconPercentage, IconPigMoney, IconReceipt, IconScale, IconTarget, IconTrophy, IconWallet,
} from '@tabler/icons-react';

import {
  dateFr, decalerDate, fmt, JOURS_FR, jjmm, jjmmaa, libelleMois, MOIS_FR, moisCourt, nombreFr, nomJour,
} from '../../lib/format';
import { C, PALETTE, regrouperAutres, signe, T } from '../../lib/palette';
import type { DashboardBourse } from '../../lib/types';
import {
  useResumeAnnee, useResumeBourseSilencieux, useResumeGlobal, useResumeJour, useResumeMois, useResumeSemaine,
} from '../../lib/queries';
import { Donut, Graphique, optionsSeries } from '../../components/Graphique';
import { Carte, Grille2, GrilleKpi, Kpi, Tableau, Variation, Vide } from '../../components/ui';
import { EnTetePeriode, type NavDashboard } from './Dashboard';

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

function KpisBourse({ bourse, libelle }: { bourse: DashboardBourse | null | undefined; libelle: string | number }) {
  if (!bourse) return null;
  return (
    <>
      <Kpi label="Portefeuille Bourse" icone={IconBriefcase} teinte="bleu" valeur={fmt(bourse.valeur_marche)} couleur={T.rev}
           aide={<Text span inherit c={signe(bourse.plus_value_latente)}>
             {bourse.plus_value_latente >= 0 ? '+' : ''}{fmt(bourse.plus_value_latente)} ({(bourse.performance_latente * 100).toFixed(2)} %)
           </Text>} />
      <Kpi label={`Résultat Bourse ${libelle}`} icone={IconChartLine} teinte="emeraude" valeur={fmt(bourse.resultat_net_periode)}
           couleur={signe(bourse.resultat_net_periode)} aide="gains nets + dividendes − frais de compte" />
    </>
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
  const titre = libelleMois(nav.mois);
  if (!r) return <Squelette nav={nav} titre={titre} />;

  const epC = r.epargne >= r.objectif_epargne ? T.ep : (r.epargne >= 0 ? T.warn : T.neg);
  const now = new Date();
  const estMoisCourant = nav.mois === `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`;
  const jourRef = estMoisCourant ? now.getDate() : r.nb_jours;

  return (
    <>
      <EnTetePeriode nav={nav} titre={titre} />
      <GrilleKpi>
        <Kpi label="Revenus" icone={IconArrowDownLeft} teinte="bleu" valeur={fmt(r.total_revenus)} couleur={T.rev}
             badge={<Variation actuel={r.total_revenus} precedent={r.revenus_mois_precedent} inverse />} />
        <Kpi label="Dépenses" icone={IconArrowUpRight} teinte="rose" valeur={fmt(r.total_depenses)} couleur={T.dep}
             badge={<Variation actuel={r.total_depenses} precedent={r.depenses_mois_precedent} />}
             aide={<>{fmt(r.total_depenses / Math.max(jourRef, 1))} / jour
               {r.projection_fin_mois ? <> · projection fin de mois : <b>{fmt(r.projection_fin_mois)}</b></> : null}</>} />
        <Kpi label="Reste à dépenser" icone={IconWallet} teinte="emeraude" valeur={fmt(r.reste_budget)} couleur={signe(r.reste_budget)}
             aide={`sur un budget de ${fmt(r.budget_total)}`} />
        <Kpi label="Épargne" icone={IconPigMoney} teinte="emeraude" valeur={fmt(r.epargne)} couleur={epC} aide={`Objectif : ${fmt(r.objectif_epargne)}`} />
        <Kpi label="Taux d'épargne" icone={IconPercentage} teinte="marque" valeur={`${r.taux_epargne}%`} couleur={epC} />
        <KpisBourse bourse={bourse} libelle="du mois" />
      </GrilleKpi>

      <Grille2>
        <Carte titre="Budget vs Réel" description="Dépensé par rapport au budget de chaque catégorie">
          {r.budget_vs_reel.length ? (
            <Stack gap="md">
              {r.budget_vs_reel.map(b => {
                const couleur = b.pct <= 80 ? T.ep : (b.pct <= 100 ? T.warn : T.neg);
                return (
                  <Box key={b.cat}>
                    <Group justify="space-between" mb={6} wrap="nowrap" gap="xs">
                      <Text fz="sm" fw={600} truncate>{b.cat}</Text>
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

  const dansBudget = r.total_depenses <= r.budget_jour;
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
             aide={dansBudget ? 'dans le budget ✓' : 'dépassé de ' + fmt(r.total_depenses - r.budget_jour)} />
        <Kpi label="Moyenne / jour du mois" icone={IconChartBar} teinte="gray" valeur={fmt(r.moyenne_jour_mois)} />
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

  return (
    <>
      <EnTetePeriode nav={nav} titre={titre} />
      <GrilleKpi>
        <Kpi label="Dépenses" icone={IconArrowUpRight} teinte="rose" valeur={fmt(r.total_depenses)} couleur={T.dep}
             badge={<Variation actuel={r.total_depenses} precedent={r.depenses_semaine_precedente} />}
             aide={`semaine préc. : ${fmt(r.depenses_semaine_precedente)}`} />
        <Kpi label="Revenus" icone={IconArrowDownLeft} teinte="bleu" valeur={fmt(r.total_revenus)} couleur={T.rev}
             badge={<Variation actuel={r.total_revenus} precedent={r.revenus_semaine_precedente} inverse />} />
        <Kpi label="Solde de la semaine" icone={IconScale} teinte="emeraude" valeur={fmt(r.epargne)} couleur={signe(r.epargne)} />
        <Kpi label="Reste budget hebdo" icone={IconWallet} teinte="marque" valeur={fmt(r.reste_budget_hebdo)} couleur={signe(r.reste_budget_hebdo)}
             aide={`sur ${fmt(r.budget_hebdo)}`} />
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
             aide={`moyenne : ${fmt(r.moyenne_dep_mois)} / mois actif`} />
        <Kpi label={`Épargne ${nav.annee}`} icone={IconPigMoney} teinte="emeraude" valeur={fmt(r.epargne)} couleur={signe(r.epargne)} aide={`taux : ${r.taux_epargne}%`} />
        <Kpi label="Objectif atteint" icone={IconTarget} teinte="marque" valeur={`${r.nb_mois_objectif} / ${r.nb_mois_actifs}`}
             aide={`mois à ≥ ${fmt(r.objectif_epargne)} d'épargne`} />
        {r.meilleur_mois && <Kpi label="Meilleur mois" icone={IconTrophy} teinte="emeraude" valeur={MOIS_FR[r.meilleur_mois.m - 1]} couleur={T.ep}
                                 aide={`épargne : ${fmt(r.meilleur_mois.ep)}`} />}
        {r.pire_mois && <Kpi label="Mois le plus difficile" icone={IconAlertTriangle} teinte="rouge" valeur={MOIS_FR[r.pire_mois.m - 1]} couleur={T.neg}
                             aide={`épargne : ${fmt(r.pire_mois.ep)}`} />}
        <KpisBourse bourse={bourse} libelle={nav.annee} />
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
  if (!r) return <Squelette nav={nav} titre="Tout l’historique" />;

  const titre = r.premier_mois
    ? 'Depuis ' + MOIS_FR[+r.premier_mois.slice(5) - 1].toLowerCase() + ' ' + r.premier_mois.slice(0, 4)
    : 'Tout l’historique';
  const labels = r.par_mois.map(x => moisCourt(x.m));
  // Épargne hors Bourse = épargne du budget − argent versé sur le compte Bourse ;
  // l'épargne totale y ajoute le patrimoine Bourse à sa valeur de marché (titres + espèces).
  const horsBourse = r.epargne - (bourse?.apports_nets ?? 0);
  const epargneTotale = horsBourse + (bourse?.patrimoine_total ?? 0);

  return (
    <>
      <EnTetePeriode nav={nav} titre={titre} />
      <GrilleKpi>
        <Kpi label="Revenus totaux" icone={IconArrowDownLeft} teinte="bleu" valeur={fmt(r.total_revenus)} couleur={T.rev} aide={`moyenne : ${fmt(r.moyenne_rev_mois)} / mois actif`} />
        <Kpi label="Dépenses totales" icone={IconArrowUpRight} teinte="rose" valeur={fmt(r.total_depenses)} couleur={T.dep} aide={`moyenne : ${fmt(r.moyenne_dep_mois)} / mois actif`} />
        <Kpi label="Épargne totale" icone={IconPigMoney} teinte="emeraude" valeur={fmt(epargneTotale)} couleur={signe(epargneTotale)}
             aide={bourse ? `hors Bourse : ${fmt(horsBourse)} · taux : ${r.taux_epargne}%` : `taux : ${r.taux_epargne}%`} />
        <Kpi label="Objectif atteint" icone={IconTarget} teinte="marque" valeur={`${r.nb_mois_objectif} / ${r.nb_mois_actifs}`}
             aide={`mois à ≥ ${fmt(r.objectif_epargne)} d'épargne`} />
        {r.meilleur_mois && <Kpi label="Meilleur mois" icone={IconTrophy} teinte="emeraude" valeur={moisCourt(r.meilleur_mois.m)} couleur={T.ep}
                                 aide={`épargne : ${fmt(r.meilleur_mois.ep)}`} />}
        {r.pire_mois && <Kpi label="Mois le plus difficile" icone={IconAlertTriangle} teinte="rouge" valeur={moisCourt(r.pire_mois.m)} couleur={T.neg}
                             aide={`épargne : ${fmt(r.pire_mois.ep)}`} />}
        <KpisBourse bourse={bourse} libelle="(global)" />
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

      <Carte titre="Top dépenses (tout l'historique)">
        <TableTop top={r.top} vide="Aucune dépense enregistrée" format={jjmmaa} />
      </Carte>
    </>
  );
}
