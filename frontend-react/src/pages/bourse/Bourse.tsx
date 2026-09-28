import { useState } from 'react';
import { Group, ScrollArea, SegmentedControl, Stack, Title } from '@mantine/core';

import { auj } from '../../lib/format';
import { JournalDividendes, JournalFrais, JournalMouvements, JournalTransactions } from './Journaux';
import { DashboardBourse, Gains, Positions } from './Portefeuille';
import { ParametresBourse } from './ParametresBourse';

export type VueBourse = 'transactions' | 'positions' | 'gains' | 'dividendes' | 'frais' | 'mouvements' | 'dashboard' | 'parametres';
export type PeriodeBourse = 'global' | 'mois' | 'annee';

/** État de navigation du module Bourse, gardé par App pour survivre aux changements d'onglet */
export function useNavBourse() {
  const [vue, setVue] = useState<VueBourse>('transactions');
  const [periode, setPeriode] = useState<PeriodeBourse>('global');   // par défaut : tout l'historique
  const [mois, setMois] = useState(auj().slice(0, 7));
  const [annee, setAnnee] = useState(new Date().getFullYear());
  return { vue, setVue, periode, setPeriode, mois, setMois, annee, setAnnee };
}
export type NavBourse = ReturnType<typeof useNavBourse>;

const VUES: { value: VueBourse; label: string }[] = [
  { value: 'transactions', label: 'Transactions' },
  { value: 'positions', label: 'Positions' },
  { value: 'gains', label: 'Gains' },
  { value: 'dividendes', label: 'Dividendes' },
  { value: 'frais', label: 'Frais' },
  { value: 'mouvements', label: 'Apports / Retraits' },
  { value: 'dashboard', label: 'Dashboard' },
  { value: 'parametres', label: 'Paramètres' },
];

export function Bourse({ nav }: { nav: NavBourse }) {
  return (
    <Stack gap="md">
      <Group justify="space-between" gap="sm" wrap="wrap">
        <Title order={2} fz={20}>📈 Bourse</Title>
        <ScrollArea type="never" maw="100%">
          <SegmentedControl data={VUES} value={nav.vue} onChange={v => nav.setVue(v as VueBourse)} radius="md" />
        </ScrollArea>
      </Group>
      {nav.vue === 'transactions' && <JournalTransactions />}
      {nav.vue === 'positions' && <Positions />}
      {nav.vue === 'gains' && <Gains />}
      {nav.vue === 'dividendes' && <JournalDividendes />}
      {nav.vue === 'frais' && <JournalFrais />}
      {nav.vue === 'mouvements' && <JournalMouvements />}
      {nav.vue === 'dashboard' && <DashboardBourse nav={nav} />}
      {nav.vue === 'parametres' && <ParametresBourse />}
    </Stack>
  );
}
