import { useState } from 'react';
import { ScrollArea, Stack, Tabs } from '@mantine/core';
import {
  IconArrowsExchange, IconBuildingBank, IconChartDonut, IconCoins, IconFileInvoice, IconLayoutDashboard, IconReceiptTax, IconReportMoney, IconSettings,
} from '@tabler/icons-react';

import { auj } from '../../lib/format';
import { useCoursAuto } from '../../lib/queries';
import { estAnnee, estMois, parmi } from '../../lib/routes';
import { EnTetePage } from '../../components/ui';
import { JournalDividendes, JournalFrais, JournalMouvements, JournalTransactions } from './Journaux';
import { DashboardBourse, Gains, Positions } from './Portefeuille';
import { Fiscalite } from './Fiscalite';
import { ParametresBourse } from './ParametresBourse';

export type VueBourse = 'transactions' | 'positions' | 'gains' | 'dividendes' | 'frais' | 'mouvements' | 'dashboard' | 'fiscalite' | 'parametres';
export type PeriodeBourse = 'global' | 'mois' | 'annee';
const VUES_BOURSE = ['dashboard', 'transactions', 'positions', 'gains', 'dividendes', 'frais', 'mouvements', 'fiscalite', 'parametres'] as const;
const PERIODES = ['global', 'mois', 'annee'] as const;

/** État de navigation du module Bourse, gardé par App pour survivre aux changements d'onglet.
 *  `initial` : segments de l'URL après « bourse » (ex : ['dashboard', 'annee', '2026'] ou ['fiscalite', '2025']). */
export function useNavBourse(initial: string[] = []) {
  const [vue, setVue] = useState<VueBourse>(parmi(initial[0], VUES_BOURSE, 'transactions'));
  const [periode, setPeriode] = useState<PeriodeBourse>(initial[0] === 'dashboard' ? parmi(initial[1], PERIODES, 'global') : 'global');   // par défaut : tout l'historique
  const [mois, setMois] = useState(estMois(initial[2]) ? initial[2] : auj().slice(0, 7));
  const [annee, setAnnee] = useState(estAnnee(initial[2]) ? +initial[2] : estAnnee(initial[1]) ? +initial[1] : new Date().getFullYear());
  function chemin(): string[] {
    if (vue === 'dashboard') return periode === 'global' ? [vue, periode] : [vue, periode, periode === 'mois' ? mois : String(annee)];
    if (vue === 'fiscalite') return [vue, String(annee)];
    return [vue];
  }
  function appliquer([v, a, b]: string[]) {
    const nv = parmi(v, VUES_BOURSE, 'transactions');
    setVue(nv);
    if (nv === 'dashboard') setPeriode(parmi(a, PERIODES, 'global'));
    if (estMois(b)) setMois(b);
    if (estAnnee(b)) setAnnee(+b);
    if (nv === 'fiscalite' && estAnnee(a)) setAnnee(+a);
  }
  return { vue, setVue, periode, setPeriode, mois, setMois, annee, setAnnee, chemin, appliquer };
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
  { value: 'fiscalite', label: 'Fiscalité', Icone: IconFileInvoice },
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
      {nav.vue === 'fiscalite' && <Fiscalite nav={nav} />}
      {nav.vue === 'parametres' && <ParametresBourse />}
    </Stack>
  );
}
