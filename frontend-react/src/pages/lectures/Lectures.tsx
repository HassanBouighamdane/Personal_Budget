import { useState } from 'react';
import { ActionIcon, Button, Group, ScrollArea, Stack, Tabs, Text, Tooltip } from '@mantine/core';
import { IconBook2, IconChartBar, IconChevronLeft, IconChevronRight, IconSettings } from '@tabler/icons-react';

import { EnTetePage } from '../../components/ui';
import { JournalLivres } from './Journal';
import { BilanLecture } from './Bilan';
import { ParametresLectures } from './ParametresLectures';

export type VueLectures = 'bilan' | 'journal' | 'parametres';

/** État de navigation du module Lectures, gardé par App pour survivre aux changements d'onglet */
export function useNavLectures() {
  const [vue, setVue] = useState<VueLectures>('journal');
  const [annee, setAnnee] = useState(new Date().getFullYear());
  return { vue, setVue, annee, setAnnee };
}
export type NavLectures = ReturnType<typeof useNavLectures>;

const VUES: { value: VueLectures; label: string; Icone: typeof IconBook2 }[] = [
  { value: 'journal', label: 'Journal', Icone: IconBook2 },
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
        <EnTetePage titre="Lectures" description="Les livres que tu as terminés, et ton bilan de l'année"
                    actions={nav.vue !== 'parametres' && <NavAnnee nav={nav} />} />
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
      {nav.vue === 'journal' && <JournalLivres annee={nav.annee} />}
      {nav.vue === 'bilan' && <BilanLecture annee={nav.annee} />}
      {nav.vue === 'parametres' && <ParametresLectures />}
    </Stack>
  );
}
