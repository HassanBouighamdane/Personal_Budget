/* Suivi — objectifs d'épargne par projet (voyage, fonds d'urgence, voiture) : un montant cible, une date limite
 * facultative, et l'argent mis de côté au fil des versements. L'argent reste dans les liquidités : il est réservé,
 * pas dépensé. */
import { useState, type ReactNode } from 'react';
import {
  ActionIcon, Badge, Box, Button, Grid, Group, Progress, SegmentedControl, SimpleGrid, Stack, Text, TextInput, Tooltip,
} from '@mantine/core';
import { DatePickerInput } from '@mantine/dates';
import { modals } from '@mantine/modals';
import { IconArchive, IconArchiveOff, IconCheck, IconPencil, IconPigMoney, IconTarget, IconWallet } from '@tabler/icons-react';

import { toast } from '../../lib/api';
import { auj, dateFr, fmt, libelleMois, lireMontant } from '../../lib/format';
import { T } from '../../lib/palette';
import type { Projet } from '../../lib/types';
import { useEcriture, useObjectifs, usePatrimoineSilencieux } from '../../lib/queries';
import { ChampDate, ChampMontant } from '../../components/champs';
import { Aide, BoutonSuppr, Carte, Chargement, confirmer, Kpi, Pastille, Vide } from '../../components/ui';

const texte = (n: number) => String(n).replace('.', ',');
const pct = (v: number) => Math.round(v * 100) + ' %';

function ouvrir(titre: string, contenu: (fermer: () => void) => ReactNode) {
  const id = modals.open({ title: <Text fw={650}>{titre}</Text>, centered: true, children: contenu(() => modals.close(id)) });
}

/** Corps de PUT /api/objectifs/{id} : l'objectif tel quel, avec les changements donnés */
const corps = (o: Projet, changements: Partial<Projet> = {}) => {
  const x = { ...o, ...changements };
  return { nom: x.nom, cible: x.cible, date_limite: x.date_limite, note: x.note, archive: x.archive };
};

function FormObjectif({ existant, onTermine }: { existant?: Projet; onTermine?: () => void }) {
  const ecrire = useEcriture('carnet');
  const [nom, setNom] = useState(existant?.nom ?? '');
  const [cible, setCible] = useState(existant ? texte(existant.cible) : '');
  const [limite, setLimite] = useState<string | null>(existant?.date_limite ?? null);
  const [note, setNote] = useState(existant?.note ?? '');

  function enregistrer() {
    const c = lireMontant(cible);
    if (!nom.trim()) return toast("Indique le nom de l'objectif", false);
    if (isNaN(c) || c <= 0) return toast('Montant cible invalide', false);
    const body = { nom: nom.trim(), cible: c, date_limite: limite, note: note.trim(), archive: existant?.archive ?? false };
    ecrire.mutate(
      existant ? { path: `/api/objectifs/${existant.id}`, method: 'PUT', body, succes: 'Objectif modifié ✓' }
               : { path: '/api/objectifs', method: 'POST', body, succes: 'Objectif créé ✓' },
      { onSuccess: () => { if (!existant) { setNom(''); setCible(''); setLimite(null); setNote(''); } onTermine?.(); } },
    );
  }

  return (
    <Stack gap="sm">
      <TextInput label="Nom" placeholder="ex : voyage en Turquie, fonds d'urgence, voiture" value={nom}
                 onChange={e => setNom(e.currentTarget.value)} maxLength={100} />
      <SimpleGrid cols={{ base: 1, xs: 2 }} spacing="sm">
        <ChampMontant label="Montant visé" value={cible} onChange={setCible} />
        <DatePickerInput label="Pour le" placeholder="Optionnel" value={limite} onChange={setLimite} clearable
                         valueFormat="DD/MM/YYYY" minDate={existant ? undefined : auj()} popoverProps={{ withinPortal: true }} />
      </SimpleGrid>
      <TextInput label="Note (optionnel)" value={note} onChange={e => setNote(e.currentTarget.value)} maxLength={1000} />
      <Button mt="xs" onClick={enregistrer} loading={ecrire.isPending}>{existant ? 'Enregistrer' : "Créer l'objectif"}</Button>
    </Stack>
  );
}

/** Versements d'un objectif : liste, suppression et ajout (mettre de côté ou reprendre) */
function Versements({ id }: { id: number }) {
  const { data } = useObjectifs();
  const ecrire = useEcriture('carnet');
  const o = data?.find(x => x.id === id);
  const [sens, setSens] = useState<'mettre' | 'reprendre'>('mettre');
  const [date, setDate] = useState(auj());
  const [montant, setMontant] = useState('');
  const [libelle, setLibelle] = useState('');
  if (!o) return <Chargement lignes={2} />;

  function enregistrer() {
    const m = lireMontant(montant);
    if (isNaN(m) || m <= 0) return toast('Montant invalide', false);
    if (sens === 'reprendre' && m > o!.verse) return toast(`Il n'y a que ${fmt(o!.verse)} de côté`, false);
    const signe = sens === 'mettre' ? 1 : -1;
    const atteint = sens === 'mettre' && !o!.atteint && o!.verse + m >= o!.cible;
    ecrire.mutate({ path: `/api/objectifs/${id}/versements`, method: 'POST',
                    body: { date_operation: date, montant: signe * m, libelle: libelle.trim() },
                    succes: atteint ? 'Objectif atteint 🎉' : sens === 'mettre' ? 'Mis de côté ✓' : 'Argent repris ✓' },
                  { onSuccess: () => { setMontant(''); setLibelle(''); } });
  }

  return (
    <Stack gap="md">
      <Group justify="space-between" align="flex-end">
        <Box>
          <Text fz="xs" c="dimmed">{o.atteint ? 'Objectif atteint' : 'Il manque'}</Text>
          <Text className="chiffre" fz={22} fw={700} c={o.atteint ? T.ep : undefined}>{fmt(o.atteint ? o.verse : o.reste)}</Text>
        </Box>
        <Text fz="xs" c="dimmed">{fmt(o.verse)} sur {fmt(o.cible)}</Text>
      </Group>
      <Progress value={Math.min(100, o.progression * 100)} color="emeraude" size={8} radius="xl" />
      {o.versements.length > 0 && (
        <Stack gap={2}>
          {o.versements.map(v => (
            <Group key={v.id} className="ligne-op" wrap="nowrap" gap="sm" px={6} py={6}>
              <Text fz="sm" c="dimmed" style={{ whiteSpace: 'nowrap' }}>{dateFr(v.date_operation)}</Text>
              <Text fz="sm" truncate style={{ flex: 1, minWidth: 0 }}>{v.libelle}</Text>
              <Text fz="sm" fw={600} className="chiffre" c={v.montant < 0 ? T.dep : undefined}>
                {v.montant < 0 ? '−' : '+'}{fmt(Math.abs(v.montant))}
              </Text>
              <BoutonSuppr onClick={() => ecrire.mutate({ path: `/api/objectifs/versements/${v.id}`, method: 'DELETE', succes: 'Versement supprimé' })} />
            </Group>
          ))}
        </Stack>
      )}
      <Stack gap="sm">
        <SegmentedControl fullWidth value={sens} onChange={v => setSens(v as typeof sens)}
                          data={[{ value: 'mettre', label: 'Mettre de côté' }, { value: 'reprendre', label: 'Reprendre', disabled: o.verse <= 0 }]} />
        <SimpleGrid cols={{ base: 1, xs: 2 }} spacing="sm">
          <ChampDate value={date} onChange={setDate} />
          <ChampMontant label="Montant" placeholder={sens === 'mettre' && o.par_mois ? `${texte(o.par_mois)} (rythme conseillé)` : undefined}
                        value={montant} onChange={setMontant} />
        </SimpleGrid>
        <TextInput label="Note (optionnel)" placeholder={sens === 'mettre' ? 'ex : prime de fin d’année' : 'ex : acompte de l’hôtel'}
                   value={libelle} onChange={e => setLibelle(e.currentTarget.value)} maxLength={200} />
        <Button onClick={enregistrer} loading={ecrire.isPending} color={sens === 'mettre' ? undefined : 'rose'}>
          {sens === 'mettre' ? 'Mettre de côté' : "Reprendre l'argent"}
        </Button>
      </Stack>
    </Stack>
  );
}

function LigneObjectif({ o }: { o: Projet }) {
  const ecrire = useEcriture('carnet');
  const termine = o.atteint || o.archive;
  const rythme = o.par_mois !== null && o.date_limite
    ? `${fmt(o.par_mois)} par mois jusqu'en ${libelleMois(o.date_limite.slice(0, 7)).toLowerCase()}`
    : null;
  const details = [
    `${fmt(o.verse)} sur ${fmt(o.cible)}`,
    !o.atteint && !o.archive && o.date_limite && !o.en_retard ? `pour le ${dateFr(o.date_limite)}` : null,
    o.note || null,
  ].filter(Boolean).join(' · ');

  return (
    <Group className="ligne-op" wrap="nowrap" gap="sm" px={6} py={8} align="flex-start">
      <Pastille icone={o.atteint ? IconCheck : IconTarget} couleur={o.archive ? 'gray' : o.atteint ? 'emeraude' : 'marque'} taille={34} />
      <Box style={{ flex: 1, minWidth: 0 }}>
        <Group justify="space-between" wrap="nowrap" gap="xs">
          <Text fz="sm" fw={600} truncate c={o.archive ? 'dimmed' : undefined}>{o.nom}</Text>
          <Text fz="sm" fw={700} className="chiffre" c={o.atteint ? T.ep : undefined} style={{ whiteSpace: 'nowrap' }}>{pct(o.progression)}</Text>
        </Group>
        <Progress value={Math.min(100, o.progression * 100)} color={o.atteint ? 'emeraude' : o.en_retard ? 'ambre' : 'marque'} size={6} radius="xl" mt={6} />
        <Text fz="xs" c="dimmed" mt={4} lineClamp={2}>{details}</Text>
        {!termine && (rythme || o.en_retard) && (
          <Badge size="xs" variant="light" color={o.en_retard ? 'ambre' : 'gray'} mt={5} tt="none">
            {o.en_retard ? `date limite passée (${dateFr(o.date_limite!, false)}) · il manque ${fmt(o.reste)}` : rythme}
          </Badge>
        )}
      </Box>
      <Group gap={0} wrap="nowrap">
        <Tooltip label="Versements" withArrow>
          <ActionIcon variant="subtle" color={termine ? 'gray' : 'marque'} aria-label="Versements" className={termine ? 'suppr' : undefined}
                      onClick={() => ouvrir(o.nom, () => <Versements id={o.id} />)}>
            <IconPigMoney size={17} stroke={1.7} />
          </ActionIcon>
        </Tooltip>
        <Tooltip label="Modifier" withArrow>
          <ActionIcon variant="subtle" color="gray" className="suppr" aria-label="Modifier"
                      onClick={() => ouvrir('Modifier', fermer => <FormObjectif existant={o} onTermine={fermer} />)}>
            <IconPencil size={16} stroke={1.7} />
          </ActionIcon>
        </Tooltip>
        <Tooltip label={o.archive ? 'Remettre en cours' : 'Archiver (atteint ou abandonné)'} withArrow>
          <ActionIcon variant="subtle" color="gray" className="suppr" aria-label={o.archive ? 'Remettre en cours' : 'Archiver'}
                      onClick={() => ecrire.mutate({ path: `/api/objectifs/${o.id}`, method: 'PUT', body: corps(o, { archive: !o.archive }),
                                                     succes: o.archive ? 'Objectif remis en cours' : 'Objectif archivé' })}>
            {o.archive ? <IconArchiveOff size={16} stroke={1.7} /> : <IconArchive size={16} stroke={1.7} />}
          </ActionIcon>
        </Tooltip>
        <BoutonSuppr onClick={() => confirmer(`Supprimer « ${o.nom} »${o.versements.length ? ' et ses versements' : ''} ? L'argent reste dans tes liquidités.`, () =>
          ecrire.mutate({ path: `/api/objectifs/${o.id}`, method: 'DELETE', succes: 'Objectif supprimé' }))} />
      </Group>
    </Group>
  );
}

export function ObjectifsEpargne() {
  const { data, isPending } = useObjectifs();
  const { data: patrimoine } = usePatrimoineSilencieux();
  const [tousTermines, setTousTermines] = useState(false);
  const enCours = (data ?? []).filter(o => !o.archive);
  const termines = (data ?? []).filter(o => o.archive);
  const deCote = enCours.reduce((s, o) => s + o.verse, 0);
  const manque = enCours.reduce((s, o) => s + o.reste, 0);
  const parMois = enCours.reduce((s, o) => s + (o.par_mois ?? 0), 0);
  const libre = patrimoine ? patrimoine.liquidites - deCote : null;

  return (
    <Stack gap="lg">
      <SimpleGrid cols={{ base: 2, sm: 4 }} spacing={{ base: 'xs', sm: 'md' }}>
        <Kpi label="Mis de côté" valeur={fmt(deCote)} couleur={deCote ? T.ep : undefined} icone={IconPigMoney} teinte="emeraude"
             aide={`pour ${enCours.length} objectif${enCours.length > 1 ? 's' : ''} en cours`} />
        <Kpi label="Encore à épargner" valeur={fmt(manque)} icone={IconTarget} teinte="marque" aide="pour atteindre tous les objectifs en cours" />
        <Kpi label="Rythme à tenir" valeur={parMois ? fmt(parMois) : '—'} icone={IconTarget} teinte="ambre"
             aide={parMois ? 'par mois, pour tenir les dates limites' : 'aucune date limite à venir'} />
        <Kpi label="Liquidités libres" valeur={libre === null ? '…' : fmt(libre)} couleur={libre !== null && libre < 0 ? T.neg : undefined}
             icone={IconWallet} teinte="gray"
             aide={libre !== null && libre < 0 ? 'tu as réservé plus que tes liquidités' : 'liquidités non réservées à un objectif'} />
      </SimpleGrid>
      <Grid gap="lg" align="flex-start">
        <Grid.Col span={{ base: 12, md: 5 }}>
          <Carte className="colle" titre="Nouvel objectif" description="Un projet, un montant, et une date si tu en as une"
                 icone={<Pastille icone={IconTarget} couleur="marque" />}>
            <FormObjectif />
          </Carte>
        </Grid.Col>
        <Grid.Col span={{ base: 12, md: 7 }}>
          <Stack gap="lg">
            <Carte titre="En cours" description={enCours.length ? 'Les dates limites les plus proches en premier' : undefined}>
              {isPending ? <Chargement lignes={3} /> : !enCours.length
                ? <Vide icone={IconTarget}>Aucun objectif en cours : crée-en un pour ton prochain voyage ou ton fonds d'urgence</Vide>
                : <Stack gap={2}>{enCours.map(o => <LigneObjectif key={o.id} o={o} />)}</Stack>}
            </Carte>
            {termines.length > 0 && (
              <Carte titre="Archivés" description={`${termines.length} objectif${termines.length > 1 ? 's' : ''} atteint${termines.length > 1 ? 's' : ''} ou abandonné${termines.length > 1 ? 's' : ''}`}
                     droite={termines.length > 5 && <Button variant="subtle" size="compact-sm" onClick={() => setTousTermines(a => !a)}>{tousTermines ? 'Réduire' : 'Tout afficher'}</Button>}>
                <Stack gap={2}>{(tousTermines ? termines : termines.slice(0, 5)).map(o => <LigneObjectif key={o.id} o={o} />)}</Stack>
              </Carte>
            )}
            <Aide titre="L'argent reste dans tes liquidités">
              Mettre de côté ne sort pas l'argent de ton compte : il est seulement réservé à l'objectif. Ce n'est ni une dépense
              ni un transfert, ton patrimoine ne change pas. Quand tu dépenses pour le projet, saisis la dépense dans le Budget,
              puis « Reprendre » l'argent ici (ou archive l'objectif).
            </Aide>
          </Stack>
        </Grid.Col>
      </Grid>
    </Stack>
  );
}
