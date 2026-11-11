/* Bourse — positions, gains réalisés et tableau de bord */
import { useEffect, useState } from 'react';
import { ActionIcon, Box, Button, Group, NumberInput, SegmentedControl, Stack, Table, Text, TextInput, Title, Tooltip } from '@mantine/core';
import {
  IconChevronLeft, IconChevronRight, IconArrowsExchange, IconBuildingBank, IconCash, IconChartDonut, IconChartLine, IconCoins, IconReceipt, IconReceiptTax, IconRefresh, IconReportMoney, IconScale, IconTrendingUp,
} from '@tabler/icons-react';

import { toast } from '../../lib/api';
import { decalerMois, fmt, jjmm, libelleMois } from '../../lib/format';
import { regrouperAutres, signe, T } from '../../lib/palette';
import type { Position } from '../../lib/types';
import { useActualiserCours, useCibles, useDashboardBourse, useEcriture, useGains, usePositions } from '../../lib/queries';
import { Donut } from '../../components/Graphique';
import { Carte, Chargement, Grille2, GrilleKpi, Kpi, Tableau, ThTri, TitreSection, useTri, Vide } from '../../components/ui';
import type { NavBourse, PeriodeBourse } from './Bourse';

const pctFr = (v: number) => (v * 100).toFixed(2) + ' %';

/* ================= Positions ================= */
function CoursEditable({ titre, cours }: { titre: string; cours: number }) {
  const ecrire = useEcriture('bourse');
  const initial = cours ? String(cours) : '';
  const [valeur, setValeur] = useState(initial);

  // Enregistré à la sortie du champ ou sur Entrée, seulement si la valeur a changé (comme onchange avant)
  function valider() {
    if (valeur === initial) return;
    const c = parseFloat(valeur.replace(',', '.'));
    if (isNaN(c) || c < 0) return toast('Cours invalide', false);
    ecrire.mutate({ path: `/api/bourse/prix/${encodeURIComponent(titre)}`, method: 'PUT', body: { cours_actuel: c }, succes: 'Cours mis à jour ✓' });
  }

  return (
    <TextInput size="xs" inputMode="decimal" w={96} styles={{ input: { textAlign: 'right' } }}
               value={valeur} onChange={e => setValeur(e.currentTarget.value)} onBlur={valider}
               onKeyDown={e => { if (e.key === 'Enter') e.currentTarget.blur(); }}
               aria-label={`Cours actuel de ${titre}`} />
  );
}

const dateHeure = (iso: string) =>
  new Date(iso).toLocaleString('fr-FR', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' });

/** Sous le cours : sa provenance (automatique avec date de mise à jour, ou manuel verrouillé) */
function SourceCours({ p }: { p: Position }) {
  const actualiser = useActualiserCours();
  if (p.cours_manuel) {
    return (
      <Group gap={2} wrap="nowrap">
        <Text fz={10} c={T.warn}>manuel</Text>
        <Tooltip label="Remettre en automatique" withArrow>
          <ActionIcon variant="subtle" color="gray" size="xs" loading={actualiser.isPending}
                      onClick={() => actualiser.mutate(p.titre)} aria-label={`Remettre ${p.titre} en cours automatique`}>
            <IconRefresh size={12} />
          </ActionIcon>
        </Tooltip>
      </Group>
    );
  }
  return <Text fz={10} c="dimmed">auto{p.cours_maj_le ? ' · ' + dateHeure(p.cours_maj_le) : ''}</Text>;
}

function Repartitions({ liste }: { liste: Position[] }) {
  const parSecteurMap: Record<string, number> = {};
  liste.forEach(p => {
    const s = p.secteur || 'Non classé';
    parSecteurMap[s] = (parSecteurMap[s] || 0) + p.valeur_marche;
  });
  return (
    <Grille2>
      <Carte titre="Répartition par titre">
        {liste.length ? <Donut {...regrouperAutres(liste.map(p => p.titre), liste.map(p => p.valeur_marche))} /> : <Vide>Aucune position</Vide>}
      </Carte>
      <Carte titre="Répartition par secteur">
        {liste.length ? <Donut {...regrouperAutres(Object.keys(parSecteurMap), Object.values(parSecteurMap))} /> : <Vide>Aucune position</Vide>}
      </Carte>
    </Grille2>
  );
}

/* ---------- Allocation par secteur : poids actuel comparé à une cible ---------- */
function Allocation({ liste }: { liste: Position[] }) {
  const { data: cibles } = useCibles();
  const ecrire = useEcriture('bourse');
  const [saisies, setSaisies] = useState<Record<string, string | number>>({});
  useEffect(() => {
    if (cibles) setSaisies(Object.fromEntries(cibles.map(c => [c.secteur, Math.round(c.cible * 10000) / 100])));
  }, [cibles]);

  const valeurs: Record<string, number> = {};
  liste.forEach(p => { valeurs[p.secteur || 'Non classé'] = (valeurs[p.secteur || 'Non classé'] ?? 0) + p.valeur_marche; });
  const total = Object.values(valeurs).reduce((a, b) => a + b, 0);
  const secteurs = [...new Set([...Object.keys(valeurs), ...(cibles ?? []).map(c => c.secteur)])]
    .sort((a, b) => (valeurs[b] ?? 0) - (valeurs[a] ?? 0));
  const pct = (s: string) => { const v = saisies[s]; return typeof v === 'number' ? v : parseFloat(v ?? '') || 0; };
  const sommeCibles = secteurs.reduce((a, s) => a + pct(s), 0);
  const modifie = secteurs.some(s => pct(s) !== Math.round((cibles?.find(c => c.secteur === s)?.cible ?? 0) * 10000) / 100);

  if (!secteurs.length) return null;
  return (
    <Carte titre="Allocation par secteur" description="Poids actuel (valeur de marché) comparé à ta cible ; le dernier chiffre indique combien acheter (+) ou alléger (−) pour l'atteindre"
           droite={<Button size="xs" variant={modifie ? 'filled' : 'default'} loading={ecrire.isPending} disabled={sommeCibles > 100.001}
                           onClick={() => ecrire.mutate({ path: '/api/bourse/cibles', method: 'PUT', succes: 'Cibles enregistrées ✓',
                             body: { cibles: secteurs.filter(s => pct(s) > 0).map(s => ({ secteur: s, cible: pct(s) / 100 })) } })}>
                     Enregistrer les cibles
                   </Button>}>
      <Tableau minWidth={640}>
        <Table.Thead>
          <Table.Tr>
            <Table.Th>Secteur</Table.Th><Table.Th className="num">Valeur</Table.Th><Table.Th className="num">Poids</Table.Th>
            <Table.Th className="num">Cible</Table.Th><Table.Th className="num">Écart</Table.Th><Table.Th className="num">Pour atteindre la cible</Table.Th>
          </Table.Tr>
        </Table.Thead>
        <Table.Tbody>
          {secteurs.map(s => {
            const valeur = valeurs[s] ?? 0;
            const poids = total ? valeur / total * 100 : 0;
            const cible = pct(s);
            const ecart = poids - cible;
            const aInvestir = cible / 100 * total - valeur;
            return (
              <Table.Tr key={s}>
                <Table.Td fw={600}>{s}</Table.Td>
                <Table.Td className="num chiffre">{fmt(valeur)}</Table.Td>
                <Table.Td className="num chiffre">{poids.toFixed(1)} %</Table.Td>
                <Table.Td className="num">
                  <NumberInput size="xs" w={90} ml="auto" min={0} max={100} decimalScale={2} suffix=" %" value={saisies[s] ?? ''}
                               onChange={v => setSaisies(x => ({ ...x, [s]: v }))} aria-label={`Cible ${s}`} />
                </Table.Td>
                <Table.Td className="num chiffre" c={cible ? (Math.abs(ecart) < 2 ? T.ep : T.warn) : 'dimmed'}>
                  {cible ? (ecart >= 0 ? '+' : '') + ecart.toFixed(1) + ' pts' : '—'}
                </Table.Td>
                <Table.Td className="num chiffre" c={cible ? signe(aInvestir) : 'dimmed'}>
                  {cible ? (aInvestir >= 0 ? '+' : '') + fmt(Math.round(aInvestir)) : '—'}
                </Table.Td>
              </Table.Tr>
            );
          })}
        </Table.Tbody>
      </Tableau>
      <Text fz="xs" c={sommeCibles > 100.001 ? T.neg : 'dimmed'} mt="xs">
        Total des cibles : {sommeCibles.toLocaleString('fr-FR', { maximumFractionDigits: 2 })} %
        {sommeCibles > 100.001 ? ' — dépasse 100 %' : sommeCibles < 100 && sommeCibles > 0 ? ' (le reste : sans cible, ou en espèces)' : ''}
      </Text>
    </Carte>
  );
}

export function Positions() {
  const { data, isPending } = usePositions();
  const liste = (data ?? []).filter(p => p.quantite_detenue > 0);
  type Cle = 'titre' | 'secteur' | 'valeur' | 'pv' | 'perf' | 'rdt';
  const { triees, tri, basculer } = useTri<Position, Cle>(liste, (p, c) =>
    c === 'titre' ? p.titre : c === 'secteur' ? p.secteur : c === 'valeur' ? p.valeur_marche : c === 'pv' ? p.plus_value_latente
      : c === 'rdt' ? p.rendement_cout : p.performance_latente,
    { cle: 'valeur', desc: true });
  const th = { tri, basculer };
  const actualiser = useActualiserCours();

  return (
    <>
      <Repartitions liste={liste} />
      <Carte titre="Portefeuille actuel"
             description="Cours récupérés automatiquement. Un cours saisi à la main (Entrée pour valider) reste verrouillé jusqu'à sa remise en automatique."
             droite={<Button variant="default" size="xs" leftSection={<IconRefresh size={14} />} loading={actualiser.isPending}
                             onClick={() => actualiser.mutate(null)}>Actualiser les cours</Button>}>
        {isPending ? <Chargement /> : !liste.length ? <Vide>Aucune position ouverte pour le moment.</Vide> : (
          <Tableau minWidth={900}>
            <Table.Thead>
              <Table.Tr>
                <ThTri cle="titre" {...th}>Titre</ThTri><ThTri cle="secteur" {...th}>Secteur</ThTri>
                <Table.Th className="num">Qté détenue</Table.Th><Table.Th className="num">PRU</Table.Th>
                <Table.Th className="num">Cours actuel</Table.Th><ThTri cle="valeur" num {...th}>Valeur marché</ThTri>
                <ThTri cle="pv" num {...th}>+/- value latente</ThTri><ThTri cle="perf" num {...th}>Perf.</ThTri>
                <ThTri cle="rdt" num {...th}>
                  <Tooltip label="Dividendes des 12 derniers mois ramenés aux actions détenues aujourd'hui, ÷ coût de la position (÷ valeur de marché dessous)" multiline w={260}>
                    <span>Rdt div.</span>
                  </Tooltip>
                </ThTri>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {triees.map(p => (
                <Table.Tr key={p.titre}>
                  <Table.Td fw={600}>{p.titre}</Table.Td>
                  <Table.Td c="dimmed" fz="xs">{p.secteur}</Table.Td>
                  <Table.Td className="num chiffre">{p.quantite_detenue}</Table.Td>
                  <Table.Td className="num chiffre">{fmt(p.pru)}</Table.Td>
                  <Table.Td>
                    <Stack gap={2} align="flex-end">
                      <CoursEditable key={p.cours_actuel} titre={p.titre} cours={p.cours_actuel} />
                      <SourceCours p={p} />
                    </Stack>
                  </Table.Td>
                  <Table.Td className="num chiffre">{fmt(p.valeur_marche)}</Table.Td>
                  <Table.Td className="num chiffre" c={signe(p.plus_value_latente)} fw={600}>{fmt(p.plus_value_latente)}</Table.Td>
                  <Table.Td className="num chiffre" c={signe(p.performance_latente)}>{pctFr(p.performance_latente)}</Table.Td>
                  <Table.Td className="num chiffre">
                    {p.dividendes_12m ? (
                      <Tooltip label={`${fmt(p.dividendes_12m)} par an sur tes ${p.quantite_detenue} actions (dividendes des 12 derniers mois)`} withArrow>
                        <Stack gap={0} align="flex-end">
                          <span>{pctFr(p.rendement_cout)}</span>
                          <Text fz={10} c="dimmed">{pctFr(p.rendement_marche)} au cours</Text>
                        </Stack>
                      </Tooltip>
                    ) : <Text c="dimmed" span>—</Text>}
                  </Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Tableau>
        )}
      </Carte>
      <Allocation liste={liste} />
    </>
  );
}

/* ================= Gains réalisés ================= */
export function Gains() {
  const { data, isPending } = useGains();
  type Cle = 'date' | 'titre' | 'brut' | 'net';
  const { triees, tri, basculer } = useTri<NonNullable<typeof data>[number], Cle>(data, (g, c) =>
    c === 'date' ? g.date_operation : c === 'titre' ? g.titre : c === 'brut' ? g.gain_brut : g.gain_net,
    { cle: 'date', desc: true });
  const th = { tri, basculer };

  return (
    <Carte titre="Gains réalisés & TPCVM" description="PRU en coût moyen pondéré, TPCVM saisie sur chaque vente">
      {isPending ? <Chargement /> : !data?.length ? <Vide>Aucune vente enregistrée pour le moment.</Vide> : (
        <Tableau minWidth={640}>
          <Table.Thead>
            <Table.Tr>
              <ThTri cle="date" {...th}>Date</ThTri><ThTri cle="titre" {...th}>Titre</ThTri><Table.Th>Instrument</Table.Th>
              <Table.Th className="num">Qté</Table.Th><ThTri cle="brut" num {...th}>Gain brut</ThTri>
              <Table.Th className="num">TPCVM</Table.Th><ThTri cle="net" num {...th}>Gain net</ThTri>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {triees.map(g => (
              <Table.Tr key={g.id}>
                <Table.Td c="dimmed" style={{ whiteSpace: 'nowrap' }}>{jjmm(g.date_operation)}</Table.Td>
                <Table.Td fw={600}>{g.titre}</Table.Td>
                <Table.Td c="dimmed" fz="xs">{g.type_instrument}</Table.Td>
                <Table.Td className="num chiffre">{g.quantite}</Table.Td>
                <Table.Td className="num chiffre">{fmt(g.gain_brut)}</Table.Td>
                <Table.Td className="num chiffre">{fmt(g.tpcvm)}</Table.Td>
                <Table.Td className="num chiffre" c={signe(g.gain_net)} fw={600}>{fmt(g.gain_net)}</Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Tableau>
      )}
    </Carte>
  );
}

/* ================= Tableau de bord ================= */
export function DashboardBourse({ nav }: { nav: NavBourse }) {
  const requete = nav.periode === 'global' ? '' : nav.periode === 'annee' ? 'annee=' + nav.annee : 'mois=' + nav.mois;
  const { data: d } = useDashboardBourse(requete);
  const libelle = nav.periode === 'global' ? 'Tout l’historique' : nav.periode === 'annee' ? 'Année ' + nav.annee : libelleMois(nav.mois);
  const fleches = nav.periode !== 'global';

  function naviguer(delta: number) {
    if (nav.periode === 'annee') nav.setAnnee(a => a + delta);
    else if (nav.periode === 'mois') nav.setMois(m => decalerMois(m, delta));
  }

  return (
    <>
      <Group justify="space-between" align="center" gap="sm" wrap="wrap">
        <Box>
          <Title order={2} fz={18}>{libelle}</Title>
          <Text c="dimmed" fz="xs" mt={2}>Résultat de la période et état actuel du compte</Text>
        </Box>
        <Group gap="xs" wrap="wrap">
          {fleches && (
            <Group gap={4} wrap="nowrap">
              <ActionIcon variant="default" size={36} radius="md" aria-label="Période précédente" onClick={() => naviguer(-1)}>
                <IconChevronLeft size={18} />
              </ActionIcon>
              <ActionIcon variant="default" size={36} radius="md" aria-label="Période suivante" onClick={() => naviguer(1)}>
                <IconChevronRight size={18} />
              </ActionIcon>
            </Group>
          )}
          <SegmentedControl value={nav.periode} onChange={v => nav.setPeriode(v as PeriodeBourse)}
            data={[{ value: 'global', label: 'Global' }, { value: 'mois', label: 'Mois' }, { value: 'annee', label: 'Année' }]} />
        </Group>
      </Group>

      {!d ? <Chargement lignes={6} /> : (
        <>
          <TitreSection>Compte Bourse</TitreSection>
          <GrilleKpi>
            <Kpi label="Patrimoine Bourse" icone={IconBuildingBank} teinte="bleu" valeur={fmt(d.patrimoine_total)} couleur={T.rev} aide="titres + espèces disponibles" />
            <Kpi label="Espèces disponibles" icone={IconCash} teinte="gray" valeur={fmt(d.especes_disponibles)} couleur={d.especes_disponibles >= 0 ? undefined : T.neg}
                 aide={d.especes_disponibles < 0 ? 'négatif : un apport n’a sans doute pas été saisi' : 'non investi, prêt à réinvestir'} />
            <Kpi label="Apports nets" icone={IconArrowsExchange} teinte="gray" valeur={fmt(d.apports_nets)} aide="argent sorti de ta banque (apports − retraits)" />
            <Kpi label="Performance globale" icone={IconTrendingUp} teinte="emeraude" couleur={signe(d.performance_globale)}
                 valeur={(d.performance_globale >= 0 ? '+' : '') + fmt(d.performance_globale)}
                 aide={d.apports_nets <= 0 ? 'saisis tes apports pour la calculer' : (
                   <>
                     {pctFr(d.performance_globale_pct)} des apports nets
                     {d.rendement_annualise !== null && (
                       <Tooltip multiline w={280} withArrow
                                label="Rendement annuel tenant compte de la date de chaque apport et retrait (TRI). Comparable à un livret ou au MASI ; un apport récent ne le fait pas baisser.">
                         <span style={{ display: 'block', textDecoration: 'underline dotted', textUnderlineOffset: 3 }}>
                           soit <b style={{ color: signe(d.rendement_annualise) }}>{(d.rendement_annualise >= 0 ? '+' : '') + pctFr(d.rendement_annualise)}</b> par an
                         </span>
                       </Tooltip>
                     )}
                   </>
                 )} />
          </GrilleKpi>

          <TitreSection>Portefeuille actuel</TitreSection>
          <GrilleKpi>
            <Kpi label="Valeur de marché" icone={IconChartDonut} teinte="bleu" valeur={fmt(d.valeur_marche)} couleur={T.rev} aide={`coût d'acquisition : ${fmt(d.cout_acquisition)}`} />
            <Kpi label="Plus/moins-value latente" icone={IconChartLine} teinte="emeraude" valeur={fmt(d.plus_value_latente)} couleur={signe(d.plus_value_latente)}
                 aide={pctFr(d.performance_latente)} />
          </GrilleKpi>

          <TitreSection>Résultat — {libelle}</TitreSection>
          <GrilleKpi>
            <Kpi label="Gains nets réalisés" icone={IconReportMoney} teinte="emeraude" valeur={fmt(d.gains_nets_realises)} couleur={signe(d.gains_nets_realises)}
                 aide={`TPCVM : ${fmt(d.tpcvm_total)}`} />
            <Kpi label="Dividendes nets" icone={IconCoins} teinte="emeraude" valeur={fmt(d.dividendes_nets)} couleur={T.ep} />
            <Kpi label="Frais de transactions" icone={IconReceipt} teinte="rose" valeur={fmt(d.frais_transactions_totaux)} couleur={T.dep}
                 aide="déjà déduits du gain net ci-dessus — pour info" />
            <Kpi label="Frais de compte" icone={IconReceiptTax} teinte="rose" valeur={fmt(d.frais_compte_totaux)} couleur={T.dep} />
            <Kpi label="Résultat net de la période" icone={IconScale} teinte="marque" valeur={fmt(d.resultat_net_periode)} couleur={signe(d.resultat_net_periode)}
                 aide="gains nets + dividendes − frais de compte" />
            <Kpi label="Apports / retraits" icone={IconBuildingBank} teinte="gray" valeur={fmt(d.apports_periode - d.retraits_periode)}
                 aide={`apports : ${fmt(d.apports_periode)} · retraits : ${fmt(d.retraits_periode)}`} />
          </GrilleKpi>
        </>
      )}
    </>
  );
}
