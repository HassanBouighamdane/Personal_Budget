import { useState, type ReactNode } from 'react';
import { ActionIcon, Button, Group, SegmentedControl, Stack, Tooltip } from '@mantine/core';
import { IconChevronLeft, IconChevronRight } from '@tabler/icons-react';

import { auj, decalerDate, decalerMois } from '../../lib/format';
import { useCoursAuto } from '../../lib/queries';
import { EnTetePage } from '../../components/ui';
import { VueAnnee, VueGlobal, VueJour, VueMois, VueSemaine } from './Vues';

export type VueDash = 'jour' | 'semaine' | 'mois' | 'annee' | 'global';

const lundiDe = (d: string) => {
  const [a, m, j] = d.split('-').map(Number);
  return decalerDate(d, -((new Date(a, m - 1, j).getDay() + 6) % 7));
};

/** État de navigation du dashboard, gardé par App pour survivre aux changements d'onglet */
export function useNavDashboard() {
  const [vue, setVue] = useState<VueDash>('mois');
  const [jour, setJour] = useState(auj());
  const [semaine, setSemaine] = useState(auj());   // n'importe quel jour de la semaine affichée
  const [mois, setMois] = useState(auj().slice(0, 7));
  const [annee, setAnnee] = useState(new Date().getFullYear());

  function naviguer(delta: number) {
    if (vue === 'annee') setAnnee(a => a + delta);
    else if (vue === 'mois') setMois(m => decalerMois(m, delta));
    else if (vue === 'semaine') setSemaine(s => decalerDate(s, delta * 7));
    else if (vue === 'jour') setJour(j => decalerDate(j, delta));
  }
  function aujourdhui() {
    setJour(auj()); setSemaine(auj()); setMois(auj().slice(0, 7)); setAnnee(new Date().getFullYear());
  }
  const surPeriodeCourante = vue === 'global'
    || (vue === 'jour' && jour === auj()) || (vue === 'mois' && mois === auj().slice(0, 7))
    || (vue === 'annee' && annee === new Date().getFullYear())
    || (vue === 'semaine' && lundiDe(semaine) === lundiDe(auj()));
  return { vue, setVue, jour, semaine, mois, annee, naviguer, aujourdhui, surPeriodeCourante };
}
export type NavDashboard = ReturnType<typeof useNavDashboard>;

const VUES = [
  { value: 'jour', label: 'Jour' },
  { value: 'semaine', label: 'Semaine' },
  { value: 'mois', label: 'Mois' },
  { value: 'annee', label: 'Année' },
  { value: 'global', label: 'Global' },
];

const DESCRIPTIONS: Record<VueDash, string> = {
  jour: 'Vue journalière',
  semaine: 'Vue hebdomadaire',
  mois: 'Vue mensuelle — budget, épargne et tendances',
  annee: 'Vue annuelle — bilan mois par mois',
  global: "Vue globale — tout l'historique",
};

/** En-tête : période affichée, navigation ‹ › (masquée en vue globale) et choix de la vue */
export function EnTetePeriode({ nav, titre }: { nav: NavDashboard; titre: ReactNode }) {
  const fleches = nav.vue !== 'global';
  return (
    <EnTetePage titre={titre} description={DESCRIPTIONS[nav.vue]} actions={
      <Group gap="xs" wrap="wrap">
        <Group gap={4} wrap="nowrap" style={{ visibility: fleches ? undefined : 'hidden' }}>
          <Tooltip label="Période précédente">
            <ActionIcon variant="default" size={36} radius="md" aria-label="Période précédente" onClick={() => nav.naviguer(-1)}>
              <IconChevronLeft size={18} />
            </ActionIcon>
          </Tooltip>
          <Button variant="default" h={36} px="sm" fw={600} disabled={nav.surPeriodeCourante} onClick={nav.aujourdhui}>
            Aujourd'hui
          </Button>
          <Tooltip label="Période suivante">
            <ActionIcon variant="default" size={36} radius="md" aria-label="Période suivante" onClick={() => nav.naviguer(1)}>
              <IconChevronRight size={18} />
            </ActionIcon>
          </Tooltip>
        </Group>
        <SegmentedControl data={VUES} value={nav.vue} onChange={v => nav.setVue(v as VueDash)} />
      </Group>
    } />
  );
}

export function Dashboard({ nav }: { nav: NavDashboard }) {
  useCoursAuto();   // le patrimoine net de la vue globale dépend des cours du jour
  return (
    <Stack gap="lg">
      {nav.vue === 'jour' && <VueJour nav={nav} />}
      {nav.vue === 'semaine' && <VueSemaine nav={nav} />}
      {nav.vue === 'mois' && <VueMois nav={nav} />}
      {nav.vue === 'annee' && <VueAnnee nav={nav} />}
      {nav.vue === 'global' && <VueGlobal nav={nav} />}
    </Stack>
  );
}
