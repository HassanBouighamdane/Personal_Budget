import { useState } from 'react';
import { ActionIcon, Button, Group, ScrollArea, Stack, Tabs, Text, Tooltip } from '@mantine/core';
import { IconBook2, IconBookmark, IconChartBar, IconChevronLeft, IconChevronRight, IconSettings, IconUserShare } from '@tabler/icons-react';

import { estAnnee, parmi } from '../../lib/routes';
import { EnTetePage } from '../../components/ui';
import { JournalLivres } from './Journal';
import { ListeALire } from './ALire';
import { BilanLecture } from './Bilan';
import { ParametresLectures } from './ParametresLectures';
import { LivresPretes } from './Prets';
import { NoteDuJour } from './communs';

export type VueLectures = 'bilan' | 'journal' | 'a_lire' | 'prets' | 'parametres';
const VUES_LECTURES = ['journal', 'a_lire', 'prets', 'bilan', 'parametres'] as const;
// L'année ne concerne que le journal et le bilan
const AVEC_ANNEE: VueLectures[] = ['journal', 'bilan'];

/** État de navigation du module Lectures, gardé par App pour survivre aux changements d'onglet.
 *  `initial` : segments de l'URL après « lectures » (ex : ['bilan', '2025']). */
export function useNavLectures(initial: string[] = []) {
  const [vue, setVue] = useState<VueLectures>(parmi(initial[0], VUES_LECTURES, 'a_lire'));
  const [annee, setAnnee] = useState(estAnnee(initial[1]) ? +initial[1] : new Date().getFullYear());
  const chemin = () => AVEC_ANNEE.includes(vue) ? [vue, String(annee)] : [vue];
  function appliquer([v, a]: string[]) {
    setVue(parmi(v, VUES_LECTURES, 'a_lire'));
    if (estAnnee(a)) setAnnee(+a);
  }
  return { vue, setVue, annee, setAnnee, chemin, appliquer };
}
export type NavLectures = ReturnType<typeof useNavLectures>;

const VUES: { value: VueLectures; label: string; Icone: typeof IconBook2 }[] = [
  { value: 'journal', label: 'Journal', Icone: IconBook2 },
  { value: 'a_lire', label: 'À lire', Icone: IconBookmark },
  { value: 'prets', label: 'Prêtés', Icone: IconUserShare },
  { value: 'bilan', label: 'Bilan annuel', Icone: IconChartBar },
  { value: 'parametres', label: 'Paramètres', Icone: IconSettings },
];

/** Navigation ‹ année › commune au journal et au bilan */
export function NavAnnee({ nav }: { nav: NavLectures }) {
  const courante = new Date().getFullYear();
  return (
    <Group gap={4} wrap="nowrap">
      <Tooltip label="Année précédente">
        <ActionIcon variant="default" size={36} radius="md" aria-label="Année précédente" onClick={() => nav.setAnnee(a => a - 1)}>
          <IconChevronLeft size={18} />
        </ActionIcon>
      </Tooltip>
      <Text fw={700} fz="lg" className="chiffre" w={56} ta="center">{nav.annee}</Text>
      <Tooltip label="Année suivante">
        <ActionIcon variant="default" size={36} radius="md" aria-label="Année suivante" onClick={() => nav.setAnnee(a => a + 1)}>
          <IconChevronRight size={18} />
        </ActionIcon>
      </Tooltip>
      <Button variant="default" h={36} px="sm" fw={600} ml={4} disabled={nav.annee === courante} onClick={() => nav.setAnnee(courante)}>
        Cette année
      </Button>
    </Group>
  );
}

export function Lectures({ nav }: { nav: NavLectures }) {
  return (
    <Stack gap="lg">
      <Stack gap="sm">
        <EnTetePage titre="Lectures" description="Les livres que tu as terminés, ceux à lire, et ton bilan de l'année"
                    actions={AVEC_ANNEE.includes(nav.vue) && <NavAnnee nav={nav} />} />
        <ScrollArea type="never" offsetScrollbars={false}>
          <Tabs value={nav.vue} onChange={v => v && nav.setVue(v as VueLectures)} color="marque">
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
      {(nav.vue === 'journal' || nav.vue === 'a_lire') && <NoteDuJour />}
      {nav.vue === 'journal' && <JournalLivres annee={nav.annee} />}
      {nav.vue === 'a_lire' && <ListeALire />}
      {nav.vue === 'prets' && <LivresPretes />}
      {nav.vue === 'bilan' && <BilanLecture annee={nav.annee} />}
      {nav.vue === 'parametres' && <ParametresLectures />}
    </Stack>
  );
}
