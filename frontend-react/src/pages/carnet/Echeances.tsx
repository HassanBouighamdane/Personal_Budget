/* Suivi — échéances : papiers, assurance, visite technique, vignette, garanties… avec un rappel avant la date.
 * Une échéance récurrente se reporte d'une période une fois traitée. Une échéance qui coûte (assurance, Aïd, rentrée)
 * peut avoir un montant et un objectif d'épargne qui la prépare mois après mois (« provision »). */
import { useState, type ReactNode } from 'react';
import { ActionIcon, Badge, Box, Button, Checkbox, Grid, Group, Progress, Select, SimpleGrid, Stack, Text, Textarea, TextInput, Tooltip } from '@mantine/core';
import { modals } from '@mantine/modals';
import { IconCalendarDue, IconCalendarEvent, IconCheck, IconPencil, IconPigMoney, IconRepeat } from '@tabler/icons-react';

import { toast } from '../../lib/api';
import { auj, dateFr, fmt, lireMontant } from '../../lib/format';
import type { Echeance } from '../../lib/types';
import { useEcheances, useEcriture } from '../../lib/queries';
import { ChampDate, ChampMontant } from '../../components/champs';
import { BoutonSuppr, Carte, Chargement, confirmer, Info, Pastille, Vide } from '../../components/ui';

const CATEGORIES = ['Papiers', 'Voiture', 'Assurance', 'Logement', 'Santé', 'Abonnement', 'Garantie', 'Impôts', 'Autre'];
const RAPPELS = [
  { value: '0', label: 'Le jour même' }, { value: '3', label: '3 jours avant' }, { value: '7', label: '1 semaine avant' },
  { value: '14', label: '2 semaines avant' }, { value: '30', label: '1 mois avant' }, { value: '60', label: '2 mois avant' },
  { value: '90', label: '3 mois avant' },
];
const RECURRENCES = [
  { value: '', label: 'Une seule fois' }, { value: '1', label: 'Tous les mois' }, { value: '3', label: 'Tous les 3 mois' },
  { value: '6', label: 'Tous les 6 mois' }, { value: '12', label: 'Tous les ans' }, { value: '24', label: 'Tous les 2 ans' },
];
const libelleRecurrence = (mois: number) =>
  RECURRENCES.find(r => r.value === String(mois))?.label.toLowerCase() ?? `tous les ${mois} mois`;

function delai(jours: number): string {
  if (jours < 0) return `en retard de ${-jours} jour${jours < -1 ? 's' : ''}`;
  if (jours === 0) return "aujourd'hui";
  if (jours === 1) return 'demain';
  if (jours < 60) return `dans ${jours} jours`;
  return `dans ${Math.round(jours / 30.44)} mois`;
}

function ouvrir(titre: string, contenu: (fermer: () => void) => ReactNode) {
  const id = modals.open({ title: <Text fw={650}>{titre}</Text>, centered: true, children: contenu(() => modals.close(id)) });
}

function FormEcheance({ existante, onTermine }: { existante?: Echeance; onTermine?: () => void }) {
  const ecrire = useEcriture('carnet');
  const [titre, setTitre] = useState(existante?.titre ?? '');
  const [categorie, setCategorie] = useState<string | null>(existante?.categorie || null);
  const [date, setDate] = useState(existante?.date_echeance ?? auj());
  const [rappel, setRappel] = useState(String(existante?.rappel_jours ?? 30));
  const [recurrence, setRecurrence] = useState(existante?.recurrence_mois ? String(existante.recurrence_mois) : '');
  const [note, setNote] = useState(existante?.note ?? '');
  const [montant, setMontant] = useState(existante?.montant ? String(existante.montant).replace('.', ',') : '');
  const [provisionner, setProvisionner] = useState(!!existante?.objectif_id);
  // Valeurs enregistrées hors des listes proposées (catégorie ancienne, délai personnalisé)
  const categories = [...new Set([...CATEGORIES, ...(existante?.categorie ? [existante.categorie] : [])])];
  const rappels = RAPPELS.some(r => r.value === rappel) ? RAPPELS : [...RAPPELS, { value: rappel, label: `${rappel} jours avant` }];
  const recurrences = RECURRENCES.some(r => r.value === recurrence) ? RECURRENCES : [...RECURRENCES, { value: recurrence, label: `Tous les ${recurrence} mois` }];

  function enregistrer() {
    if (!titre.trim()) return toast('Indique le titre', false);
    const m = montant.trim() ? lireMontant(montant) : null;
    if (m !== null && (isNaN(m) || m <= 0)) return toast('Montant invalide', false);
    const body = {
      titre: titre.trim(), categorie: categorie ?? '', date_echeance: date, rappel_jours: +rappel,
      recurrence_mois: recurrence ? +recurrence : null, note: note.trim(), montant: m, provisionner: provisionner && m !== null,
    };
    ecrire.mutate(
      existante ? { path: `/api/carnet/echeances/${existante.id}`, method: 'PUT', body, succes: 'Échéance modifiée ✓' }
                : { path: '/api/carnet/echeances', method: 'POST', body, succes: 'Échéance ajoutée ✓' },
      { onSuccess: () => { if (!existante) { setTitre(''); setNote(''); setMontant(''); setProvisionner(false); } onTermine?.(); } },
    );
  }

  return (
    <Stack gap="sm">
      <TextInput label="Quoi" placeholder="ex : Assurance voiture, passeport, visite technique" value={titre}
                 onChange={e => setTitre(e.currentTarget.value)} maxLength={150} />
      <SimpleGrid cols={{ base: 1, xs: 2 }} spacing="sm">
        <Select label="Catégorie" placeholder="— Choisir —" data={categories} value={categorie} onChange={setCategorie} clearable />
        <ChampDate label="Date limite" value={date} onChange={setDate} />
        <Select label="Me prévenir" data={rappels} value={rappel} onChange={v => v !== null && setRappel(v)} allowDeselect={false} />
        <Select label="Revient" data={recurrences} value={recurrence} onChange={v => v !== null && setRecurrence(v)} allowDeselect={false} />
      </SimpleGrid>
      <ChampMontant label="Ce que ça coûtera (optionnel)" value={montant} onChange={setMontant} />
      <Checkbox label="Mettre de côté chaque mois d'ici là" checked={provisionner && !!montant.trim()} disabled={!montant.trim()}
                onChange={e => setProvisionner(e.currentTarget.checked)}
                description={existante?.objectif_id && !provisionner
                  ? "L'objectif lié sera retiré (gardé s'il contient déjà de l'argent)"
                  : "Crée un objectif d'épargne du même montant pour cette date : le montant à mettre de côté chaque mois s'affiche ici et dans Objectifs"} />
      <Textarea label="Note (optionnel)" placeholder="N° de contrat, où renouveler, montant…" autosize minRows={1} maxRows={4}
                value={note} onChange={e => setNote(e.currentTarget.value)} maxLength={2000} />
      <Button mt="xs" onClick={enregistrer} loading={ecrire.isPending}>{existante ? 'Enregistrer' : "Ajouter l'échéance"}</Button>
    </Stack>
  );
}

function LigneEcheance({ e }: { e: Echeance }) {
  const ecrire = useEcriture('carnet');
  const enRetard = e.jours_restants < 0;
  const couleur = enRetard ? 'rouge' : e.a_rappeler ? 'ambre' : 'gray';
  const details = [e.categorie, dateFr(e.date_echeance), e.montant ? fmt(e.montant) : ''].filter(Boolean).join(' · ');
  const p = e.provision && !e.provision.archive ? e.provision : null;

  return (
    <Group className="ligne-op" wrap="nowrap" gap="sm" px={6} py={8} align="flex-start">
      <Pastille icone={IconCalendarDue} couleur={couleur} taille={34} />
      <Box style={{ flex: 1, minWidth: 0 }}>
        <Text fz="sm" fw={600} truncate>{e.titre}</Text>
        <Text fz="xs" c="dimmed" truncate>{details}</Text>
        {e.note && <Text fz="xs" c="dimmed" fs="italic" lineClamp={2} mt={2} style={{ whiteSpace: 'pre-wrap' }}>{e.note}</Text>}
        {p && (
          <Box mt={6}>
            <Progress value={Math.min(100, p.verse / p.cible * 100)} color={p.verse >= p.cible ? 'emeraude' : 'marque'} size={6} radius="xl" />
            <Text fz="xs" c="dimmed" mt={3}>
              {fmt(p.verse)} mis de côté sur {fmt(p.cible)}
              {p.reste > 0 ? (p.par_mois ? ` · ${fmt(p.par_mois)} par mois` : ' · date passée') : ' · prêt ✓'}
            </Text>
          </Box>
        )}
        <Group gap={6} mt={5}>
          <Badge size="xs" variant="light" color={couleur}>{delai(e.jours_restants)}</Badge>
          {p && <Badge size="xs" variant="light" color="marque" leftSection={<IconPigMoney size={10} stroke={2.2} />}>provision</Badge>}
          {e.recurrence_mois && (
            <Badge size="xs" variant="light" color="gray" leftSection={<IconRepeat size={10} stroke={2.2} />}>{libelleRecurrence(e.recurrence_mois)}</Badge>
          )}
        </Group>
      </Box>
      <Group gap={0} wrap="nowrap">
        {e.recurrence_mois && (
          <Tooltip label="Fait : reporter à la prochaine fois" withArrow>
            <ActionIcon variant="subtle" color="emeraude" aria-label="Fait : reporter à la prochaine fois"
                        onClick={() => ecrire.mutate({ path: `/api/carnet/echeances/${e.id}/reporter`, method: 'POST', succes: 'Reportée à la prochaine fois ✓' })}>
              <IconCheck size={16} stroke={1.9} />
            </ActionIcon>
          </Tooltip>
        )}
        <Tooltip label="Modifier" withArrow>
          <ActionIcon variant="subtle" color="gray" className="suppr" aria-label="Modifier"
                      onClick={() => ouvrir('Modifier', fermer => <FormEcheance existante={e} onTermine={fermer} />)}>
            <IconPencil size={16} stroke={1.7} />
          </ActionIcon>
        </Tooltip>
        <BoutonSuppr onClick={() => confirmer(`Supprimer « ${e.titre} » ?`, () =>
          ecrire.mutate({ path: `/api/carnet/echeances/${e.id}`, method: 'DELETE', succes: 'Échéance supprimée' }))} />
      </Group>
    </Group>
  );
}

/** Ce qu'il faut mettre de côté ce mois-ci pour les échéances provisionnées (aussi sur le dashboard du mois) */
export function aProvisionner(echeances: Echeance[] | undefined): { total: number; nb: number } {
  const p = (echeances ?? []).map(e => e.provision).filter(p => p && !p.archive && p.reste > 0 && p.par_mois);
  return { total: p.reduce((s, x) => s + x!.par_mois!, 0), nb: p.length };
}

export function ListeEcheances() {
  const { data, isPending } = useEcheances();
  const aTraiter = (data ?? []).filter(e => e.a_rappeler);
  const plusTard = (data ?? []).filter(e => !e.a_rappeler);
  const provision = aProvisionner(data);

  return (
    <Grid gap="lg" align="flex-start">
      <Grid.Col span={{ base: 12, md: 5 }}>
        <Stack gap="lg">
          {provision.nb > 0 && (
            <Carte titre="À mettre de côté ce mois-ci" icone={<Pastille icone={IconPigMoney} couleur="marque" />}
                   droite={<Text className="chiffre" fz="lg" fw={700}>{fmt(provision.total)}</Text>}>
              <Info>
                Pour {provision.nb} échéance{provision.nb > 1 ? 's' : ''} à venir. Mets cet argent de côté dans Suivi → Objectifs
                (« Mettre de côté ») : le jour venu, la dépense ne pèse plus sur un seul mois.
              </Info>
            </Carte>
          )}
          <Carte className="colle" titre="Nouvelle échéance" description="Un papier, un contrat ou une garantie qui expire"
                 icone={<Pastille icone={IconCalendarEvent} couleur="marque" />}>
            <FormEcheance />
          </Carte>
        </Stack>
      </Grid.Col>
      <Grid.Col span={{ base: 12, md: 7 }}>
        <Stack gap="lg">
          <Carte titre="À traiter" description="En retard, ou entrées dans leur délai de rappel">
            {isPending ? <Chargement lignes={2} /> : !aTraiter.length
              ? <Vide icone={IconCheck}>Rien d'urgent pour l'instant</Vide>
              : <Stack gap={2}>{aTraiter.map(e => <LigneEcheance key={e.id} e={e} />)}</Stack>}
          </Carte>
          <Carte titre="Plus tard" description={plusTard.length ? `${plusTard.length} échéance${plusTard.length > 1 ? 's' : ''} à venir` : undefined}>
            {isPending ? <Chargement lignes={3} /> : !plusTard.length
              ? <Vide icone={IconCalendarDue}>Ajoute ta CIN, ton passeport, l'assurance et la visite technique de la voiture…</Vide>
              : <Stack gap={2}>{plusTard.map(e => <LigneEcheance key={e.id} e={e} />)}</Stack>}
          </Carte>
        </Stack>
      </Grid.Col>
    </Grid>
  );
}
