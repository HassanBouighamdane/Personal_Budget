import { useState } from 'react';
import { Box, Button, Grid, Group, SegmentedControl, Select, SimpleGrid, Stack, Text, TextInput } from '@mantine/core';
import { IconArrowDownLeft, IconArrowUpRight, IconMinus, IconPlus, IconReceipt } from '@tabler/icons-react';

import { toast } from '../lib/api';
import { auj, decalerDate, fmt, JOURS_FR, lireMontant, MOIS_FR } from '../lib/format';
import { T } from '../lib/palette';
import { useConfig, useEcriture, useTransactionsMois } from '../lib/queries';
import { ChampDate, ChampMontant } from '../components/champs';
import { BoutonSuppr, Carte, Chargement, confirmer, EnTetePage, Pastille, Vide } from '../components/ui';

const AUTRE = '__autre__';

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
              color={type === 'depense' ? 'safran' : 'ocean'}
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
          <TransactionsDuMois mois={mois} />
        </Grid.Col>
      </Grid>
    </Stack>
  );
}

function FormDepense() {
  const { data: config } = useConfig();
  const ecrire = useEcriture('budget');
  const [date, setDate] = useState(auj());
  const [categorie, setCategorie] = useState<string | null>(null);
  const [montant, setMontant] = useState('');
  const [description, setDescription] = useState('');

  function ajouter() {
    const m = lireMontant(montant);
    if (!categorie) return toast('Choisis une catégorie', false);
    if (isNaN(m) || m <= 0) return toast('Montant invalide', false);
    ecrire.mutate(
      { path: '/api/depenses', method: 'POST', body: { date, categorie, description, montant: m }, succes: 'Dépense ajoutée ✓' },
      { onSuccess: () => { setMontant(''); setDescription(''); } },
    );
  }

  // Sans doublon : Mantine refuse deux options de même valeur (les noms sont uniques en base)
  const cats = [...new Set(config?.categories.map(c => c.nom))];
  return (
    <Stack gap="sm">
      <ChampMontant label="Montant (DH)" size="md" value={montant} onChange={setMontant}
                    onKeyDown={e => { if (e.key === 'Enter') ajouter(); }} />
      <Select label="Catégorie" placeholder="— Choisir une catégorie —" data={cats} searchable
              nothingFoundMessage="Aucune catégorie"
              value={categorie && cats.includes(categorie) ? categorie : null} onChange={setCategorie} />
      <SimpleGrid cols={{ base: 1, xs: 2 }} spacing="sm">
        <ChampDate value={date} onChange={setDate} />
        <TextInput label="Description (optionnel)" placeholder="ex : courses Marjane"
                   value={description} onChange={e => setDescription(e.currentTarget.value)} />
      </SimpleGrid>
      <Button mt="xs" size="md" onClick={ajouter} loading={ecrire.isPending}>Ajouter la dépense</Button>
    </Stack>
  );
}

function FormRevenu() {
  const { data: config } = useConfig();
  const ecrire = useEcriture('budget');
  const [date, setDate] = useState(auj());
  const [source, setSource] = useState<string | null>(null);
  const [autre, setAutre] = useState('');
  const [montant, setMontant] = useState('');

  function ajouter() {
    const m = lireMontant(montant);
    let s = source;
    if (!s) return toast('Choisis une source', false);
    if (s === AUTRE) {
      s = autre.trim();
      if (!s) return toast('Précise la source', false);
    }
    if (isNaN(m) || m <= 0) return toast('Montant invalide', false);
    ecrire.mutate(
      { path: '/api/revenus', method: 'POST', body: { date, source: s, montant: m }, succes: 'Revenu ajouté ✓' },
      { onSuccess: () => { setMontant(''); setAutre(''); } },
    );
  }

  const noms = [...new Set(config?.sources.map(s => s.nom))];
  const valeur = source && (source === AUTRE || noms.includes(source)) ? source : null;
  return (
    <Stack gap="sm">
      <ChampMontant label="Montant (DH)" size="md" value={montant} onChange={setMontant}
                    onKeyDown={e => { if (e.key === 'Enter') ajouter(); }} />
      <Select label="Source" placeholder="— Choisir une source —"
              data={[...noms.map(n => ({ value: n, label: n })), { value: AUTRE, label: 'Autre…' }]}
              value={valeur} onChange={setSource} />
      {valeur === AUTRE && (
        <TextInput placeholder="Précise la source..." value={autre} onChange={e => setAutre(e.currentTarget.value)} />
      )}
      <ChampDate value={date} onChange={setDate} />
      <Button mt="xs" size="md" color="ocean" onClick={ajouter} loading={ecrire.isPending}>Ajouter le revenu</Button>
    </Stack>
  );
}

type Ligne = { id: number; type: 'depenses' | 'revenus'; date: string; titre: string; detail: string; montant: number };

function libelleJour(date: string) {
  if (date === auj()) return "Aujourd'hui";
  if (date === decalerDate(auj(), -1)) return 'Hier';
  const [a, m, j] = date.split('-').map(Number);
  return JOURS_FR[(new Date(a, m - 1, j).getDay() + 6) % 7] + ' ' + j + ' ' + MOIS_FR[m - 1].toLowerCase();
}

function Resume({ label, valeur, couleur }: { label: string; valeur: string; couleur?: string }) {
  return (
    <Box>
      <Text fz={11} c="dimmed" fw={500}>{label}</Text>
      <Text className="chiffre" fw={700} fz={{ base: 15, sm: 17 }} c={couleur}>{valeur}</Text>
    </Box>
  );
}

function TransactionsDuMois({ mois }: { mois: string }) {
  const { data, isPending } = useTransactionsMois(mois);
  const ecrire = useEcriture('budget');
  const [filtre, setFiltre] = useState<'tout' | 'depenses' | 'revenus'>('tout');

  const lignes: Ligne[] = data ? [
    ...data.depenses.map(x => ({ id: x.id, type: 'depenses' as const, date: x.date, montant: x.montant, titre: x.categorie, detail: x.description })),
    ...data.revenus.map(x => ({ id: x.id, type: 'revenus' as const, date: x.date, montant: x.montant, titre: x.source || 'Revenu', detail: '' })),
  ].sort((a, b) => b.date.localeCompare(a.date) || b.id - a.id) : [];
  const visibles = filtre === 'tout' ? lignes : lignes.filter(l => l.type === filtre);
  const totalDep = lignes.filter(l => l.type === 'depenses').reduce((s, l) => s + l.montant, 0);
  const totalRev = lignes.filter(l => l.type === 'revenus').reduce((s, l) => s + l.montant, 0);

  // Regroupement par jour (lignes déjà triées par date décroissante)
  const jours: { date: string; lignes: Ligne[] }[] = [];
  for (const l of visibles) {
    if (jours.at(-1)?.date !== l.date) jours.push({ date: l.date, lignes: [] });
    jours.at(-1)!.lignes.push(l);
  }

  const supprimer = (l: Ligne) => confirmer('Supprimer cette ligne ?', () =>
    ecrire.mutate({ path: `/api/${l.type}/${l.id}`, method: 'DELETE', succes: 'Supprimé' }));

  return (
    <Carte titre="Transactions du mois" description={lignes.length ? `${lignes.length} opération${lignes.length > 1 ? 's' : ''}` : undefined}
      droite={lignes.length > 0 && (
        <SegmentedControl size="xs" value={filtre} onChange={v => setFiltre(v as typeof filtre)}
          data={[{ value: 'tout', label: 'Tout' }, { value: 'depenses', label: 'Dépenses' }, { value: 'revenus', label: 'Revenus' }]} />
      )}>
      {isPending ? <Chargement lignes={5} /> : !lignes.length ? (
        <Vide icone={IconReceipt}>Aucune transaction ce mois — commence ta saisie !</Vide>
      ) : (
        <Stack gap="md">
          <Group grow gap="sm" p="sm" style={{ borderRadius: 'var(--mantine-radius-md)', background: 'light-dark(var(--mantine-color-gray-0), rgba(141,152,180,.06))' }}>
            <Resume label="Dépenses" valeur={fmt(totalDep)} couleur={T.dep} />
            <Resume label="Revenus" valeur={fmt(totalRev)} couleur={T.rev} />
            <Resume label="Solde" valeur={fmt(totalRev - totalDep)} couleur={totalRev - totalDep >= 0 ? T.ep : T.neg} />
          </Group>
          {jours.map(j => (
            <Box key={j.date}>
              <Text fz={11} fw={700} c="dimmed" tt="uppercase" lts={0.5} mb={4} px={4}>{libelleJour(j.date)}</Text>
              <Stack gap={2}>
                {j.lignes.map(l => {
                  const dep = l.type === 'depenses';
                  return (
                    <Group key={l.type + l.id} className="ligne-op" wrap="nowrap" gap="sm" px={6} py={8}>
                      <Pastille icone={dep ? IconArrowUpRight : IconArrowDownLeft} couleur={dep ? 'safran' : 'ocean'} taille={34} />
                      <Box style={{ flex: 1, minWidth: 0 }}>
                        <Text fz="sm" fw={600} truncate>{l.titre}</Text>
                        {l.detail && <Text fz="xs" c="dimmed" truncate>{l.detail}</Text>}
                      </Box>
                      <Text className="chiffre" fw={650} fz="sm" c={dep ? T.dep : T.rev} style={{ whiteSpace: 'nowrap' }}>
                        {dep ? '−' : '+'} {fmt(l.montant)}
                      </Text>
                      <BoutonSuppr onClick={() => supprimer(l)} />
                    </Group>
                  );
                })}
              </Stack>
            </Box>
          ))}
          {!visibles.length && <Vide>Aucune opération de ce type ce mois</Vide>}
        </Stack>
      )}
    </Carte>
  );
}
