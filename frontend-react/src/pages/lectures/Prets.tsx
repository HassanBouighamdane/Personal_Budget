/* Lectures — livres prêtés : qui a quel livre, et depuis quand */
import { useState, type ReactNode } from 'react';
import { ActionIcon, Autocomplete, Badge, Box, Button, Grid, Group, Stack, Text, TextInput, Tooltip } from '@mantine/core';
import { modals } from '@mantine/modals';
import { IconArrowBackUp, IconPencil, IconUserShare } from '@tabler/icons-react';

import { toast } from '../../lib/api';
import { auj, dateFr } from '../../lib/format';
import type { PretLivre } from '../../lib/types';
import { useEcriture, usePretsLivres, useTitresLivres } from '../../lib/queries';
import { ChampDate } from '../../components/champs';
import { BoutonSuppr, Carte, Chargement, confirmer, Pastille, Vide } from '../../components/ui';

/** Durée lisible : 12 jours, 3 mois, 1 an */
function duree(jours: number): string {
  if (jours < 1) return "aujourd'hui";
  if (jours < 60) return `${jours} jour${jours > 1 ? 's' : ''}`;
  if (jours < 365) return `${Math.round(jours / 30.44)} mois`;
  const ans = Math.floor(jours / 365);
  return `${ans} an${ans > 1 ? 's' : ''}`;
}

const corps = (p: PretLivre) => ({ titre: p.titre, personne: p.personne, date_pret: p.date_pret, date_retour: p.date_retour, note: p.note });

function FormPret({ existant, onTermine }: { existant?: PretLivre; onTermine?: () => void }) {
  const ecrire = useEcriture('lectures');
  const { data: titres } = useTitresLivres();
  const { data: prets } = usePretsLivres();
  const [titre, setTitre] = useState(existant?.titre ?? '');
  const [personne, setPersonne] = useState(existant?.personne ?? '');
  const [date, setDate] = useState(existant?.date_pret ?? auj());
  const [note, setNote] = useState(existant?.note ?? '');
  const personnes = [...new Set((prets ?? []).map(p => p.personne))].sort((a, b) => a.localeCompare(b, 'fr'));

  function enregistrer() {
    if (!titre.trim()) return toast('Indique le livre', false);
    if (!personne.trim()) return toast('Indique la personne', false);
    if (existant?.date_retour && existant.date_retour < date) return toast('Le prêt ne peut pas suivre le retour', false);
    const body = { titre: titre.trim(), personne: personne.trim(), date_pret: date, date_retour: existant?.date_retour ?? null, note: note.trim() };
    ecrire.mutate(
      existant ? { path: `/api/lectures/prets/${existant.id}`, method: 'PUT', body, succes: 'Prêt modifié ✓' }
               : { path: '/api/lectures/prets', method: 'POST', body, succes: 'Prêt noté ✓' },
      { onSuccess: () => { if (!existant) { setTitre(''); setPersonne(''); setNote(''); } onTermine?.(); } },
    );
  }

  return (
    <Stack gap="sm">
      <Autocomplete label="Livre" placeholder="ex : Sapiens" data={titres ?? []} value={titre} onChange={setTitre} limit={20} />
      <Autocomplete label="Prêté à" placeholder="ex : Sara" data={personnes} value={personne} onChange={setPersonne} limit={20} />
      <ChampDate label="Depuis le" value={date} onChange={setDate} />
      <TextInput label="Note (optionnel)" placeholder="ex : à récupérer avant l'été" value={note} onChange={e => setNote(e.currentTarget.value)} maxLength={1000} />
      <Button mt="xs" onClick={enregistrer} loading={ecrire.isPending}>{existant ? 'Enregistrer' : 'Noter le prêt'}</Button>
    </Stack>
  );
}

function LignePret({ p }: { p: PretLivre }) {
  const ecrire = useEcriture('lectures');
  const rendu = !!p.date_retour;
  const ouvrir = (titre: string, contenu: (fermer: () => void) => ReactNode) => {
    const id = modals.open({ title: <Text fw={650}>{titre}</Text>, centered: true, children: contenu(() => modals.close(id)) });
  };
  return (
    <Group className="ligne-op" wrap="nowrap" gap="sm" px={6} py={8} align="flex-start">
      <Pastille icone={IconUserShare} couleur={rendu ? 'gray' : p.jours > 90 ? 'ambre' : 'marque'} taille={34} />
      <Box style={{ flex: 1, minWidth: 0 }}>
        <Text fz="sm" fw={600} truncate>{p.titre}</Text>
        <Text fz="xs" c="dimmed" truncate>
          {rendu ? `rendu par ${p.personne} le ${dateFr(p.date_retour!)}` : `chez ${p.personne} depuis le ${dateFr(p.date_pret)}`}
        </Text>
        {p.note && <Text fz="xs" c="dimmed" fs="italic" lineClamp={2} mt={2}>{p.note}</Text>}
        <Badge size="xs" variant="light" color={rendu ? 'gray' : p.jours > 90 ? 'ambre' : 'marque'} mt={4}>
          {rendu ? `gardé ${duree(p.jours)}` : `depuis ${duree(p.jours)}`}
        </Badge>
      </Box>
      <Group gap={0} wrap="nowrap">
        {rendu ? (
          <Tooltip label="Finalement pas rendu" withArrow>
            <ActionIcon variant="subtle" color="gray" className="suppr" aria-label="Finalement pas rendu"
                        onClick={() => ecrire.mutate({ path: `/api/lectures/prets/${p.id}`, method: 'PUT', body: { ...corps(p), date_retour: null } })}>
              <IconArrowBackUp size={16} stroke={1.7} style={{ transform: 'scaleX(-1)' }} />
            </ActionIcon>
          </Tooltip>
        ) : (
          <Tooltip label="Rendu aujourd'hui" withArrow>
            <ActionIcon variant="subtle" color="emeraude" aria-label="Rendu aujourd'hui"
                        onClick={() => ecrire.mutate({ path: `/api/lectures/prets/${p.id}`, method: 'PUT', body: { ...corps(p), date_retour: auj() }, succes: 'Livre récupéré ✓' })}>
              <IconArrowBackUp size={17} stroke={1.8} />
            </ActionIcon>
          </Tooltip>
        )}
        <Tooltip label="Modifier" withArrow>
          <ActionIcon variant="subtle" color="gray" className="suppr" aria-label="Modifier"
                      onClick={() => ouvrir('Modifier', fermer => <FormPret existant={p} onTermine={fermer} />)}>
            <IconPencil size={16} stroke={1.7} />
          </ActionIcon>
        </Tooltip>
        <BoutonSuppr onClick={() => confirmer(`Supprimer le prêt de « ${p.titre} » ?`, () =>
          ecrire.mutate({ path: `/api/lectures/prets/${p.id}`, method: 'DELETE', succes: 'Supprimé' }))} />
      </Group>
    </Group>
  );
}

export function LivresPretes() {
  const { data, isPending } = usePretsLivres();
  const [tous, setTous] = useState(false);
  const dehors = (data ?? []).filter(p => !p.date_retour);
  const rendus = (data ?? []).filter(p => p.date_retour);

  return (
    <Grid gap="lg" align="flex-start">
      <Grid.Col span={{ base: 12, md: 5 }}>
        <Carte className="colle" titre="Livre prêté" description="Pour savoir chez qui il est, et depuis quand"
               icone={<Pastille icone={IconUserShare} couleur="marque" />}>
          <FormPret />
        </Carte>
      </Grid.Col>
      <Grid.Col span={{ base: 12, md: 7 }}>
        <Stack gap="lg">
          <Carte titre="Chez quelqu'un" description={dehors.length ? `${dehors.length} livre${dehors.length > 1 ? 's' : ''}, le plus ancien prêt en premier` : undefined}>
            {isPending ? <Chargement lignes={3} /> : !dehors.length
              ? <Vide icone={IconUserShare}>Tous tes livres sont à la maison</Vide>
              : <Stack gap={2}>{dehors.map(p => <LignePret key={p.id} p={p} />)}</Stack>}
          </Carte>
          {rendus.length > 0 && (
            <Carte titre="Rendus" description={`${rendus.length} livre${rendus.length > 1 ? 's' : ''}`}
                   droite={rendus.length > 5 && <Button variant="subtle" size="compact-sm" onClick={() => setTous(t => !t)}>{tous ? 'Réduire' : 'Tout afficher'}</Button>}>
              <Stack gap={2}>{(tous ? rendus : rendus.slice(0, 5)).map(p => <LignePret key={p.id} p={p} />)}</Stack>
            </Carte>
          )}
        </Stack>
      </Grid.Col>
    </Grid>
  );
}
