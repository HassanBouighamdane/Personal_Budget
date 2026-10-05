import { useState } from 'react';
import { Box, Grid, Group, SegmentedControl, Stack } from '@mantine/core';
import { IconMinus, IconPlus } from '@tabler/icons-react';

import { auj, MOIS_FR } from '../lib/format';
import { FormDepense, FormRevenu, TransactionsDuMois } from '../components/Transactions';
import { Carte, EnTetePage } from '../components/ui';

export function Saisie() {
  const [type, setType] = useState<'depense' | 'revenu'>('depense');
  const mois = auj().slice(0, 7);
  return (
    <Stack gap="lg">
      <EnTetePage titre="Saisie" description={`Enregistre tes opérations de ${MOIS_FR[+mois.slice(5) - 1].toLowerCase()} ${mois.slice(0, 4)}`} />
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
          <TransactionsDuMois mois={mois} vide="Aucune transaction ce mois — commence ta saisie !" />
        </Grid.Col>
      </Grid>
    </Stack>
  );
}
