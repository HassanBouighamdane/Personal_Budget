/* Lectures — saisie d'un livre terminé et journal de l'année */
import { useState } from 'react';
import {
  ActionIcon, Autocomplete, Box, Button, CloseButton, Grid, Group, NumberInput, Rating, Select, SimpleGrid, Stack, Text, Textarea, TextInput, Tooltip,
} from '@mantine/core';
import { DatePickerInput } from '@mantine/dates';
import { modals } from '@mantine/modals';
import { IconBook, IconCalendar, IconPencil } from '@tabler/icons-react';

import { toast } from '../../lib/api';
import { auj, dateFr, MOIS_FR } from '../../lib/format';
import type { Livre } from '../../lib/types';
import { useAuteurs, useEcriture, useGenres, useLivres } from '../../lib/queries';
import { ChampDate } from '../../components/champs';
import { BoutonSuppr, Carte, Chargement, confirmer, Pastille, Vide } from '../../components/ui';

/* ---------- Formulaire (ajout, ou modification dans une fenêtre) ---------- */
function FormLivre({ livre, onTermine }: { livre?: Livre; onTermine?: () => void }) {
  const ecrire = useEcriture('lectures');
  const { data: genres } = useGenres();
  const { data: auteurs } = useAuteurs();
  const [titre, setTitre] = useState(livre?.titre ?? '');
  const [auteur, setAuteur] = useState(livre?.auteur ?? '');
  const [genre, setGenre] = useState<string | null>(livre?.genre || null);
  const [dateDebut, setDateDebut] = useState<string | null>(livre?.date_debut ?? null);
  const [dateFin, setDateFin] = useState(livre?.date_fin ?? auj());
  const [pages, setPages] = useState<string | number>(livre?.pages ?? '');
  const [note, setNote] = useState(livre?.note ?? 0);
  const [commentaire, setCommentaire] = useState(livre?.commentaire ?? '');

  // Un genre désactivé depuis reste proposé pour le livre qui le porte déjà
  const nomsGenres = [...new Set([...(genres ?? []).map(g => g.nom), ...(livre?.genre ? [livre.genre] : [])])];

  function enregistrer() {
    if (!titre.trim()) return toast('Indique le titre', false);
    if (dateDebut && dateDebut > dateFin) return toast('La date de début doit précéder la date de fin', false);
    const p = typeof pages === 'number' ? pages : parseInt(pages);
    const body = {
      titre: titre.trim(), auteur: auteur.trim(), genre: genre ?? '', date_debut: dateDebut, date_fin: dateFin,
      pages: p > 0 ? p : null, note: note || null, commentaire: commentaire.trim(),
    };
    ecrire.mutate(
      livre
        ? { path: `/api/lectures/livres/${livre.id}`, method: 'PUT', body, succes: 'Livre modifié ✓' }
        : { path: '/api/lectures/livres', method: 'POST', body, succes: 'Livre ajouté ✓ Bonne lecture pour la suite !' },
      {
        onSuccess: () => {
          if (!livre) { setTitre(''); setAuteur(''); setGenre(null); setDateDebut(null); setPages(''); setNote(0); setCommentaire(''); }
          onTermine?.();
        },
      },
    );
  }

  return (
    <Stack gap="sm">
      <TextInput label="Titre" placeholder="ex : L'Étranger" value={titre} onChange={e => setTitre(e.currentTarget.value)} />
      <SimpleGrid cols={{ base: 1, xs: 2 }} spacing="sm">
        <Autocomplete label="Auteur" placeholder="ex : Albert Camus" data={auteurs ?? []} value={auteur} onChange={setAuteur} limit={20} />
        <Select label="Genre" placeholder="— Choisir —" data={nomsGenres} value={genre} onChange={setGenre} searchable clearable
                nothingFoundMessage="Aucun genre (ajoute-le dans Paramètres)" />
      </SimpleGrid>
      <SimpleGrid cols={{ base: 1, xs: 2 }} spacing="sm">
        <DatePickerInput label="Commencé le (optionnel)" placeholder="—" value={dateDebut} onChange={setDateDebut} clearable
                         valueFormat="DD/MM/YYYY" leftSection={<IconCalendar size={16} />} maxDate={dateFin} />
        <ChampDate label="Terminé le" value={dateFin} onChange={setDateFin} />
      </SimpleGrid>
      <SimpleGrid cols={{ base: 1, xs: 2 }} spacing="sm" style={{ alignItems: 'end' }}>
        <NumberInput label="Pages (optionnel)" placeholder="ex : 320" min={1} allowNegative={false} allowDecimal={false}
                     value={pages} onChange={setPages} />
        <Box>
          <Text fz={13} fw={600} mb={6}>Ton avis</Text>
          <Group gap={6} h={36} wrap="nowrap">
            <Rating value={note} onChange={setNote} size="lg" />
            {note > 0 && <CloseButton size="sm" aria-label="Effacer la note" onClick={() => setNote(0)} />}
          </Group>
        </Box>
      </SimpleGrid>
      <Textarea label="Note personnelle (optionnel)" placeholder="Ce que tu en retiens, une citation…" autosize minRows={2} maxRows={6}
                value={commentaire} onChange={e => setCommentaire(e.currentTarget.value)} />
      <Button mt="xs" onClick={enregistrer} loading={ecrire.isPending}>{livre ? 'Enregistrer' : 'Ajouter le livre'}</Button>
    </Stack>
  );
}

function modifier(livre: Livre) {
  const id = modals.open({
    title: <Text fw={650}>Modifier le livre</Text>,
    size: 'lg',
    centered: true,
    children: <FormLivre livre={livre} onTermine={() => modals.close(id)} />,
  });
}

/* ---------- Ligne du journal ---------- */
function LigneLivre({ l }: { l: Livre }) {
  const ecrire = useEcriture('lectures');
  const details = [l.auteur, l.genre, l.pages ? `${l.pages} pages` : ''].filter(Boolean).join(' · ');
  return (
    <Group className="ligne-op" wrap="nowrap" gap="sm" px={6} py={8} align="flex-start">
      <Pastille icone={IconBook} couleur="marque" taille={34} />
      <Box style={{ flex: 1, minWidth: 0 }}>
        <Text fz="sm" fw={600} truncate>{l.titre}</Text>
        {details && <Text fz="xs" c="dimmed" truncate>{details}</Text>}
        {l.commentaire && <Text fz="xs" c="dimmed" fs="italic" lineClamp={2} mt={2}>« {l.commentaire} »</Text>}
      </Box>
      <Stack gap={2} align="flex-end">
        {l.note ? <Rating value={l.note} readOnly size="xs" /> : null}
        <Text fz="xs" c="dimmed" style={{ whiteSpace: 'nowrap' }}>{dateFr(l.date_fin, false)}</Text>
      </Stack>
      <Tooltip label="Modifier" withArrow>
        <ActionIcon variant="subtle" color="gray" onClick={() => modifier(l)} aria-label="Modifier" className="suppr">
          <IconPencil size={16} stroke={1.7} />
        </ActionIcon>
      </Tooltip>
      <BoutonSuppr onClick={() => confirmer(`Supprimer « ${l.titre} » de ton journal ?`, () =>
        ecrire.mutate({ path: `/api/lectures/livres/${l.id}`, method: 'DELETE', succes: 'Livre supprimé' }))} />
    </Group>
  );
}

/* ---------- Page ---------- */
export function JournalLivres({ annee }: { annee: number }) {
  const { data: livres, isPending } = useLivres(annee);

  // Regroupement par mois de fin de lecture (livres déjà triés du plus récent au plus ancien)
  const mois: { m: number; livres: Livre[] }[] = [];
  for (const l of livres ?? []) {
    const m = +l.date_fin.slice(5, 7);
    if (mois.at(-1)?.m !== m) mois.push({ m, livres: [] });
    mois.at(-1)!.livres.push(l);
  }
  const nb = livres?.length ?? 0;

  return (
    <Grid gap="lg" align="flex-start">
      <Grid.Col span={{ base: 12, md: 5 }}>
        <Carte className="colle" titre="Livre terminé" description="Une relecture compte comme un nouveau livre"
               icone={<Pastille icone={IconBook} couleur="marque" />}>
          <FormLivre />
        </Carte>
      </Grid.Col>
      <Grid.Col span={{ base: 12, md: 7 }}>
        <Carte titre={`Livres lus en ${annee}`} description={nb ? `${nb} livre${nb > 1 ? 's' : ''}` : undefined}>
          {isPending ? <Chargement lignes={5} /> : !nb ? (
            <Vide icone={IconBook}>Aucun livre terminé en {annee} — ajoute ta première lecture !</Vide>
          ) : (
            <Stack gap="md">
              {mois.map(({ m, livres }) => (
                <Box key={m}>
                  <Text fz={11} fw={700} c="dimmed" tt="uppercase" lts={0.5} mb={4} px={4}>
                    {MOIS_FR[m - 1]} · {livres.length} livre{livres.length > 1 ? 's' : ''}
                  </Text>
                  <Stack gap={2}>{livres.map(l => <LigneLivre key={l.id} l={l} />)}</Stack>
                </Box>
              ))}
            </Stack>
          )}
        </Carte>
      </Grid.Col>
    </Grid>
  );
}
