/* Lectures — objectifs (annuel, mensuel) et genres */
import { useEffect, useState } from 'react';
import { ActionIcon, Button, Divider, Grid, Group, NumberInput, Stack, Text, TextInput, Tooltip } from '@mantine/core';
import { IconCategory, IconDeviceFloppy, IconPlus, IconTarget } from '@tabler/icons-react';

import { toast } from '../../lib/api';
import type { Genre } from '../../lib/types';
import { useEcriture, useGenres, useObjectifsLecture } from '../../lib/queries';
import { BoutonSuppr, Carte, Chargement, confirmer, Info, Pastille, Vide } from '../../components/ui';

const entier = (v: string | number) => (typeof v === 'number' ? v : parseInt(v)) || 0;

function LigneGenre({ g }: { g: Genre }) {
  const ecrire = useEcriture('lectures');
  const [nom, setNom] = useState(g.nom);
  const modifie = nom !== g.nom;
  return (
    <Group gap="xs" wrap="nowrap">
      <TextInput value={nom} onChange={e => setNom(e.currentTarget.value)} style={{ flex: 1 }} aria-label="Nom du genre" />
      <Tooltip label="Enregistrer" withArrow>
        <ActionIcon variant={modifie ? 'filled' : 'default'} size="lg" loading={ecrire.isPending} aria-label="Enregistrer"
          onClick={() => nom.trim()
            ? ecrire.mutate({ path: '/api/lectures/genres/' + g.id, method: 'PUT', body: { nom: nom.trim() }, succes: 'Genre mis à jour ✓' })
            : toast('Nom requis', false)}>
          <IconDeviceFloppy size={16} />
        </ActionIcon>
      </Tooltip>
      <BoutonSuppr label="Retirer" onClick={() => confirmer('Retirer ce genre de la liste ? (les livres déjà saisis le gardent)',
        () => ecrire.mutate({ path: '/api/lectures/genres/' + g.id, method: 'DELETE', succes: 'Genre retiré' }), 'Retirer')} />
    </Group>
  );
}

export function ParametresLectures() {
  const { data: objectifs } = useObjectifsLecture();
  const { data: genres, isPending } = useGenres();
  const ecrire = useEcriture('lectures');
  const [annuel, setAnnuel] = useState<string | number>('');
  const [mensuel, setMensuel] = useState<string | number>('');
  const [nouveau, setNouveau] = useState('');

  useEffect(() => {
    if (objectifs) { setAnnuel(objectifs.annuel); setMensuel(objectifs.mensuel); }
  }, [objectifs?.annuel, objectifs?.mensuel]);

  function ajouterGenre() {
    const nom = nouveau.trim();
    if (!nom) return toast('Nom requis', false);
    ecrire.mutate({ path: '/api/lectures/genres', method: 'POST', body: { nom }, succes: 'Genre ajouté ✓' },
      { onSuccess: () => setNouveau('') });
  }

  return (
    <Grid gap="lg" align="flex-start">
      <Grid.Col span={{ base: 12, md: 5 }}>
        <Carte titre="Objectifs de lecture" description="Nombre de livres à terminer" icone={<Pastille icone={IconTarget} couleur="emeraude" />}>
          <Stack gap="sm">
            <NumberInput label="Par an" value={annuel} onChange={setAnnuel} min={0} allowNegative={false} allowDecimal={false} rightSection="livres" rightSectionWidth={56} />
            <NumberInput label="Par mois" value={mensuel} onChange={setMensuel} min={0} allowNegative={false} allowDecimal={false} rightSection="livres" rightSectionWidth={56} />
            <Button mt="xs" loading={ecrire.isPending} style={{ alignSelf: 'flex-start' }}
              onClick={() => ecrire.mutate({ path: '/api/lectures/objectifs', method: 'PUT', succes: 'Objectifs enregistrés ✓',
                body: { annuel: entier(annuel), mensuel: entier(mensuel) } })}>
              Enregistrer
            </Button>
            <Info>Mets 0 pour ne pas suivre un objectif. Ils s'appliquent à toutes les années du bilan.</Info>
          </Stack>
        </Carte>
      </Grid.Col>
      <Grid.Col span={{ base: 12, md: 7 }}>
        <Carte titre="Genres" description="Proposés dans le formulaire ; renommer met à jour les livres déjà saisis"
               icone={<Pastille icone={IconCategory} couleur="marque" />}>
          {isPending ? <Chargement /> : !genres?.length ? <Vide>Aucun genre configuré</Vide> : (
            <Stack gap="xs">
              {/* key incluant le nom : la ligne se réinitialise après un rechargement */}
              {genres.map(g => <LigneGenre key={`${g.id}|${g.nom}`} g={g} />)}
            </Stack>
          )}
          <Divider my="md" color="var(--bordure-douce)" />
          <Text fz="xs" fw={700} c="dimmed" tt="uppercase" lts={0.5} mb={8}>Ajouter un genre</Text>
          <Group gap="xs" wrap="nowrap">
            <TextInput placeholder="ex : Science-fiction" value={nouveau} onChange={e => setNouveau(e.currentTarget.value)}
                       onKeyDown={e => { if (e.key === 'Enter') ajouterGenre(); }} style={{ flex: 1 }} />
            <ActionIcon size={36} onClick={ajouterGenre} aria-label="Ajouter le genre"><IconPlus size={18} /></ActionIcon>
          </Group>
        </Carte>
      </Grid.Col>
    </Grid>
  );
}
