/* Opérations récurrentes (loyer, abonnements, salaire) : la liste à ajouter ce mois-ci, affichée dans Saisie, et la fenêtre
 * de gestion (création, modification, suggestions tirées de l'historique). Une récurrence « auto » est ajoutée toute seule
 * par la tâche du matin le jour venu ; les autres attendent ici, avec un montant modifiable (facture qui varie). */
import { useState } from 'react';
import {
  ActionIcon, Badge, Box, Button, Checkbox, Divider, Group, NumberInput, SegmentedControl, Select, SimpleGrid, Stack, Switch, Text, TextInput, Tooltip,
} from '@mantine/core';
import { modals } from '@mantine/modals';
import { IconBulb, IconPencil, IconPlayerSkipForward, IconPlus, IconRepeat } from '@tabler/icons-react';

import { toast } from '../lib/api';
import { auj, dateFr, decalerMois, fmt, libelleMois, lireMontant } from '../lib/format';
import { T } from '../lib/palette';
import type { Generation, Recurrence, RecurrenceAGenerer, SuggestionRecurrence, TypeOperation } from '../lib/types';
import { useConfig, useEcriture, useRecurrences, useRecurrencesAGenerer, useSuggestionsRecurrences } from '../lib/queries';
import { ChampMontant } from './champs';
import { ChampTags } from './Transactions';
import { BoutonSuppr, Carte, Chargement, confirmer, Pastille, Vide } from './ui';

const texteMontant = (m: number) => String(m).replace('.', ',');
const libelle = (r: { nom: string; description: string; type: TypeOperation }) =>
  [r.nom, r.description].filter(Boolean).join(' · ') || (r.type === 'revenu' ? 'Revenu' : 'Dépense');
const signeMontant = (type: TypeOperation, m: number) => (type === 'revenu' ? '+' : '−') + fmt(m);

/** Premier mois proposé : ce mois-ci si le jour n'est pas encore passé, sinon le suivant
 *  (un loyer du 1er créé le 12 a sans doute déjà été saisi à la main ce mois-ci) */
export function debutParDefaut(jour: number, aujourdhui = auj()): string {
  const mois = aujourdhui.slice(0, 7);
  return jour >= +aujourdhui.slice(8, 10) ? mois : decalerMois(mois, 1);
}

/* ---------- Formulaire ---------- */
type Modele = Partial<Pick<Recurrence, 'type' | 'nom' | 'description' | 'montant' | 'jour' | 'tags' | 'auto' | 'actif' | 'debut'>>;

function FormRecurrence({ existant, modele, onTermine }: { existant?: Recurrence; modele?: Modele; onTermine?: () => void }) {
  const base: Modele = existant ?? modele ?? {};
  const ecrire = useEcriture('budget');
  const { data: config } = useConfig();
  const [type, setType] = useState<TypeOperation>(base.type ?? 'depense');
  const [nom, setNom] = useState<string | null>(base.nom || null);
  const [description, setDescription] = useState(base.description ?? '');
  const [montant, setMontant] = useState(base.montant ? texteMontant(base.montant) : '');
  const [jour, setJour] = useState<number>(base.jour ?? 1);
  const [tags, setTags] = useState<string[]>(base.tags ?? []);
  const [auto, setAuto] = useState(base.auto ?? false);
  const [debut, setDebut] = useState<string | null>(base.debut ?? null);   // null : suit le jour choisi
  const debutEffectif = debut ?? debutParDefaut(jour);

  const courant = auj().slice(0, 7);
  const moisProposes = [...new Set([...Array.from({ length: 16 }, (_, i) => decalerMois(courant, i - 3)), debutEffectif])].sort();
  const noms = type === 'depense'
    ? [...new Set([...(config?.categories.map(c => c.nom) ?? []), ...(base.type === 'depense' && base.nom ? [base.nom] : [])])]
    : [...new Set([...(config?.sources.map(s => s.nom) ?? []), ...(base.type === 'revenu' && base.nom ? [base.nom] : [])])];

  function enregistrer() {
    const m = lireMontant(montant);
    if (type === 'depense' && !nom) return toast('Choisis la catégorie', false);
    if (isNaN(m) || m <= 0) return toast('Montant invalide', false);
    const body = { type, nom: nom ?? '', description: description.trim(), montant: m, jour, tags, auto,
                   actif: existant?.actif ?? true, debut: debutEffectif };
    ecrire.mutate(existant
      ? { path: `/api/recurrences/${existant.id}`, method: 'PUT', body, succes: 'Récurrence modifiée ✓' }
      : { path: '/api/recurrences', method: 'POST', body, succes: 'Récurrence créée ✓' },
    { onSuccess: () => onTermine?.() });
  }

  return (
    <Stack gap="sm">
      <SegmentedControl fullWidth value={type} color={type === 'depense' ? 'rose' : 'bleu'}
                        onChange={v => { setType(v as TypeOperation); setNom(null); }}
                        data={[{ value: 'depense', label: 'Dépense' }, { value: 'revenu', label: 'Revenu' }]} />
      <SimpleGrid cols={{ base: 1, xs: 2 }} spacing="sm">
        <Select label={type === 'depense' ? 'Catégorie' : 'Source'} placeholder={type === 'depense' ? '— Choisir —' : 'Sans source'}
                data={noms} value={nom} onChange={setNom} searchable clearable={type === 'revenu'} comboboxProps={{ withinPortal: true }} />
        <ChampMontant label="Montant" value={montant} onChange={setMontant} />
      </SimpleGrid>
      <TextInput label="Description (optionnel)" placeholder={type === 'depense' ? 'ex : loyer, Netflix, internet' : 'ex : salaire'}
                 value={description} onChange={e => setDescription(e.currentTarget.value)} maxLength={500} />
      <SimpleGrid cols={{ base: 1, xs: 2 }} spacing="sm">
        <NumberInput label="Jour du mois" min={1} max={31} clampBehavior="strict" allowDecimal={false} value={jour}
                     onChange={v => setJour(Math.min(31, Math.max(1, Number(v) || 1)))}
                     description={jour > 28 ? 'Dernier jour des mois plus courts' : undefined} />
        <Select label="À partir de" data={moisProposes.map(m => ({ value: m, label: libelleMois(m) }))} value={debutEffectif}
                onChange={v => v && setDebut(v)} allowDeselect={false} comboboxProps={{ withinPortal: true }}
                description={existant?.dernier_mois ? `Déjà ajoutée jusqu'en ${libelleMois(existant.dernier_mois).toLowerCase()}` : undefined} />
      </SimpleGrid>
      <ChampTags value={tags} onChange={setTags} />
      <Switch checked={auto} onChange={e => setAuto(e.currentTarget.checked)} label="Ajouter toute seule le jour venu"
              description={auto ? 'La tâche du matin l\'ajoute au Budget (et te le dit dans le message du matin).'
                : 'Proposée dans Saisie à partir du début du mois : tu confirmes, en corrigeant le montant si besoin.'} />
      <Button mt="xs" onClick={enregistrer} loading={ecrire.isPending}>{existant ? 'Enregistrer' : 'Créer la récurrence'}</Button>
    </Stack>
  );
}

function ouvrirFormulaire(titre: string, props: { existant?: Recurrence; modele?: Modele }) {
  const id = modals.open({ title: <Text fw={650}>{titre}</Text>, centered: true,
                           children: <FormRecurrence {...props} onTermine={() => modals.close(id)} /> });
}

/* ---------- Gestion ---------- */
function LigneRecurrence({ r }: { r: Recurrence }) {
  const ecrire = useEcriture('budget');
  const corps = { type: r.type, nom: r.nom, description: r.description, montant: r.montant, jour: r.jour, tags: r.tags,
                  auto: r.auto, debut: r.debut };
  return (
    <Group className="ligne-op" wrap="nowrap" gap="sm" px={6} py={7} align="flex-start">
      <Box style={{ flex: 1, minWidth: 0 }}>
        <Group justify="space-between" wrap="nowrap" gap="xs">
          <Text fz="sm" fw={600} truncate c={r.actif ? undefined : 'dimmed'}>{libelle(r)}</Text>
          <Text fz="sm" fw={700} className="chiffre" c={r.type === 'revenu' ? T.rev : T.dep} style={{ whiteSpace: 'nowrap' }}>
            {signeMontant(r.type, r.montant)}
          </Text>
        </Group>
        <Group gap={5} mt={4}>
          <Text fz="xs" c="dimmed">le {r.jour > 28 ? `${r.jour} (ou dernier jour)` : r.jour} de chaque mois</Text>
          {r.actif && <Text fz="xs" c="dimmed">· prochaine : {dateFr(r.prochaine_date)}</Text>}
          {r.auto && <Badge size="xs" variant="light" color="marque" tt="none">auto</Badge>}
          {!r.actif && <Badge size="xs" variant="light" color="gray" tt="none">en pause</Badge>}
          {r.en_attente > 0 && <Badge size="xs" variant="light" color="ambre" tt="none">{r.en_attente} à ajouter</Badge>}
        </Group>
      </Box>
      <Group gap={0} wrap="nowrap">
        <Tooltip label={r.actif ? 'Mettre en pause' : 'Reprendre'} withArrow>
          <Switch size="xs" mt={4} mr={4} checked={r.actif} aria-label={r.actif ? 'Mettre en pause' : 'Reprendre'}
                  onChange={e => ecrire.mutate({ path: `/api/recurrences/${r.id}`, method: 'PUT', body: { ...corps, actif: e.currentTarget.checked },
                                                 succes: e.currentTarget.checked ? 'Récurrence reprise' : 'Récurrence en pause' })} />
        </Tooltip>
        <Tooltip label="Modifier" withArrow>
          <ActionIcon variant="subtle" color="gray" aria-label="Modifier" onClick={() => ouvrirFormulaire('Modifier la récurrence', { existant: r })}>
            <IconPencil size={16} stroke={1.7} />
          </ActionIcon>
        </Tooltip>
        <BoutonSuppr onClick={() => confirmer(`Supprimer la récurrence « ${libelle(r)} » ? Les opérations déjà ajoutées restent dans le Budget.`,
          () => ecrire.mutate({ path: `/api/recurrences/${r.id}`, method: 'DELETE', succes: 'Récurrence supprimée' }))} />
      </Group>
    </Group>
  );
}

function Suggestions() {
  const { data, isPending } = useSuggestionsRecurrences(true);
  if (isPending) return <Chargement lignes={2} />;
  if (!data?.length) return null;
  return (
    <Stack gap={4}>
      <Divider label={<Group gap={4}><IconBulb size={14} />Repérées dans tes 3 derniers mois</Group>} labelPosition="left" />
      {data.map(s => (
        <Group key={s.type + s.nom + s.description} className="ligne-op" wrap="nowrap" gap="sm" px={6} py={6}>
          <Box style={{ flex: 1, minWidth: 0 }}>
            <Text fz="sm" truncate>{libelle(s)}</Text>
            <Text fz="xs" c="dimmed">chaque mois vers le {s.jour} · {signeMontant(s.type, s.montant)}</Text>
          </Box>
          <Button size="compact-sm" variant="light" leftSection={<IconPlus size={14} />}
                  onClick={() => ouvrirFormulaire('Nouvelle récurrence', { modele: suggestionEnModele(s) })}>Créer</Button>
        </Group>
      ))}
    </Stack>
  );
}

const suggestionEnModele = (s: SuggestionRecurrence): Modele => ({
  type: s.type, nom: s.nom, description: s.description, montant: s.montant, jour: s.jour, tags: s.tags,
  auto: s.type === 'depense' ? false : true,
});

export function GestionRecurrences() {
  const { data, isPending } = useRecurrences();
  const liste = data ?? [];
  const actives = liste.filter(r => r.actif);
  const parMois = (type: TypeOperation) => actives.filter(r => r.type === type).reduce((s, r) => s + r.montant, 0);
  return (
    <Stack gap="md">
      <Group justify="space-between" gap="xs">
        <Text fz="sm" c="dimmed">
          {actives.length ? <>Chaque mois : <Text span inherit c={T.rev} fw={600}>+{fmt(parMois('revenu'))}</Text> · <Text span inherit c={T.dep} fw={600}>−{fmt(parMois('depense'))}</Text></>
            : 'Loyer, abonnements, salaire : saisis une fois, ajoutés chaque mois.'}
        </Text>
        <Button size="compact-sm" leftSection={<IconPlus size={14} />} onClick={() => ouvrirFormulaire('Nouvelle récurrence', {})}>Nouvelle</Button>
      </Group>
      {isPending ? <Chargement lignes={3} /> : !liste.length
        ? <Vide icone={IconRepeat}>Aucune récurrence pour l'instant</Vide>
        : <Stack gap={2}>{liste.map(r => <LigneRecurrence key={r.id} r={r} />)}</Stack>}
      <Suggestions />
    </Stack>
  );
}

export function ouvrirRecurrences() {
  modals.open({ title: <Text fw={650}>Opérations récurrentes</Text>, centered: true, size: 'lg', children: <GestionRecurrences /> });
}

/* ---------- À ajouter ce mois-ci (Saisie) ---------- */
const cle = (e: RecurrenceAGenerer) => `${e.id}:${e.mois}`;

function LigneAAjouter({ e, coche, montant, onCoche, onMontant }: {
  e: RecurrenceAGenerer; coche: boolean; montant: string; onCoche: (v: boolean) => void; onMontant: (v: string) => void;
}) {
  const ecrire = useEcriture('budget');
  return (
    <Group wrap="nowrap" gap="sm" px={4} py={5} className="ligne-op">
      <Checkbox checked={coche} onChange={x => onCoche(x.currentTarget.checked)} aria-label={`Ajouter ${libelle(e)}`} />
      <Box style={{ flex: 1, minWidth: 0 }}>
        <Text fz="sm" truncate>{libelle(e)}</Text>
        <Text fz="xs" c={e.a_venir ? 'dimmed' : undefined}>
          {dateFr(e.date, false)}{e.a_venir ? ' · à venir' : ''}{e.auto ? ' · auto' : ''}
        </Text>
      </Box>
      <ChampMontant size="xs" w={110} value={montant} onChange={onMontant} aria-label={`Montant de ${libelle(e)}`}
                    styles={{ input: { textAlign: 'right', color: e.type === 'revenu' ? T.rev : undefined } }} />
      <Tooltip label="Rien ce mois-ci : passer" withArrow>
        <ActionIcon variant="subtle" color="gray" aria-label="Passer ce mois" loading={ecrire.isPending}
                    onClick={() => ecrire.mutate({ path: `/api/recurrences/${e.id}/passer`, method: 'POST', body: { mois: e.mois },
                                                   succes: `${libelle(e)} : ${libelleMois(e.mois).toLowerCase()} passé` })}>
          <IconPlayerSkipForward size={16} stroke={1.7} />
        </ActionIcon>
      </Tooltip>
    </Group>
  );
}

/** Carte de Saisie : les opérations récurrentes pas encore ajoutées jusqu'à ce mois-ci. Rien s'il n'y en a pas. */
export function RecurrencesAAjouter() {
  const { data } = useRecurrencesAGenerer();
  const ecrire = useEcriture('budget');
  // Choix et montants modifiés à la main ; par défaut : cochée si sa date est arrivée, montant de la récurrence
  const [coches, setCoches] = useState<Record<string, boolean>>({});
  const [montants, setMontants] = useState<Record<string, string>>({});
  const liste = data ?? [];
  if (!liste.length) return null;
  const estCoche = (e: RecurrenceAGenerer) => coches[cle(e)] ?? !e.a_venir;
  const choisies = liste.filter(estCoche);

  function ajouter() {
    const elements = choisies.map(e => {
      const texte = montants[cle(e)];
      const m = texte === undefined ? e.montant : lireMontant(texte);
      return { id: e.id, mois: e.mois, montant: m };
    });
    if (elements.some(x => isNaN(x.montant) || x.montant <= 0)) return toast('Montant invalide', false);
    ecrire.mutate({ path: '/api/recurrences/generer', method: 'POST', body: { elements } }, {
      onSuccess: r => {
        const n = (r as Generation).generees.length;
        toast(n ? `${n} opération${n > 1 ? 's' : ''} ajoutée${n > 1 ? 's' : ''} ✓` : 'Déjà ajoutées entre-temps');
        setCoches({}); setMontants({});
      },
    });
  }

  return (
    <Carte titre="Récurrences à ajouter" icone={<Pastille icone={IconRepeat} couleur="ambre" />}
           description="Coche, corrige le montant si la facture a changé, puis ajoute"
           droite={<Button variant="subtle" size="compact-sm" onClick={ouvrirRecurrences}>Gérer</Button>}>
      <Stack gap={2}>
        {liste.map(e => (
          <LigneAAjouter key={cle(e)} e={e} coche={estCoche(e)} montant={montants[cle(e)] ?? texteMontant(e.montant)}
                         onCoche={v => setCoches(s => ({ ...s, [cle(e)]: v }))} onMontant={v => setMontants(s => ({ ...s, [cle(e)]: v }))} />
        ))}
      </Stack>
      <Button mt="sm" fullWidth onClick={ajouter} loading={ecrire.isPending} disabled={!choisies.length}>
        Ajouter {choisies.length > 1 ? `les ${choisies.length} opérations` : choisies.length ? "l'opération" : ''}
      </Button>
    </Carte>
  );
}
