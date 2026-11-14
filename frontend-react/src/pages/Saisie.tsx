import { useEffect, useState } from 'react';
import { ActionIcon, Box, Button, CloseButton, Grid, Group, SegmentedControl, Stack, TextInput, Tooltip } from '@mantine/core';
import { DatePickerInput, type DatesRangeValue } from '@mantine/dates';
import { useDebouncedValue } from '@mantine/hooks';
import { IconCalendarEvent, IconChevronLeft, IconChevronRight, IconMinus, IconPlus, IconRepeat, IconSearch } from '@tabler/icons-react';

import { auj, decalerDate, decalerMois, libelleMois } from '../lib/format';
import { estDate, estMois } from '../lib/routes';
import type { Periode } from '../lib/types';
import { FormDepense, FormRevenu, ResultatsRecherche, TransactionsDuMois } from '../components/Transactions';
import { ouvrirRecurrences, RecurrencesAAjouter } from '../components/Recurrences';
import { Carte, EnTetePage } from '../components/ui';

/** Segments « periode/2026-01-01/2026-03-31[/recherche] » → [période, recherche], sinon null */
function lirePeriode([a, b, c, d]: string[]): [Periode, string] | null {
  return a === 'periode' && estDate(b) && estDate(c) && b <= c ? [[b, c], d ?? ''] : null;
}

/** Mois listé, recherche et période en cours, gardés par App (et dans l'URL : #/saisie/2026-09,
 *  #/saisie/recherche/… ou #/saisie/periode/2026-01-01/2026-03-31[/…]) */
export function useNavSaisie(initial: string[] = []) {
  const [mois, setMois] = useState(estMois(initial[0]) ? initial[0] : auj().slice(0, 7));
  const p = lirePeriode(initial);
  const [periode, setPeriode] = useState<Periode | null>(p ? p[0] : null);
  const [recherche, setRecherche] = useState(p ? p[1] : initial[0] === 'recherche' ? initial[1] ?? '' : '');
  const chemin = () => {
    const q = recherche.trim();
    if (periode) return ['periode', ...periode, ...(q ? [q] : [])];
    return q ? ['recherche', q] : [mois];
  };
  function appliquer(segments: string[]) {
    const [a, b] = segments;
    const lu = lirePeriode(segments);
    setPeriode(lu ? lu[0] : null);
    if (lu) setRecherche(lu[1]);
    else if (a === 'recherche') setRecherche(b ?? '');
    else {
      setRecherche('');
      if (estMois(a)) setMois(a);
    }
  }
  return { mois, setMois, recherche, setRecherche, periode, setPeriode, chemin, appliquer };
}

/** Raccourcis du choix de période (bornes incluses) */
function raccourcisPeriode() {
  const j = auj(), m = j.slice(0, 7), a = +j.slice(0, 4);
  const prec = decalerMois(m, -1);
  return [
    { label: 'Ce mois', value: [m + '-01', j] as [string, string] },
    { label: 'Mois dernier', value: [prec + '-01', decalerDate(m + '-01', -1)] as [string, string] },
    { label: '3 derniers mois', value: [decalerMois(m, -2) + '-01', j] as [string, string] },
    { label: 'Cette année', value: [`${a}-01-01`, j] as [string, string] },
    { label: 'Année dernière', value: [`${a - 1}-01-01`, `${a - 1}-12-31`] as [string, string] },
  ];
}

/** Période : la recherche (ou, sans texte, toutes les opérations) est limitée à ces dates */
function ChoixPeriode({ periode, onChange }: { periode: Periode | null; onChange: (p: Periode | null) => void }) {
  // Valeur affichée : garde le premier jour cliqué en attendant le second
  const [valeur, setValeur] = useState<DatesRangeValue<string>>(periode ?? [null, null]);
  useEffect(() => setValeur(periode ?? [null, null]), [periode?.[0], periode?.[1]]);   // eslint-disable-line react-hooks/exhaustive-deps
  return (
    <DatePickerInput type="range" w={{ base: '100%', xs: 260 }} placeholder="Période" clearable allowSingleDateInRange
                     valueFormat="DD/MM/YYYY" leftSection={<IconCalendarEvent size={16} />} aria-label="Filtrer sur une période"
                     presets={raccourcisPeriode()} value={valeur} popoverProps={{ withinPortal: true }}
                     onChange={v => {
                       setValeur(v);
                       if (v[0] && v[1]) onChange([v[0], v[1]]);
                       else if (!v[0] && !v[1]) onChange(null);
                     }} />
  );
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
  const { periode } = nav;
  const filtre = !!q || !!periode;

  return (
    <Stack gap="lg">
      <EnTetePage titre="Saisie" description="Enregistre tes opérations, ou modifie celles déjà saisies" actions={
        <Group gap="xs" wrap="wrap">
          <Button variant="default" h={36} px="sm" leftSection={<IconRepeat size={16} />} onClick={ouvrirRecurrences}>Récurrences</Button>
          <TextInput w={{ base: '100%', xs: 240 }} placeholder="Rechercher (texte, 250, #tag)" value={texte}
                     onChange={e => setTexte(e.currentTarget.value)} leftSection={<IconSearch size={16} />}
                     rightSection={texte ? <CloseButton size="sm" aria-label="Effacer la recherche" onClick={() => setTexte('')} /> : null}
                     aria-label="Rechercher dans tout l'historique" />
          <ChoixPeriode periode={periode} onChange={nav.setPeriode} />
          <Group gap={4} wrap="nowrap" display={periode ? 'none' : undefined} style={{ visibility: q ? 'hidden' : undefined }}>
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
                 description={mois === moisCourant || filtre ? 'Dépense ou revenu, saisi en quelques secondes' : `Datée par défaut en ${libelleMois(mois).toLowerCase()}`}>
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
          {filtre ? <ResultatsRecherche q={q} periode={periode} onTag={t => setTexte('#' + t)} /> : (
            <Stack gap="lg">
              <RecurrencesAAjouter />
              <TransactionsDuMois mois={mois} titre={'Transactions — ' + libelleMois(mois)} onTag={t => setTexte('#' + t)}
                                  vide={mois === moisCourant ? 'Aucune transaction ce mois — commence ta saisie !' : 'Aucune transaction ce mois'} />
            </Stack>
          )}
        </Grid.Col>
      </Grid>
    </Stack>
  );
}
