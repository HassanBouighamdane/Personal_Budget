import { useState } from 'react';
import { Badge, ScrollArea, Stack, Tabs } from '@mantine/core';
import { IconBuildingBank, IconCalendarDue, IconHeartHandshake } from '@tabler/icons-react';

import { parmi } from '../../lib/routes';
import { useEcheances } from '../../lib/queries';
import { EnTetePage } from '../../components/ui';
import { DettesEtPrets } from './Dettes';
import { ListeEcheances } from './Echeances';
import { VuePatrimoine } from './Patrimoine';

export type VueCarnet = 'dettes' | 'echeances' | 'patrimoine';
const VUES_CARNET = ['dettes', 'echeances', 'patrimoine'] as const;

/** État de navigation de l'onglet Suivi (dettes, échéances, patrimoine), gardé par App pour survivre aux
 *  changements d'onglet. `initial` : segments de l'URL après « suivi » (ex : ['echeances']). */
export function useNavCarnet(initial: string[] = []) {
  const [vue, setVue] = useState<VueCarnet>(parmi(initial[0], VUES_CARNET, 'dettes'));
  const chemin = () => [vue];
  const appliquer = ([v]: string[]) => setVue(parmi(v, VUES_CARNET, 'dettes'));
  return { vue, setVue, chemin, appliquer };
}
export type NavCarnet = ReturnType<typeof useNavCarnet>;

export function Carnet({ nav }: { nav: NavCarnet }) {
  const { data: echeances } = useEcheances();
  const aTraiter = (echeances ?? []).filter(e => e.a_rappeler).length;
  return (
    <Stack gap="lg">
      <Stack gap="sm">
        <EnTetePage titre="Suivi" description="L'argent prêté ou emprunté, ce qui a une date limite, et tout ce que tu possèdes" />
        <ScrollArea type="never" offsetScrollbars={false}>
          <Tabs value={nav.vue} onChange={v => v && nav.setVue(v as VueCarnet)} color="marque">
            <Tabs.List style={{ flexWrap: 'nowrap' }}>
              <Tabs.Tab value="dettes" leftSection={<IconHeartHandshake size={16} stroke={1.7} />} fw={500} fz={13.5} px={12}
                        style={{ whiteSpace: 'nowrap' }}>
                Dettes et prêts
              </Tabs.Tab>
              <Tabs.Tab value="echeances" leftSection={<IconCalendarDue size={16} stroke={1.7} />} fw={500} fz={13.5} px={12}
                        style={{ whiteSpace: 'nowrap' }}
                        rightSection={aTraiter > 0 && <Badge size="xs" variant="light" color="ambre" circle>{aTraiter}</Badge>}>
                Échéances
              </Tabs.Tab>
              <Tabs.Tab value="patrimoine" leftSection={<IconBuildingBank size={16} stroke={1.7} />} fw={500} fz={13.5} px={12}
                        style={{ whiteSpace: 'nowrap' }}>
                Patrimoine
              </Tabs.Tab>
            </Tabs.List>
          </Tabs>
        </ScrollArea>
      </Stack>
      {nav.vue === 'dettes' && <DettesEtPrets />}
      {nav.vue === 'echeances' && <ListeEcheances />}
      {nav.vue === 'patrimoine' && <VuePatrimoine />}
    </Stack>
  );
}
