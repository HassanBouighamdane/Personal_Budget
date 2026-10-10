/* Lectures — pièces partagées par le journal et la liste à lire : ISBN, couverture, notes et citations */
import { useState } from 'react';
import {
  ActionIcon, Badge, Box, Button, Group, Image, NumberInput, SegmentedControl, Stack, Text, Textarea, TextInput, Tooltip,
} from '@mantine/core';
import { modals } from '@mantine/modals';
import { IconNotes, IconPencil, IconQuote, IconSearch } from '@tabler/icons-react';

import { api } from '../../lib/api';
import type { FicheIsbn, NoteLecture } from '../../lib/types';
import { useEcriture, useNotes } from '../../lib/queries';
import { BoutonSuppr, Chargement, confirmer, Vide } from '../../components/ui';

/** Champ ISBN avec recherche Open Library : `onFiche` reçoit titre, auteur, pages et couverture */
export function ChampIsbn({ value, onChange, onFiche }: { value: string; onChange: (v: string) => void; onFiche: (f: FicheIsbn) => void }) {
  const [recherche, setRecherche] = useState(false);
  async function chercher() {
    if (!value.trim()) return;
    setRecherche(true);
    try {
      onFiche(await api<FicheIsbn>('/api/lectures/isbn/' + encodeURIComponent(value.trim())));
    } catch { /* message déjà affiché */ } finally { setRecherche(false); }
  }
  return (
    <TextInput label="ISBN (optionnel)" placeholder="ex : 978-2-07-036002-4" value={value}
               description="Remplit titre, auteur, pages et couverture depuis Open Library"
               onChange={e => onChange(e.currentTarget.value)}
               onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); chercher(); } }}
               rightSectionWidth={92}
               rightSection={<Button size="compact-xs" variant="light" leftSection={<IconSearch size={12} />} loading={recherche}
                                     onClick={chercher} disabled={!value.trim()}>Chercher</Button>} />
  );
}

/** Vignette de couverture ; masquée si l'image n'existe pas */
export function Couverture({ url, largeur = 34 }: { url: string; largeur?: number }) {
  const [erreur, setErreur] = useState(false);
  if (!url || erreur) return null;
  return <Image src={url} w={largeur} h={largeur * 1.5} radius="sm" fit="cover" alt="" onError={() => setErreur(true)}
                style={{ flexShrink: 0 }} />;
}

/* ---------- Notes et citations ---------- */
type Cible = { livre_id: number } | { a_lire_id: number };

function FormNote({ cible, note, onTermine }: { cible: Cible; note?: NoteLecture; onTermine?: () => void }) {
  const ecrire = useEcriture('lectures');
  const [type, setType] = useState<'note' | 'citation'>(note?.type ?? 'note');
  const [texte, setTexte] = useState(note?.texte ?? '');
  const [page, setPage] = useState<string | number>(note?.page ?? '');

  function enregistrer() {
    if (!texte.trim()) return;
    const p = typeof page === 'number' ? page : parseInt(page);
    const body = { ...cible, type, texte: texte.trim(), page: p > 0 ? p : null };
    ecrire.mutate(
      note ? { path: `/api/lectures/notes/${note.id}`, method: 'PUT', body, succes: 'Note modifiée ✓' }
           : { path: '/api/lectures/notes', method: 'POST', body, succes: type === 'citation' ? 'Citation ajoutée ✓' : 'Note ajoutée ✓' },
      { onSuccess: () => { if (!note) { setTexte(''); setPage(''); } onTermine?.(); } },
    );
  }

  return (
    <Stack gap="xs">
      <Group gap="xs" wrap="nowrap" align="flex-end">
        <SegmentedControl size="xs" value={type} onChange={v => setType(v as typeof type)}
                          data={[{ value: 'note', label: 'Note' }, { value: 'citation', label: 'Citation' }]} />
        <NumberInput size="xs" w={90} placeholder="Page" min={1} allowDecimal={false} allowNegative={false} value={page} onChange={setPage}
                     aria-label="Page" />
      </Group>
      <Textarea placeholder={type === 'citation' ? 'La phrase, telle quelle…' : 'Ce que tu en retiens…'} autosize minRows={2} maxRows={8}
                value={texte} onChange={e => setTexte(e.currentTarget.value)} />
      <Group gap="xs">
        <Button size="xs" onClick={enregistrer} loading={ecrire.isPending} disabled={!texte.trim()}>{note ? 'Enregistrer' : 'Ajouter'}</Button>
        {note && <Button size="xs" variant="default" onClick={onTermine}>Annuler</Button>}
      </Group>
    </Stack>
  );
}

function ListeNotes({ cible }: { cible: Cible }) {
  const filtre = 'livre_id' in cible ? `livre_id=${cible.livre_id}` : `a_lire_id=${cible.a_lire_id}`;
  const { data: notes, isPending } = useNotes(filtre);
  const ecrire = useEcriture('lectures');
  const [edition, setEdition] = useState<number | null>(null);

  return (
    <Stack gap="md">
      {isPending ? <Chargement lignes={2} /> : !notes?.length ? (
        <Vide icone={IconNotes}>Aucune note pour l'instant. Garde ici ce que tu retiens, ou une citation avec sa page.</Vide>
      ) : (
        <Stack gap="sm">
          {notes.map(n => edition === n.id ? (
            <FormNote key={n.id} cible={cible} note={n} onTermine={() => setEdition(null)} />
          ) : (
            <Group key={n.id} gap="sm" wrap="nowrap" align="flex-start" className="ligne-op" px={6} py={6}>
              {n.type === 'citation' ? <IconQuote size={16} style={{ flexShrink: 0, marginTop: 3 }} /> : <IconNotes size={16} style={{ flexShrink: 0, marginTop: 3 }} />}
              <Box style={{ flex: 1, minWidth: 0 }}>
                <Text fz="sm" fs={n.type === 'citation' ? 'italic' : undefined} style={{ whiteSpace: 'pre-wrap' }}>
                  {n.type === 'citation' ? `« ${n.texte} »` : n.texte}
                </Text>
                {n.page && <Badge size="xs" variant="light" color="gray" mt={4}>p. {n.page}</Badge>}
              </Box>
              <Tooltip label="Modifier" withArrow>
                <ActionIcon variant="subtle" color="gray" onClick={() => setEdition(n.id)} aria-label="Modifier" className="suppr">
                  <IconPencil size={16} stroke={1.7} />
                </ActionIcon>
              </Tooltip>
              <BoutonSuppr onClick={() => confirmer('Supprimer cette note ?', () =>
                ecrire.mutate({ path: `/api/lectures/notes/${n.id}`, method: 'DELETE', succes: 'Note supprimée' }))} />
            </Group>
          ))}
        </Stack>
      )}
      <FormNote cible={cible} />
    </Stack>
  );
}

export function ouvrirNotes(titre: string, cible: Cible) {
  modals.open({ title: <Text fw={650}>Notes — {titre}</Text>, size: 'lg', centered: true, children: <ListeNotes cible={cible} /> });
}

/** Bouton « Notes » avec leur nombre */
export function BoutonNotes({ nb, onClick }: { nb: number; onClick: () => void }) {
  return (
    <Tooltip label="Notes et citations" withArrow>
      <ActionIcon variant="subtle" color={nb ? 'marque' : 'gray'} onClick={onClick} aria-label="Notes et citations" className={nb ? undefined : 'suppr'}
                  w="auto" px={4}>
        <Group gap={2} wrap="nowrap">
          <IconNotes size={16} stroke={1.7} />
          {nb > 0 && <Text fz={11} fw={700}>{nb}</Text>}
        </Group>
      </ActionIcon>
    </Tooltip>
  );
}
