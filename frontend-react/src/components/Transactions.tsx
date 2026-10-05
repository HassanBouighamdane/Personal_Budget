/* Dépenses et revenus : formulaires (ajout, ou modification dans une fenêtre) et liste d'un mois.
 * Partagé par la Saisie (mois en cours) et la vue mensuelle du dashboard (n'importe quel mois). */
import { useState } from 'react';
import { ActionIcon, Box, Button, Group, SegmentedControl, Select, SimpleGrid, Stack, Text, TextInput, Tooltip } from '@mantine/core';
import { modals } from '@mantine/modals';
import { IconArrowDownLeft, IconArrowUpRight, IconPencil, IconReceipt } from '@tabler/icons-react';

import { toast } from '../lib/api';
import { auj, decalerDate, fmt, JOURS_FR, lireMontant, MOIS_FR } from '../lib/format';
import { T } from '../lib/palette';
import type { Depense, Revenu } from '../lib/types';
import { useConfig, useEcriture, useTransactionsMois } from '../lib/queries';
import { ChampDate, ChampMontant } from './champs';
import { BoutonSuppr, Carte, Chargement, confirmer, Pastille, Vide } from './ui';

const AUTRE = '__autre__';

// Montant existant remis dans le champ texte, avec la virgule française
const texteMontant = (m?: number) => m === undefined ? '' : String(m).replace('.', ',');

/* ---------- Formulaires ---------- */
export function FormDepense({ depense, onTermine }: { depense?: Depense; onTermine?: () => void }) {
  const { data: config } = useConfig();
  const ecrire = useEcriture('budget');
  const [date, setDate] = useState(depense?.date ?? auj());
  const [categorie, setCategorie] = useState<string | null>(depense?.categorie ?? null);
  const [montant, setMontant] = useState(texteMontant(depense?.montant));
  const [description, setDescription] = useState(depense?.description ?? '');

  function enregistrer() {
    const m = lireMontant(montant);
    if (!categorie) return toast('Choisis une catégorie', false);
    if (isNaN(m) || m <= 0) return toast('Montant invalide', false);
    const body = { date, categorie, description, montant: m };
    ecrire.mutate(
      depense
        ? { path: `/api/depenses/${depense.id}`, method: 'PUT', body, succes: 'Dépense modifiée ✓' }
        : { path: '/api/depenses', method: 'POST', body, succes: 'Dépense ajoutée ✓' },
      { onSuccess: () => { if (!depense) { setMontant(''); setDescription(''); } onTermine?.(); } },
    );
  }

  // Sans doublon : Mantine refuse deux options de même valeur (les noms sont uniques en base).
  // Une catégorie désactivée depuis reste proposée pour la dépense qui la porte déjà.
  const cats = [...new Set([...(config?.categories.map(c => c.nom) ?? []), ...(depense ? [depense.categorie] : [])])];
  return (
    <Stack gap="sm">
      <ChampMontant label="Montant (DH)" size="md" value={montant} onChange={setMontant}
                    onKeyDown={e => { if (e.key === 'Enter') enregistrer(); }} />
      <Select label="Catégorie" placeholder="— Choisir une catégorie —" data={cats} searchable
              nothingFoundMessage="Aucune catégorie"
              value={categorie && cats.includes(categorie) ? categorie : null} onChange={setCategorie} />
      <SimpleGrid cols={{ base: 1, xs: 2 }} spacing="sm">
        <ChampDate value={date} onChange={setDate} />
        <TextInput label="Description (optionnel)" placeholder="ex : courses Marjane"
                   value={description} onChange={e => setDescription(e.currentTarget.value)} />
      </SimpleGrid>
      <Button mt="xs" size="md" color="rose" onClick={enregistrer} loading={ecrire.isPending}>
        {depense ? 'Enregistrer' : 'Ajouter la dépense'}
      </Button>
    </Stack>
  );
}

export function FormRevenu({ revenu, onTermine }: { revenu?: Revenu; onTermine?: () => void }) {
  const { data: config } = useConfig();
  const ecrire = useEcriture('budget');
  const [date, setDate] = useState(revenu?.date ?? auj());
  const [source, setSource] = useState<string | null>(revenu?.source || null);
  const [autre, setAutre] = useState('');
  const [montant, setMontant] = useState(texteMontant(revenu?.montant));

  function enregistrer() {
    const m = lireMontant(montant);
    let s = source;
    if (!s) return toast('Choisis une source', false);
    if (s === AUTRE) {
      s = autre.trim();
      if (!s) return toast('Précise la source', false);
    }
    if (isNaN(m) || m <= 0) return toast('Montant invalide', false);
    const body = { date, source: s, montant: m };
    ecrire.mutate(
      revenu
        ? { path: `/api/revenus/${revenu.id}`, method: 'PUT', body, succes: 'Revenu modifié ✓' }
        : { path: '/api/revenus', method: 'POST', body, succes: 'Revenu ajouté ✓' },
      { onSuccess: () => { if (!revenu) { setMontant(''); setAutre(''); } onTermine?.(); } },
    );
  }

  // Une source libre (« Autre… ») ou désactivée depuis reste proposée pour le revenu qui la porte déjà
  const noms = [...new Set([...(config?.sources.map(s => s.nom) ?? []), ...(revenu?.source ? [revenu.source] : [])])];
  const valeur = source && (source === AUTRE || noms.includes(source)) ? source : null;
  return (
    <Stack gap="sm">
      <ChampMontant label="Montant (DH)" size="md" value={montant} onChange={setMontant}
                    onKeyDown={e => { if (e.key === 'Enter') enregistrer(); }} />
      <Select label="Source" placeholder="— Choisir une source —"
              data={[...noms.map(n => ({ value: n, label: n })), { value: AUTRE, label: 'Autre…' }]}
              value={valeur} onChange={setSource} />
      {valeur === AUTRE && (
        <TextInput placeholder="Précise la source..." value={autre} onChange={e => setAutre(e.currentTarget.value)} />
      )}
      <ChampDate value={date} onChange={setDate} />
      <Button mt="xs" size="md" color="bleu" onClick={enregistrer} loading={ecrire.isPending}>
        {revenu ? 'Enregistrer' : 'Ajouter le revenu'}
      </Button>
    </Stack>
  );
}

/* ---------- Liste d'un mois ---------- */
type Ligne = { id: number; date: string; titre: string; detail: string; montant: number }
  & ({ type: 'depenses'; origine: Depense } | { type: 'revenus'; origine: Revenu });

function modifier(l: Ligne) {
  const fermer = () => modals.close(id);
  const id = modals.open({
    title: <Text fw={650}>{l.type === 'depenses' ? 'Modifier la dépense' : 'Modifier le revenu'}</Text>,
    centered: true,
    children: l.type === 'depenses'
      ? <FormDepense depense={l.origine} onTermine={fermer} />
      : <FormRevenu revenu={l.origine} onTermine={fermer} />,
  });
}

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

export function TransactionsDuMois({ mois, titre = 'Transactions du mois', vide = 'Aucune transaction ce mois' }: {
  mois: string; titre?: string; vide?: string;
}) {
  const { data, isPending } = useTransactionsMois(mois);
  const ecrire = useEcriture('budget');
  const [filtre, setFiltre] = useState<'tout' | 'depenses' | 'revenus'>('tout');

  const lignes: Ligne[] = data ? [
    ...data.depenses.map(x => ({ id: x.id, type: 'depenses' as const, origine: x, date: x.date, montant: x.montant, titre: x.categorie, detail: x.description })),
    ...data.revenus.map(x => ({ id: x.id, type: 'revenus' as const, origine: x, date: x.date, montant: x.montant, titre: x.source || 'Revenu', detail: '' })),
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
    <Carte titre={titre} description={lignes.length ? `${lignes.length} opération${lignes.length > 1 ? 's' : ''}` : undefined}
      droite={lignes.length > 0 && (
        <SegmentedControl size="xs" value={filtre} onChange={v => setFiltre(v as typeof filtre)}
          data={[{ value: 'tout', label: 'Tout' }, { value: 'depenses', label: 'Dépenses' }, { value: 'revenus', label: 'Revenus' }]} />
      )}>
      {isPending ? <Chargement lignes={5} /> : !lignes.length ? (
        <Vide icone={IconReceipt}>{vide}</Vide>
      ) : (
        <Stack gap="md">
          <Group grow gap="sm" p="sm" style={{ borderRadius: 'var(--mantine-radius-md)', background: 'light-dark(var(--mantine-color-gray-0), rgba(154,161,173,.06))' }}>
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
                      <Pastille icone={dep ? IconArrowUpRight : IconArrowDownLeft} couleur={dep ? 'rose' : 'bleu'} taille={34} />
                      <Box style={{ flex: 1, minWidth: 0 }}>
                        <Text fz="sm" fw={600} truncate>{l.titre}</Text>
                        {l.detail && <Text fz="xs" c="dimmed" truncate>{l.detail}</Text>}
                      </Box>
                      <Text className="chiffre" fw={650} fz="sm" c={dep ? T.dep : T.rev} style={{ whiteSpace: 'nowrap' }}>
                        {dep ? '−' : '+'} {fmt(l.montant)}
                      </Text>
                      <Group gap={0} wrap="nowrap">
                        <Tooltip label="Modifier" withArrow>
                          <ActionIcon variant="subtle" color="gray" onClick={() => modifier(l)} aria-label="Modifier" className="suppr">
                            <IconPencil size={16} stroke={1.7} />
                          </ActionIcon>
                        </Tooltip>
                        <BoutonSuppr onClick={() => supprimer(l)} />
                      </Group>
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
