/* Lectures — livres en cours et liste à lire. « Terminé » ouvre le formulaire du journal pré-rempli :
 * le livre y passe avec ses notes et citations. */
import { useState, type ReactNode } from 'react';
import {
  ActionIcon, Autocomplete, Badge, Box, Button, Grid, Group, NumberInput, Progress, Select, SimpleGrid, Stack, Text, Textarea, TextInput, Tooltip,
} from '@mantine/core';
import { modals } from '@mantine/modals';
import { IconBookmark, IconCheck, IconFlame, IconPencil, IconPlayerPlay, IconPlayerStop, IconProgressCheck } from '@tabler/icons-react';

import { toast } from '../../lib/api';
import { auj, dateFr } from '../../lib/format';
import type { ALire } from '../../lib/types';
import { useALire, useAuteurs, useEcriture, useGenres, useSerieLecture } from '../../lib/queries';
import { BoutonSuppr, Carte, Chargement, confirmer, Pastille, Vide } from '../../components/ui';
import { BoutonNotes, ChampIsbn, Couverture, ouvrirNotes } from './communs';
import { FormLivre } from './Journal';

const corps = (a: ALire) => ({
  titre: a.titre, auteur: a.auteur, genre: a.genre, pages: a.pages, isbn: a.isbn, couverture: a.couverture,
  commentaire: a.commentaire, date_debut: a.date_debut,
});

function FormALire({ existant, onTermine }: { existant?: ALire; onTermine?: () => void }) {
  const ecrire = useEcriture('lectures');
  const { data: genres } = useGenres();
  const { data: auteurs } = useAuteurs();
  const [isbn, setIsbn] = useState(existant?.isbn ?? '');
  const [couverture, setCouverture] = useState(existant?.couverture ?? '');
  const [titre, setTitre] = useState(existant?.titre ?? '');
  const [auteur, setAuteur] = useState(existant?.auteur ?? '');
  const [genre, setGenre] = useState<string | null>(existant?.genre || null);
  const [pages, setPages] = useState<string | number>(existant?.pages ?? '');
  const [commentaire, setCommentaire] = useState(existant?.commentaire ?? '');
  const nomsGenres = [...new Set([...(genres ?? []).map(g => g.nom), ...(existant?.genre ? [existant.genre] : [])])];

  function enregistrer() {
    if (!titre.trim()) return toast('Indique le titre', false);
    const p = typeof pages === 'number' ? pages : parseInt(pages);
    const body = {
      titre: titre.trim(), auteur: auteur.trim(), genre: genre ?? '', pages: p > 0 ? p : null, isbn: isbn.trim(), couverture,
      commentaire: commentaire.trim(), date_debut: existant?.date_debut ?? null,
    };
    ecrire.mutate(
      existant ? { path: `/api/lectures/a_lire/${existant.id}`, method: 'PUT', body, succes: 'Livre modifié ✓' }
               : { path: '/api/lectures/a_lire', method: 'POST', body, succes: 'Ajouté à ta liste ✓' },
      {
        onSuccess: () => {
          if (!existant) { setIsbn(''); setCouverture(''); setTitre(''); setAuteur(''); setGenre(null); setPages(''); setCommentaire(''); }
          onTermine?.();
        },
      },
    );
  }

  return (
    <Stack gap="sm">
      <Group gap="sm" wrap="nowrap" align="flex-start">
        <Box style={{ flex: 1 }}>
          <ChampIsbn value={isbn} onChange={setIsbn} onFiche={f => {
            setIsbn(f.isbn); setTitre(f.titre); setCouverture(f.couverture);
            if (f.auteur) setAuteur(f.auteur);
            if (f.pages) setPages(f.pages);
          }} />
        </Box>
        <Couverture url={couverture} largeur={48} />
      </Group>
      <TextInput label="Titre" placeholder="ex : Sapiens" value={titre} onChange={e => setTitre(e.currentTarget.value)} />
      <SimpleGrid cols={{ base: 1, xs: 2 }} spacing="sm">
        <Autocomplete label="Auteur" data={auteurs ?? []} value={auteur} onChange={setAuteur} limit={20} />
        <Select label="Genre" placeholder="— Choisir —" data={nomsGenres} value={genre} onChange={setGenre} searchable clearable />
      </SimpleGrid>
      <NumberInput label="Pages (optionnel)" min={1} allowNegative={false} allowDecimal={false} value={pages} onChange={setPages} />
      <Textarea label="Pourquoi le lire (optionnel)" placeholder="Conseillé par…, pour…" autosize minRows={1} maxRows={4}
                value={commentaire} onChange={e => setCommentaire(e.currentTarget.value)} />
      <Button mt="xs" onClick={enregistrer} loading={ecrire.isPending}>{existant ? 'Enregistrer' : 'Ajouter à la liste'}</Button>
    </Stack>
  );
}

/** Page atteinte aujourd'hui : une saisie par jour, la dernière remplace la précédente */
function FormProgression({ a, onTermine }: { a: ALire; onTermine: () => void }) {
  const ecrire = useEcriture('lectures');
  const [page, setPage] = useState<string | number>(a.page_actuelle ?? '');
  function enregistrer() {
    const p = typeof page === 'number' ? page : parseInt(page);
    if (isNaN(p) || p < 0) return toast('Indique la page', false);
    ecrire.mutate({ path: `/api/lectures/a_lire/${a.id}/progression`, method: 'PUT', body: { page: p },
                    succes: a.pages && p >= a.pages ? 'Dernière page ! Pense à le marquer terminé ✓' : 'Page notée ✓' },
                  { onSuccess: onTermine });
  }
  return (
    <Stack gap="sm">
      <NumberInput label="Page où tu en es" description={a.pages ? `sur ${a.pages} pages` : undefined} min={0} max={a.pages ?? undefined}
                   allowNegative={false} allowDecimal={false} value={page} onChange={setPage} data-autofocus
                   onKeyDown={e => { if (e.key === 'Enter') enregistrer(); }} />
      <Button onClick={enregistrer} loading={ecrire.isPending}>Enregistrer</Button>
    </Stack>
  );
}

/** Avancement d'un livre en cours : barre, rythme et fin estimée */
function Avancement({ a }: { a: ALire }) {
  if (a.page_actuelle === null) return null;
  const infos = [
    a.pages ? `p. ${a.page_actuelle} / ${a.pages}` : `p. ${a.page_actuelle}`,
    a.pages_par_jour ? `${String(a.pages_par_jour).replace('.', ',')} p. / jour` : '',
    a.fin_estimee ? `fin vers le ${dateFr(a.fin_estimee, false)}` : '',
  ].filter(Boolean).join(' · ');
  return (
    <Box mt={6}>
      {a.pages && <Progress value={Math.min(100, a.page_actuelle / a.pages * 100)} color="emeraude" size={6} radius="xl" mb={3} />}
      <Text fz="xs" c="dimmed">{infos}</Text>
    </Box>
  );
}

function BadgeSerie() {
  const { data } = useSerieLecture();
  if (!data || (!data.serie && !data.record)) return null;
  return (
    <Tooltip withArrow multiline w={230} label={
      (data.serie ? (data.lu_aujourdhui ? "Tu as lu aujourd'hui." : "Note ta page aujourd'hui pour continuer la série.") : 'Série interrompue.')
      + ` Record : ${data.record} jour${data.record > 1 ? 's' : ''}.`}>
      <Badge variant="light" color={data.serie ? (data.lu_aujourdhui ? 'ambre' : 'gray') : 'gray'} leftSection={<IconFlame size={12} stroke={2} />}>
        {data.serie} jour{data.serie > 1 ? 's' : ''} de suite
      </Badge>
    </Tooltip>
  );
}

function LigneALire({ a }: { a: ALire }) {
  const ecrire = useEcriture('lectures');
  const enCours = !!a.date_debut;
  const details = [a.auteur, a.genre, a.pages ? `${a.pages} pages` : ''].filter(Boolean).join(' · ');

  const ouvrir = (titre: string, contenu: (fermer: () => void) => ReactNode, taille?: string) => {
    const id = modals.open({ title: <Text fw={650}>{titre}</Text>, size: taille, centered: true, children: contenu(() => modals.close(id)) });
  };

  return (
    <Group className="ligne-op" wrap="nowrap" gap="sm" px={6} py={8} align="flex-start">
      {a.couverture ? <Couverture url={a.couverture} /> : <Pastille icone={IconBookmark} couleur={enCours ? 'emeraude' : 'gray'} taille={34} />}
      <Box style={{ flex: 1, minWidth: 0 }}>
        <Text fz="sm" fw={600} truncate>{a.titre}</Text>
        {details && <Text fz="xs" c="dimmed" truncate>{details}</Text>}
        {a.commentaire && <Text fz="xs" c="dimmed" fs="italic" lineClamp={2} mt={2}>{a.commentaire}</Text>}
        {enCours && a.page_actuelle === null && <Badge size="xs" variant="light" color="emeraude" mt={4}>commencé le {dateFr(a.date_debut!, false)}</Badge>}
        {enCours && <Avancement a={a} />}
      </Box>
      <Group gap={0} wrap="nowrap">
        {enCours && (
          <Tooltip label="Noter ma page" withArrow>
            <ActionIcon variant="subtle" color="emeraude" aria-label="Noter ma page"
                        onClick={() => ouvrir(a.titre, fermer => <FormProgression a={a} onTermine={fermer} />, 'sm')}>
              <IconProgressCheck size={17} stroke={1.7} />
            </ActionIcon>
          </Tooltip>
        )}
        <BoutonNotes nb={a.nb_notes} onClick={() => ouvrirNotes(a.titre, { a_lire_id: a.id })} />
        {enCours ? (
          <Tooltip label="Remettre dans la liste à lire" withArrow>
            <ActionIcon variant="subtle" color="gray" className="suppr" aria-label="Remettre dans la liste à lire"
                        onClick={() => ecrire.mutate({ path: `/api/lectures/a_lire/${a.id}`, method: 'PUT', body: { ...corps(a), date_debut: null } })}>
              <IconPlayerStop size={16} stroke={1.7} />
            </ActionIcon>
          </Tooltip>
        ) : (
          <Tooltip label="Commencer aujourd'hui" withArrow>
            <ActionIcon variant="subtle" color="emeraude" aria-label="Commencer"
                        onClick={() => ecrire.mutate({ path: `/api/lectures/a_lire/${a.id}`, method: 'PUT', body: { ...corps(a), date_debut: auj() }, succes: 'Bonne lecture !' })}>
              <IconPlayerPlay size={16} stroke={1.7} />
            </ActionIcon>
          </Tooltip>
        )}
        <Tooltip label="Terminé : l'ajouter au journal" withArrow>
          <ActionIcon variant="subtle" color="marque" aria-label="Terminé"
                      onClick={() => ouvrir(`Terminé : ${a.titre}`, fermer => <FormLivre depuis={a} onTermine={fermer} />, 'lg')}>
            <IconCheck size={16} stroke={1.9} />
          </ActionIcon>
        </Tooltip>
        <Tooltip label="Modifier" withArrow>
          <ActionIcon variant="subtle" color="gray" className="suppr" aria-label="Modifier"
                      onClick={() => ouvrir('Modifier', fermer => <FormALire existant={a} onTermine={fermer} />)}>
            <IconPencil size={16} stroke={1.7} />
          </ActionIcon>
        </Tooltip>
        <BoutonSuppr onClick={() => confirmer(`Retirer « ${a.titre} » de ta liste ?${a.nb_notes ? ' Ses notes seront supprimées.' : ''}`, () =>
          ecrire.mutate({ path: `/api/lectures/a_lire/${a.id}`, method: 'DELETE', succes: 'Retiré de la liste' }))} />
      </Group>
    </Group>
  );
}

export function ListeALire() {
  const { data, isPending } = useALire();
  const enCours = (data ?? []).filter(a => a.date_debut);
  const aLire = (data ?? []).filter(a => !a.date_debut);

  return (
    <Grid gap="lg" align="flex-start">
      <Grid.Col span={{ base: 12, md: 5 }}>
        <Carte className="colle" titre="Livre à lire" description="Avec l'ISBN, le reste se remplit tout seul"
               icone={<Pastille icone={IconBookmark} couleur="marque" />}>
          <FormALire />
        </Carte>
      </Grid.Col>
      <Grid.Col span={{ base: 12, md: 7 }}>
        <Stack gap="lg">
          <Carte titre="En cours" description={enCours.length ? `${enCours.length} livre${enCours.length > 1 ? 's' : ''} · note ta page pour suivre ton rythme` : undefined}
                 droite={<BadgeSerie />}>
            {isPending ? <Chargement lignes={2} /> : !enCours.length
              ? <Vide icone={IconPlayerPlay}>Aucune lecture en cours : lance un livre de ta liste avec ▶</Vide>
              : <Stack gap={2}>{enCours.map(a => <LigneALire key={a.id} a={a} />)}</Stack>}
          </Carte>
          <Carte titre="À lire" description={aLire.length ? `${aLire.length} livre${aLire.length > 1 ? 's' : ''}` : undefined}>
            {isPending ? <Chargement lignes={3} /> : !aLire.length
              ? <Vide icone={IconBookmark}>Ta liste est vide — ajoute un livre qui te fait envie</Vide>
              : <Stack gap={2}>{aLire.map(a => <LigneALire key={a.id} a={a} />)}</Stack>}
          </Carte>
        </Stack>
      </Grid.Col>
    </Grid>
  );
}
