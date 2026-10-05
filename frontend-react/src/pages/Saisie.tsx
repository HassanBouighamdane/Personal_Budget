import { useState } from 'react';
import { ActionIcon, Box, Button, Grid, Group, SegmentedControl, Stack, Tooltip } from '@mantine/core';
import { IconChevronLeft, IconChevronRight, IconMinus, IconPlus } from '@tabler/icons-react';

import { auj, decalerMois, libelleMois } from '../lib/format';
import { FormDepense, FormRevenu, TransactionsDuMois } from '../components/Transactions';
import { Carte, EnTetePage } from '../components/ui';

export function Saisie() {
  const [type, setType] = useState<'depense' | 'revenu'>('depense');
  const moisCourant = auj().slice(0, 7);
  // Mois dont les opérations sont listées (et modifiables) à droite ; le formulaire d'ajout reste daté librement
  const [mois, setMois] = useState(moisCourant);
  return (
    <Stack gap="lg">
      <EnTetePage titre="Saisie" description="Enregistre tes opérations, ou modifie celles déjà saisies" actions={
        <Group gap={4} wrap="nowrap">
          <Tooltip label="Mois précédent">
            <ActionIcon variant="default" size={36} radius="md" aria-label="Mois précédent" onClick={() => setMois(m => decalerMois(m, -1))}>
              <IconChevronLeft size={18} />
            </ActionIcon>
          </Tooltip>
          <Button variant="default" h={36} px="sm" fw={600} disabled={mois === moisCourant} onClick={() => setMois(moisCourant)}>
            Mois en cours
          </Button>
          <Tooltip label="Mois suivant">
            <ActionIcon variant="default" size={36} radius="md" aria-label="Mois suivant" onClick={() => setMois(m => decalerMois(m, 1))}>
              <IconChevronRight size={18} />
            </ActionIcon>
          </Tooltip>
        </Group>
      } />
      <Grid gap="lg" align="flex-start">
        <Grid.Col span={{ base: 12, md: 5 }}>
          <Carte className="colle" titre="Nouvelle opération" description="Dépense ou revenu, saisi en quelques secondes">
            <SegmentedControl fullWidth mb="md" value={type} onChange={v => setType(v as typeof type)}
              color={type === 'depense' ? 'rose' : 'bleu'}
              data={[
                { value: 'depense', label: <Group gap={6} justify="center" wrap="nowrap"><IconMinus size={15} />Dépense</Group> },
                { value: 'revenu', label: <Group gap={6} justify="center" wrap="nowrap"><IconPlus size={15} />Revenu</Group> },
              ]} />
            {/* Les deux formulaires restent montés : la saisie en cours n'est pas perdue en changeant de type */}
            <Box display={type === 'depense' ? undefined : 'none'}><FormDepense /></Box>
            <Box display={type === 'revenu' ? undefined : 'none'}><FormRevenu /></Box>
          </Carte>
        </Grid.Col>
        <Grid.Col span={{ base: 12, md: 7 }}>
          <TransactionsDuMois mois={mois} titre={'Transactions — ' + libelleMois(mois)}
                              vide={mois === moisCourant ? 'Aucune transaction ce mois — commence ta saisie !' : 'Aucune transaction ce mois'} />
        </Grid.Col>
      </Grid>
    </Stack>
  );
}
