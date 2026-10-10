import { useEffect, useState } from 'react';
import { ActionIcon, Box, Button, CloseButton, Grid, Group, SegmentedControl, Stack, TextInput, Tooltip } from '@mantine/core';
import { useDebouncedValue } from '@mantine/hooks';
import { IconChevronLeft, IconChevronRight, IconMinus, IconPlus, IconSearch } from '@tabler/icons-react';

import { auj, decalerMois, libelleMois } from '../lib/format';
import { estMois } from '../lib/routes';
import { FormDepense, FormRevenu, ResultatsRecherche, TransactionsDuMois } from '../components/Transactions';
import { Carte, EnTetePage } from '../components/ui';

/** Mois listé et recherche en cours, gardés par App (et dans l'URL : #/saisie/2026-09 ou #/saisie/recherche/…) */
export function useNavSaisie(initial: string[] = []) {
  const [mois, setMois] = useState(estMois(initial[0]) ? initial[0] : auj().slice(0, 7));
  const [recherche, setRecherche] = useState(initial[0] === 'recherche' ? initial[1] ?? '' : '');
  const chemin = () => recherche.trim() ? ['recherche', recherche.trim()] : [mois];
  function appliquer([a, b]: string[]) {
    if (a === 'recherche') setRecherche(b ?? '');
    else {
      setRecherche('');
      if (estMois(a)) setMois(a);
    }
  }
  return { mois, setMois, recherche, setRecherche, chemin, appliquer };
}
export type NavSaisie = ReturnType<typeof useNavSaisie>;

export function Saisie({ nav }: { nav: NavSaisie }) {
  const [type, setType] = useState<'depense' | 'revenu'>('depense');
  const moisCourant = auj().slice(0, 7);
  const { mois, setMois } = nav;
  // Texte tapé, envoyé à la recherche après une courte pause
  const [texte, setTexte] = useState(nav.recherche);
  const [cherche] = useDebouncedValue(texte, 350);
  useEffect(() => { nav.setRecherche(cherche); }, [cherche]);   // eslint-disable-line react-hooks/exhaustive-deps
  // Recherche changée ailleurs (bouton Retour du navigateur) : le champ suit
  useEffect(() => { if (nav.recherche !== cherche) setTexte(nav.recherche); }, [nav.recherche]);   // eslint-disable-line react-hooks/exhaustive-deps
  const q = nav.recherche.trim();

  return (
    <Stack gap="lg">
      <EnTetePage titre="Saisie" description="Enregistre tes opérations, ou modifie celles déjà saisies" actions={
        <Group gap="xs" wrap="wrap">
          <TextInput w={{ base: '100%', xs: 240 }} placeholder="Rechercher (texte, 250, #tag)" value={texte}
                     onChange={e => setTexte(e.currentTarget.value)} leftSection={<IconSearch size={16} />}
                     rightSection={texte ? <CloseButton size="sm" aria-label="Effacer la recherche" onClick={() => setTexte('')} /> : null}
                     aria-label="Rechercher dans tout l'historique" />
          <Group gap={4} wrap="nowrap" style={{ visibility: q ? 'hidden' : undefined }}>
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
        </Group>
      } />
      <Grid gap="lg" align="flex-start">
        <Grid.Col span={{ base: 12, md: 5 }}>
          <Carte className="colle" titre="Nouvelle opération"
                 description={mois === moisCourant || q ? 'Dépense ou revenu, saisi en quelques secondes' : `Datée par défaut en ${libelleMois(mois).toLowerCase()}`}>
            <SegmentedControl fullWidth mb="md" value={type} onChange={v => setType(v as typeof type)}
              color={type === 'depense' ? 'rose' : 'bleu'}
              data={[
                { value: 'depense', label: <Group gap={6} justify="center" wrap="nowrap"><IconMinus size={15} />Dépense</Group> },
                { value: 'revenu', label: <Group gap={6} justify="center" wrap="nowrap"><IconPlus size={15} />Revenu</Group> },
              ]} />
            {/* Les deux formulaires restent montés : la saisie en cours n'est pas perdue en changeant de type */}
            <Box display={type === 'depense' ? undefined : 'none'}><FormDepense mois={mois} /></Box>
            <Box display={type === 'revenu' ? undefined : 'none'}><FormRevenu mois={mois} /></Box>
          </Carte>
        </Grid.Col>
        <Grid.Col span={{ base: 12, md: 7 }}>
          {q ? <ResultatsRecherche q={q} onTag={t => setTexte('#' + t)} /> : (
            <TransactionsDuMois mois={mois} titre={'Transactions — ' + libelleMois(mois)} onTag={t => setTexte('#' + t)}
                                vide={mois === moisCourant ? 'Aucune transaction ce mois — commence ta saisie !' : 'Aucune transaction ce mois'} />
          )}
        </Grid.Col>
      </Grid>
    </Stack>
  );
}
