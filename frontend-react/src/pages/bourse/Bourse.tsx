import { useState } from 'react';
import { ScrollArea, Stack, Tabs } from '@mantine/core';
import {
  IconArrowsExchange, IconBuildingBank, IconChartDonut, IconCoins, IconLayoutDashboard, IconReceiptTax, IconReportMoney, IconSettings,
} from '@tabler/icons-react';

import { auj } from '../../lib/format';
import { useCoursAuto } from '../../lib/queries';
import { EnTetePage } from '../../components/ui';
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

const VUES: { value: VueBourse; label: string; Icone: typeof IconCoins }[] = [
  { value: 'dashboard', label: 'Dashboard', Icone: IconLayoutDashboard },
  { value: 'transactions', label: 'Transactions', Icone: IconArrowsExchange },
  { value: 'positions', label: 'Positions', Icone: IconChartDonut },
  { value: 'gains', label: 'Gains', Icone: IconReportMoney },
  { value: 'dividendes', label: 'Dividendes', Icone: IconCoins },
  { value: 'frais', label: 'Frais', Icone: IconReceiptTax },
  { value: 'mouvements', label: 'Apports / Retraits', Icone: IconBuildingBank },
  { value: 'parametres', label: 'Paramètres', Icone: IconSettings },
];

export function Bourse({ nav }: { nav: NavBourse }) {
  useCoursAuto();
  return (
    <Stack gap="lg">
      <Stack gap="sm">
        <EnTetePage titre="Bourse" description="Portefeuille à la Bourse de Casablanca" />
        <ScrollArea type="never" offsetScrollbars={false}>
          <Tabs value={nav.vue} onChange={v => v && nav.setVue(v as VueBourse)} variant="default" color="marque">
            <Tabs.List style={{ flexWrap: 'nowrap' }}>
              {VUES.map(({ value, label, Icone }) => (
                <Tabs.Tab key={value} value={value} leftSection={<Icone size={16} stroke={1.7} />} fw={500} fz={13.5}
                          px={12} style={{ whiteSpace: 'nowrap' }}>
                  {label}
                </Tabs.Tab>
              ))}
            </Tabs.List>
          </Tabs>
        </ScrollArea>
      </Stack>
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
