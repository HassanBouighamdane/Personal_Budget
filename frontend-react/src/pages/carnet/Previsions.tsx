/* Suivi → Patrimoine — prévisions de trésorerie : les liquidités fin de mois, du mois en cours aux prochains, à partir des
 * récurrences, des moyennes passées, des échéances et des emprunts à rembourser. Les objectifs ne sortent pas d'argent :
 * ils en réservent (« libres » = liquidités − réservé). La zone autour de la courbe donne l'incertitude. */
import { useState } from 'react';
import { Alert, Badge, Box, Button, Collapse, Group, SegmentedControl, Stack, Table, Text, UnstyledButton } from '@mantine/core';
import { IconAlertTriangle, IconChevronDown, IconChevronRight, IconTelescope } from '@tabler/icons-react';
import type { ChartData } from 'chart.js';

import { toast } from '../../lib/api';
import { fmt, libelleMois, lireMontant, moisCourt } from '../../lib/format';
import { C, T, signe } from '../../lib/palette';
import type { LignePrevision, MoisPrevision, Previsions } from '../../lib/types';
import { useEcriture, usePrevisions } from '../../lib/queries';
import { Graphique, optionsSeries } from '../../components/Graphique';
import { ChampMontant } from '../../components/champs';
import { Carte, Chargement, Info, Pastille, Tableau } from '../../components/ui';

const HORIZONS = [{ value: '3', label: '3 mois' }, { value: '6', label: '6 mois' }, { value: '12', label: '1 an' }];
const BASES: Record<LignePrevision['base'], string> = {
  recurrence: 'récurrence', budget: 'budget fixe', moyenne: 'moyenne', saisi: 'déjà saisi',
};

function Courbe({ p }: { p: Previsions }) {
  const labels = ["Aujourd'hui", ...p.mois.map((m, i) => (i === 0 ? 'fin ' : '') + moisCourt(m.mois))];
  const aReserve = p.mois.some(m => m.reserve > 0);
  const avecDepart = (v: (m: MoisPrevision) => number) => [p.depart, ...p.mois.map(v)];
  const base = optionsSeries();
  return (
    <Graphique type="line" hauteur={240} options={{
      ...base,
      plugins: {
        legend: { position: 'top', align: 'end', labels: { filter: item => !item.text.startsWith('_') } },
        tooltip: { filter: item => !String(item.dataset.label).startsWith('_'),
                   callbacks: { label: ctx => `${ctx.dataset.label} : ${fmt(ctx.parsed.y ?? 0)}` } },
      },
    }} data={{
      labels,
      datasets: [
        // Fourchette : la courbe haute remplie jusqu'à la basse (préfixe « _ » : hors légende et infobulle)
        { label: '_haut', data: avecDepart(m => m.haut), borderWidth: 0, pointRadius: 0, fill: '+1', backgroundColor: 'rgba(16,185,129,.10)' },
        { label: '_bas', data: avecDepart(m => m.bas), borderWidth: 0, pointRadius: 0, fill: false },
        { label: 'Liquidités prévues', data: avecDepart(m => m.solde), borderColor: C.ep, backgroundColor: C.ep, tension: .25, pointRadius: 3 },
        ...(aReserve ? [{ label: 'dont libres', data: avecDepart(m => m.libre), borderColor: C.rev, backgroundColor: C.rev,
                          borderDash: [6, 4], borderWidth: 1.5, tension: .25, pointRadius: 0 }] : []),
        ...(p.plancher > 0 ? [{ label: 'Plancher', data: labels.map(() => p.plancher), borderColor: C.dep, borderWidth: 1,
                                borderDash: [3, 3], pointRadius: 0 }] : []),
      ],
    } as ChartData} />
  );
}

function Lignes({ titre, lignes }: { titre: string; lignes: { nom: string; montant: number; note?: string }[] }) {
  if (!lignes.length) return null;
  return (
    <Box>
      <Text fz="xs" fw={600} c="dimmed" mb={2}>{titre}</Text>
      {lignes.map((l, i) => (
        <Group key={l.nom + i} justify="space-between" gap="xs" wrap="nowrap">
          <Text fz="xs" truncate>{l.nom || 'Sans source'}{l.note ? <Text span inherit c="dimmed"> · {l.note}</Text> : null}</Text>
          <Text fz="xs" className="chiffre" style={{ whiteSpace: 'nowrap' }}>{fmt(l.montant)}</Text>
        </Group>
      ))}
    </Box>
  );
}

function Detail({ m }: { m: MoisPrevision }) {
  return (
    <Stack gap={8} py={6}>
      <Lignes titre="Entrées" lignes={m.detail.revenus.map(l => ({ ...l, note: BASES[l.base] }))} />
      <Lignes titre="Dépenses" lignes={m.detail.depenses.map(l => ({ ...l, note: BASES[l.base] }))} />
      <Lignes titre="Échéances" lignes={m.detail.echeances.map(e => ({ nom: e.titre, montant: e.montant, note: e.date.slice(8) + '/' + e.date.slice(5, 7) }))} />
      <Lignes titre="Remboursements" lignes={m.detail.dettes.map(d => ({ nom: d.personne, montant: d.montant, note: d.en_retard ? 'en retard' : undefined }))} />
      {m.reserve > 0 && <Text fz="xs" c="dimmed">Réservé aux objectifs fin {libelleMois(m.mois).toLowerCase()} : {fmt(m.reserve)}, libres : {fmt(m.libre)}</Text>}
    </Stack>
  );
}

function TableMois({ p }: { p: Previsions }) {
  const [ouvert, setOuvert] = useState<string | null>(null);
  return (
    <Tableau minWidth={420}>
      <Table.Thead>
        <Table.Tr>
          <Table.Th>Mois</Table.Th><Table.Th className="num">Entrées</Table.Th><Table.Th className="num">Sorties</Table.Th>
          <Table.Th className="num">Fin de mois</Table.Th>
        </Table.Tr>
      </Table.Thead>
      <Table.Tbody>
        {p.mois.map((m, i) => {
          const sorties = m.depenses + m.echeances + m.dettes;
          const Chevron = ouvert === m.mois ? IconChevronDown : IconChevronRight;
          const bas = m.mois === p.point_bas.mois;
          return [
            <Table.Tr key={m.mois} style={{ cursor: 'pointer' }} onClick={() => setOuvert(o => o === m.mois ? null : m.mois)}>
              <Table.Td>
                <UnstyledButton style={{ font: 'inherit', color: 'inherit' }} aria-expanded={ouvert === m.mois}>
                  <Group gap={4} wrap="nowrap">
                    <Chevron size={14} />
                    <Text fz="sm" span>{libelleMois(m.mois)}</Text>
                    {i === 0 && <Text fz="xs" c="dimmed" span>(reste du mois)</Text>}
                    {bas && <Badge size="xs" variant="light" color={m.solde < p.plancher ? 'rouge' : 'gray'} tt="none">point bas</Badge>}
                  </Group>
                </UnstyledButton>
              </Table.Td>
              <Table.Td className="num chiffre" c={T.rev}>+{fmt(m.revenus)}</Table.Td>
              <Table.Td className="num chiffre" c={T.dep}>−{fmt(sorties)}</Table.Td>
              <Table.Td className="num chiffre" fw={600} c={m.solde < p.plancher ? T.neg : signe(m.solde)}>{fmt(m.solde)}</Table.Td>
            </Table.Tr>,
            <Table.Tr key={m.mois + '-detail'} style={{ display: ouvert === m.mois ? undefined : 'none' }}>
              <Table.Td colSpan={4}><Collapse expanded={ouvert === m.mois}><Detail m={m} /></Collapse></Table.Td>
            </Table.Tr>,
          ];
        })}
      </Table.Tbody>
    </Tableau>
  );
}

function Plancher({ p }: { p: Previsions }) {
  const ecrire = useEcriture('patrimoine');
  const [valeur, setValeur] = useState(p.plancher ? String(p.plancher).replace('.', ',') : '');
  function enregistrer() {
    const v = valeur.trim() ? lireMontant(valeur) : 0;
    if (isNaN(v) || v < 0) return toast('Montant invalide', false);
    ecrire.mutate({ path: '/api/previsions/reglages', method: 'PUT', body: { plancher: v }, succes: 'Plancher enregistré ✓' });
  }
  return (
    <Group gap="xs" align="flex-end" wrap="wrap">
      <ChampMontant size="xs" w={150} label="Plancher" placeholder="0" value={valeur} onChange={setValeur}
                    description="Prévenir sous ce montant" />
      <Button size="xs" variant="light" onClick={enregistrer} loading={ecrire.isPending}>Enregistrer</Button>
    </Group>
  );
}

export function CartePrevisions() {
  const [horizon, setHorizon] = useState('6');
  const { data: p, isPending } = usePrevisions(Number(horizon));
  const choix = <SegmentedControl size="xs" value={horizon} onChange={setHorizon} data={HORIZONS} />;
  return (
    <Carte titre="Prévisions" icone={<Pastille icone={IconTelescope} couleur="bleu" />} droite={choix}
           description={p ? <>Point bas : <Text span inherit fw={600} c={p.point_bas.solde < p.plancher ? T.neg : undefined}>{fmt(p.point_bas.solde)}</Text> fin {libelleMois(p.point_bas.mois).toLowerCase()}</>
             : 'Tes liquidités fin de mois, à partir de tes habitudes'}>
      {isPending || !p ? <Chargement lignes={3} /> : (
        <Stack gap="md">
          {p.alertes.map(a => (
            <Alert key={a.type} variant="light" color={a.type === 'plancher' ? 'rouge' : 'ambre'} radius="md" p="xs"
                   icon={<IconAlertTriangle size={16} />} title={<Text fz="sm" fw={600}>{a.titre}</Text>}>
              <Text fz="xs">{a.detail}</Text>
            </Alert>
          ))}
          <Courbe p={p} />
          <TableMois p={p} />
          <Group justify="space-between" align="flex-end" gap="sm" wrap="wrap">
            <Info>
              <Text span fz="xs" inherit>
                {p.nb_mois_historique ? `Moyennes sur tes ${p.nb_mois_historique} derniers mois terminés` : 'Pas encore de mois terminé : seulement tes récurrences et budgets fixes'}
                {p.rythme_objectifs > 0 ? ` · objectifs : ${fmt(p.rythme_objectifs)} par mois à réserver` : ''}
                {` · épargne prévue : ${fmt(p.epargne_prevue)} par mois.`} La zone verte donne la marge d'erreur.
              </Text>
            </Info>
            <Plancher key={p.plancher} p={p} />
          </Group>
        </Stack>
      )}
    </Carte>
  );
}
