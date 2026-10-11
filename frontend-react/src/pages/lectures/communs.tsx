/* Lectures — pièces partagées par le journal et la liste à lire : couverture, notes et citations */
import { useEffect, useState } from 'react';
import {
  ActionIcon, Badge, Box, Button, Checkbox, Group, Image, Modal, NumberInput, SegmentedControl, Stack, Text, Textarea, Tooltip,
} from '@mantine/core';
import { useMediaQuery } from '@mantine/hooks';
import { modals } from '@mantine/modals';
import { IconDownload, IconNotes, IconPencil, IconQuote, IconRefresh } from '@tabler/icons-react';

import { auj } from '../../lib/format';
import type { NoteDuJour as Note, NoteLecture } from '../../lib/types';
import { useEcriture, useNoteDuJour, useNotes } from '../../lib/queries';
import { BoutonSuppr, Chargement, confirmer, Vide } from '../../components/ui';

/** Téléphone : les boutons d'une ligne passent sous le texte, qui garde toute la largeur */
export const useMobile = () => useMediaQuery('(max-width: 47.99em)') ?? false;

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
      {!!notes?.length && (
        <Button component="a" href={'/api/lectures/notes/export?' + filtre} download variant="subtle" size="compact-sm" color="gray"
                leftSection={<IconDownload size={14} />} style={{ alignSelf: 'flex-start' }}>
          Exporter en Markdown
        </Button>
      )}
    </Stack>
  );
}

/** Texte de la note (citation en italique, entre guillemets) et son livre ; dir="auto" pour l'arabe */
function TexteNote({ note, taille = 'sm', lignes }: { note: Note; taille?: string; lignes?: number }) {
  const citation = note.type === 'citation';
  return (
    <>
      <Text fz={taille} lh={1.6} fs={citation ? 'italic' : undefined} lineClamp={lignes} style={{ whiteSpace: 'pre-wrap' }} dir="auto">
        {citation ? `« ${note.texte} »` : note.texte}
      </Text>
      <Text fz="xs" c="dimmed" mt={4} dir="auto">
        {[note.titre, note.auteur].filter(Boolean).join(' · ')}{note.page ? ` · p. ${note.page}` : ''}
      </Text>
    </>
  );
}

/** Une note ou citation tirée de tes lectures : la même toute la journée, « Une autre » en fait défiler */
export function NoteDuJour() {
  const [decalage, setDecalage] = useState(0);
  const { data: note } = useNoteDuJour(decalage);
  if (!note) return null;
  const citation = note.type === 'citation';
  return (
    <Group gap="sm" wrap="nowrap" align="flex-start" px="md" py="sm"
           style={{ borderRadius: 'var(--mantine-radius-lg)', border: '1px solid var(--bordure-douce)', borderLeft: '3px solid var(--c-brand)',
                    background: 'color-mix(in srgb, var(--c-brand) 6%, transparent)' }}>
      {citation ? <IconQuote size={18} style={{ flexShrink: 0, marginTop: 2, color: 'var(--c-brand)' }} />
                : <IconNotes size={18} style={{ flexShrink: 0, marginTop: 2, color: 'var(--c-brand)' }} />}
      <Box style={{ flex: 1, minWidth: 0 }}>
        <TexteNote note={note} lignes={6} />
      </Box>
      <Tooltip label="Une autre" withArrow>
        <ActionIcon variant="subtle" color="gray" aria-label="Une autre note" onClick={() => setDecalage(d => d + 1)}>
          <IconRefresh size={16} stroke={1.7} />
        </ActionIcon>
      </Tooltip>
    </Group>
  );
}

/* Fenêtre de la note du jour, à l'ouverture de l'application. « Ne plus l'afficher aujourd'hui » la masque
   jusqu'au lendemain sur cet appareil ; sinon elle revient à la prochaine ouverture (pas à chaque retour sur l'accueil). */
const CLE_MASQUEE = 'note-du-jour-masquee';
let vueCetteOuverture = false;

function masqueeAujourdhui() {
  try { return localStorage.getItem(CLE_MASQUEE) === auj(); } catch { return false; }
}

export function FenetreNoteDuJour() {
  const { data: note } = useNoteDuJour(0);
  const [ouverte, setOuverte] = useState(() => !vueCetteOuverture && !masqueeAujourdhui());
  const [masquer, setMasquer] = useState(false);
  useEffect(() => { if (note && ouverte) vueCetteOuverture = true; }, [note, ouverte]);

  function fermer() {
    if (masquer) {
      try { localStorage.setItem(CLE_MASQUEE, auj()); } catch { /* stockage indisponible : elle reviendra */ }
    }
    setOuverte(false);
  }

  if (!note) return null;
  const citation = note.type === 'citation';
  return (
    <Modal opened={ouverte} onClose={fermer} centered radius="lg"
           title={<Group gap={8}>
             {citation ? <IconQuote size={18} color="var(--c-brand)" /> : <IconNotes size={18} color="var(--c-brand)" />}
             <Text fw={650}>{citation ? 'Citation du jour' : 'Note du jour'}</Text>
           </Group>}>
      <Box pl="sm" style={{ borderLeft: '3px solid var(--c-brand)' }}>
        <TexteNote note={note} taille="md" />
      </Box>
      <Group justify="space-between" mt="lg" gap="sm">
        <Checkbox size="sm" label="Ne plus l'afficher aujourd'hui" checked={masquer} onChange={e => setMasquer(e.currentTarget.checked)} />
        <Button onClick={fermer}>Fermer</Button>
      </Group>
    </Modal>
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
