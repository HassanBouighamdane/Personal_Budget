import { useState, type ReactNode } from 'react';
import { ActionIcon, Group, SegmentedControl, Stack, Title } from '@mantine/core';
import { IconChevronLeft, IconChevronRight } from '@tabler/icons-react';

import { auj, decalerDate, decalerMois } from '../../lib/format';
import { VueAnnee, VueGlobal, VueJour, VueMois, VueSemaine } from './Vues';

export type VueDash = 'jour' | 'semaine' | 'mois' | 'annee' | 'global';

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
  return { vue, setVue, jour, semaine, mois, annee, naviguer };
}
export type NavDashboard = ReturnType<typeof useNavDashboard>;

const VUES = [
  { value: 'jour', label: 'Jour' },
  { value: 'semaine', label: 'Semaine' },
  { value: 'mois', label: 'Mois' },
  { value: 'annee', label: 'Année' },
  { value: 'global', label: 'Global' },
];

/** Barre ‹ titre › + choix de la vue ; les flèches sont masquées en vue globale */
export function EnTetePeriode({ nav, titre }: { nav: NavDashboard; titre: ReactNode }) {
  const fleches = nav.vue !== 'global';
  return (
    <Group justify="space-between" gap="sm" wrap="wrap">
      <Group gap="xs" wrap="nowrap">
        <ActionIcon variant="default" size="lg" radius="md" aria-label="Période précédente"
                    style={{ visibility: fleches ? undefined : 'hidden' }} onClick={() => nav.naviguer(-1)}>
          <IconChevronLeft size={18} />
        </ActionIcon>
        <Title order={2} fz={{ base: 17, sm: 20 }} miw={{ sm: 260 }} ta="center">{titre}</Title>
        <ActionIcon variant="default" size="lg" radius="md" aria-label="Période suivante"
                    style={{ visibility: fleches ? undefined : 'hidden' }} onClick={() => nav.naviguer(1)}>
          <IconChevronRight size={18} />
        </ActionIcon>
      </Group>
      <SegmentedControl data={VUES} value={nav.vue} onChange={v => nav.setVue(v as VueDash)} radius="md" />
    </Group>
  );
}

export function Dashboard({ nav }: { nav: NavDashboard }) {
  return (
    <Stack gap="md">
      {nav.vue === 'jour' && <VueJour nav={nav} />}
      {nav.vue === 'semaine' && <VueSemaine nav={nav} />}
      {nav.vue === 'mois' && <VueMois nav={nav} />}
      {nav.vue === 'annee' && <VueAnnee nav={nav} />}
      {nav.vue === 'global' && <VueGlobal nav={nav} />}
    </Stack>
  );
}
