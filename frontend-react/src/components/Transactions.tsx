/* Dépenses et revenus : formulaires (ajout, modification ou duplication dans une fenêtre), liste d'un
 * mois et résultats de recherche. Utilisé par la Saisie. */
import { useEffect, useState } from 'react';
import {
  ActionIcon, Autocomplete, Badge, Box, Button, Group, Progress, SegmentedControl, Select, SimpleGrid, Stack, TagsInput, Text, TextInput, Tooltip,
} from '@mantine/core';
import { modals } from '@mantine/modals';
import { IconArrowDownLeft, IconArrowUpRight, IconClockHour4, IconCopy, IconPencil, IconReceipt, IconSearch } from '@tabler/icons-react';

import { avertir, toast } from '../lib/api';
import { auj, decalerDate, fmt, JOURS_FR, libelleMois, lireMontant, MOIS_FR, prixEnTravail } from '../lib/format';
import { T } from '../lib/palette';
import type { Depense, ResultatRecherche, Revenu } from '../lib/types';
import { useConfig, useEcriture, useRecherche, useResumeMois, useSuggestions, useTags, useTransactionsMois } from '../lib/queries';
import { ChampDate, ChampMontant } from './champs';
import { BoutonSuppr, Carte, Chargement, notifierAnnulable, Pastille, Vide } from './ui';

const AUTRE = '__autre__';

// Montant existant remis dans le champ texte, avec la virgule française
const texteMontant = (m?: number) => m === undefined ? '' : String(m).replace('.', ',');

/** Date proposée pour une nouvelle opération quand la liste affiche `mois` : aujourd'hui pour le
 *  mois en cours, le dernier jour d'un mois passé (oubli à rattraper), le 1er d'un mois futur. */
export function dateParDefaut(mois?: string): string {
  const courant = auj().slice(0, 7);
  if (!mois || mois === courant) return auj();
  if (mois > courant) return mois + '-01';
  const [a, m] = mois.split('-').map(Number);
  return decalerDate(`${m === 12 ? a + 1 : a}-${String(m === 12 ? 1 : m + 1).padStart(2, '0')}-01`, -1);
}

/* ---------- Champs communs ---------- */
function ChampTags({ value, onChange }: { value: string[]; onChange: (v: string[]) => void }) {
  const { data: tags } = useTags();
  return (
    <TagsInput label="Tags (optionnel)" placeholder="ex : voyage été 2026, puis Entrée" value={value} maxTags={10}
               data={(tags ?? []).map(t => t.tag)} clearable splitChars={[',']} acceptValueOnBlur
               onChange={v => onChange([...new Set(v.map(t => t.trim().toLowerCase().replace(/^#/, '')).filter(Boolean))])} />
  );
}

/** Description avec les 5 dernières de la catégorie / source ; en choisir une remplit le montant s'il est vide */
function ChampDescription({ type, nom, value, onChange, onMontant, placeholder }: {
  type: 'depenses' | 'revenus'; nom: string | null; value: string; onChange: (v: string) => void;
  onMontant: (m: number) => void; placeholder: string;
}) {
  const { data: suggestions } = useSuggestions(type, nom);
  return (
    <Autocomplete label="Description (optionnel)" placeholder={placeholder} value={value} onChange={onChange}
                  data={[...new Set((suggestions ?? []).map(s => s.description))]}
                  onOptionSubmit={v => { const s = suggestions?.find(x => x.description === v); if (s) onMontant(s.montant); }} />
  );
}

/* ---------- Budget de la catégorie, au moment de la saisie ---------- */
/** Seuil à partir duquel la saisie prévient : la catégorie a consommé 80 % de son budget du mois */
const SEUIL_ALERTE = 80;

type EtatBudget = { budget: number; deja: number; apres: number; pct: number; mois: string };

/** Où en est le budget de `categorie` le mois de `date`, avec `montant` en plus ; null sans budget.
 *  Lu dans le résumé du mois (souvent déjà en cache depuis le dashboard ou l'accueil). */
function useEtatBudget(categorie: string | null, date: string, montant: number, existante?: Depense): EtatBudget | null {
  const mois = date.slice(0, 7);
  const { data: r } = useResumeMois(mois);
  // r.mois : le résumé affiché pendant le chargement peut être celui du mois précédemment choisi
  if (!categorie || !r || r.mois !== mois) return null;
  const b = r.budget_vs_reel.find(x => x.cat === categorie);
  if (!b || b.budget <= 0) return null;
  // En modification, l'ancien montant est déjà compté dans le réel du mois
  const ancien = existante && existante.categorie === categorie && existante.date.slice(0, 7) === mois ? existante.montant : 0;
  const deja = Math.round((b.reel - ancien) * 100) / 100;
  const apres = deja + (montant > 0 ? montant : 0);
  return { budget: b.budget, deja, apres, pct: apres / b.budget * 100, mois };
}

const couleurBudget = (pct: number) => pct > 100 ? 'rouge' : pct >= SEUIL_ALERTE ? 'ambre' : 'marque';
const pctTexte = (pct: number) => Math.round(pct) + ' %';

function LigneBudget({ categorie, etat, avecMontant }: { categorie: string; etat: EtatBudget; avecMontant: boolean }) {
  const couleur = couleurBudget(etat.pct);
  return (
    <Box>
      <Progress value={Math.min(100, etat.pct)} color={couleur} size={5} radius="xl" />
      <Text fz="xs" c="dimmed" mt={4}>
        {categorie} : {fmt(etat.deja)} dépensés sur {fmt(etat.budget)} en {libelleMois(etat.mois).toLowerCase()}
        {avecMontant && (
          <> · <Text span inherit fw={600} c={couleur === 'marque' ? undefined : `var(--mantine-color-${couleur}-6)`}>
            {etat.pct > 100 ? `dépassé de ${fmt(etat.apres - etat.budget)}` : `${pctTexte(etat.pct)} avec celle-ci`}
          </Text></>
        )}
      </Text>
    </Box>
  );
}

/** Après l'enregistrement : prévient si la catégorie atteint 80 % de son budget ou le dépasse */
function alerteBudget(categorie: string, e: EtatBudget | null) {
  if (!e || e.pct < SEUIL_ALERTE) return;
  const detail = `${fmt(e.apres)} sur ${fmt(e.budget)} en ${libelleMois(e.mois).toLowerCase()}`;
  if (e.pct > 100) avertir(`${categorie} : budget dépassé de ${fmt(e.apres - e.budget)}`, detail, true);
  else avertir(`${categorie} : ${pctTexte(e.pct)} du budget utilisé`, `${detail} · reste ${fmt(e.budget - e.apres)}`);
}

/* ---------- Formulaires ---------- */
type PropsForm<O> = {
  /** Opération modifiée (fenêtre « Modifier ») */
  existante?: O;
  /** Opération recopiée dans un nouveau formulaire (« Dupliquer »), datée d'aujourd'hui */
  modele?: O;
  /** Mois affiché à côté du formulaire de saisie : sa date par défaut suit ce mois */
  mois?: string;
  onTermine?: () => void;
};

export function FormDepense({ existante, modele, mois, onTermine }: PropsForm<Depense>) {
  const { data: config } = useConfig();
  const ecrire = useEcriture('budget');
  const base = existante ?? modele;
  const [date, setDate] = useState(existante?.date ?? dateParDefaut(mois));
  const [categorie, setCategorie] = useState<string | null>(base?.categorie ?? null);
  const [montant, setMontant] = useState(texteMontant(base?.montant));
  const [description, setDescription] = useState(base?.description ?? '');
  const [tags, setTags] = useState<string[]>(base?.tags ?? []);

  // Formulaire de saisie : en changeant de mois dans la liste, la date suit
  useEffect(() => { if (!existante && !modele) setDate(dateParDefaut(mois)); }, [mois, existante, modele]);

  const montantLu = lireMontant(montant);
  const budget = useEtatBudget(categorie, date, montantLu, existante);

  function enregistrer() {
    const m = lireMontant(montant);
    if (!categorie) return toast('Choisis une catégorie', false);
    if (isNaN(m) || m <= 0) return toast('Montant invalide', false);
    const body = { date, categorie, description, montant: m, tags };
    const etatBudget = budget;   // calculé avant l'enregistrement (le résumé est rechargé ensuite)
    ecrire.mutate(
      existante
        ? { path: `/api/depenses/${existante.id}`, method: 'PUT', body, succes: 'Dépense modifiée ✓' }
        : { path: '/api/depenses', method: 'POST', body, succes: 'Dépense ajoutée ✓' },
      { onSuccess: () => { alerteBudget(categorie, etatBudget); if (!existante) { setMontant(''); setDescription(''); } onTermine?.(); } },
    );
  }

  // Sans doublon : Mantine refuse deux options de même valeur (les noms sont uniques en base).
  // Une catégorie désactivée depuis reste proposée pour la dépense qui la porte déjà.
  const cats = [...new Set([...(config?.categories.map(c => c.nom) ?? []), ...(existante ? [existante.categorie] : [])])];
  // Le prix en heures de travail : pour réfléchir avant un gros achat (rien sous 2 h)
  const enTravail = config?.travail && prixEnTravail(lireMontant(montant), config.travail.taux_horaire, config.travail.heures_mois);
  return (
    <Stack gap="sm">
      <Box>
        <ChampMontant label="Montant (DH)" size="md" value={montant} onChange={setMontant}
                      onKeyDown={e => { if (e.key === 'Enter') enregistrer(); }} />
        {enTravail && (
          <Tooltip label={`À ${fmt(config!.travail.taux_horaire!)} de l'heure (${fmt(config!.travail.revenu_mensuel)} par mois pour ${config!.travail.heures_mois} h)`}
                   multiline w={280} withArrow position="bottom-start">
            <Group gap={4} mt={6} c="dimmed" wrap="nowrap" w="fit-content">
              <IconClockHour4 size={14} stroke={1.7} />
              <Text fz="xs">{enTravail}</Text>
            </Group>
          </Tooltip>
        )}
      </Box>
      <Select label="Catégorie" placeholder="— Choisir une catégorie —" data={cats} searchable
              nothingFoundMessage="Aucune catégorie"
              value={categorie && cats.includes(categorie) ? categorie : null} onChange={setCategorie} />
      {categorie && budget && <LigneBudget categorie={categorie} etat={budget} avecMontant={montantLu > 0} />}
      <SimpleGrid cols={{ base: 1, xs: 2 }} spacing="sm">
        <ChampDate value={date} onChange={setDate} />
        <ChampDescription type="depenses" nom={categorie} value={description} onChange={setDescription}
                          onMontant={m => { if (!montant) setMontant(texteMontant(m)); }} placeholder="ex : courses Marjane" />
      </SimpleGrid>
      <ChampTags value={tags} onChange={setTags} />
      <Button mt="xs" size="md" color="rose" onClick={enregistrer} loading={ecrire.isPending}>
        {existante ? 'Enregistrer' : 'Ajouter la dépense'}
      </Button>
    </Stack>
  );
}

export function FormRevenu({ existante, modele, mois, onTermine }: PropsForm<Revenu>) {
  const { data: config } = useConfig();
  const ecrire = useEcriture('budget');
  const base = existante ?? modele;
  const [date, setDate] = useState(existante?.date ?? dateParDefaut(mois));
  const [source, setSource] = useState<string | null>(base?.source || null);
  const [autre, setAutre] = useState('');
  const [montant, setMontant] = useState(texteMontant(base?.montant));
  const [description, setDescription] = useState(base?.description ?? '');
  const [tags, setTags] = useState<string[]>(base?.tags ?? []);

  useEffect(() => { if (!existante && !modele) setDate(dateParDefaut(mois)); }, [mois, existante, modele]);

  function enregistrer() {
    const m = lireMontant(montant);
    let s = source;
    if (!s) return toast('Choisis une source', false);
    if (s === AUTRE) {
      s = autre.trim();
      if (!s) return toast('Précise la source', false);
    }
    if (isNaN(m) || m <= 0) return toast('Montant invalide', false);
    const body = { date, source: s, description, montant: m, tags };
    ecrire.mutate(
      existante
        ? { path: `/api/revenus/${existante.id}`, method: 'PUT', body, succes: 'Revenu modifié ✓' }
        : { path: '/api/revenus', method: 'POST', body, succes: 'Revenu ajouté ✓' },
      { onSuccess: () => { if (!existante) { setMontant(''); setAutre(''); setDescription(''); } onTermine?.(); } },
    );
  }

  // Une source libre (« Autre… ») ou désactivée depuis reste proposée pour le revenu qui la porte déjà
  const noms = [...new Set([...(config?.sources.map(s => s.nom) ?? []), ...(base?.source ? [base.source] : [])])];
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
      <SimpleGrid cols={{ base: 1, xs: 2 }} spacing="sm">
        <ChampDate value={date} onChange={setDate} />
        <ChampDescription type="revenus" nom={valeur === AUTRE ? autre.trim() || null : valeur} value={description}
                          onChange={setDescription} onMontant={m => { if (!montant) setMontant(texteMontant(m)); }}
                          placeholder="ex : salaire de septembre" />
      </SimpleGrid>
      <ChampTags value={tags} onChange={setTags} />
      <Button mt="xs" size="md" color="bleu" onClick={enregistrer} loading={ecrire.isPending}>
        {existante ? 'Enregistrer' : 'Ajouter le revenu'}
      </Button>
    </Stack>
  );
}

/* ---------- Lignes (liste du mois et recherche) ---------- */
type Ligne = { id: number; date: string; titre: string; detail: string; montant: number; tags: string[] }
  & ({ type: 'depenses'; origine: Depense } | { type: 'revenus'; origine: Revenu });

const ligneDepense = (x: Depense): Ligne => ({ id: x.id, type: 'depenses', origine: x, date: x.date, montant: x.montant, titre: x.categorie, detail: x.description, tags: x.tags });
const ligneRevenu = (x: Revenu): Ligne => ({ id: x.id, type: 'revenus', origine: x, date: x.date, montant: x.montant, titre: x.source || 'Revenu', detail: x.description, tags: x.tags });
const ligneRecherche = (r: ResultatRecherche): Ligne => r.type === 'depenses'
  ? ligneDepense({ id: r.id, date: r.date, categorie: r.nom, description: r.description, montant: r.montant, tags: r.tags })
  : ligneRevenu({ id: r.id, date: r.date, source: r.nom, description: r.description, montant: r.montant, tags: r.tags });

function ouvrirFormulaire(l: Ligne, mode: 'modifier' | 'dupliquer') {
  const fermer = () => modals.close(id);
  const dep = l.type === 'depenses';
  const titre = (mode === 'modifier' ? 'Modifier ' : 'Dupliquer ') + (dep ? 'la dépense' : 'le revenu');
  const props = mode === 'modifier' ? { existante: l.origine, onTermine: fermer } : { modele: l.origine, onTermine: fermer };
  const id = modals.open({
    title: <Text fw={650}>{titre}</Text>,
    centered: true,
    children: (
      <>
        {l.type === 'depenses'
          ? <FormDepense {...props as PropsForm<Depense>} />
          : <FormRevenu {...props as PropsForm<Revenu>} />}
        {/* Sur téléphone, l'icône « Dupliquer » de la ligne est masquée faute de place */}
        {mode === 'modifier' && (
          <Button hiddenFrom="xs" fullWidth mt="xs" variant="subtle" color="gray" leftSection={<IconCopy size={16} />}
                  onClick={() => { fermer(); ouvrirFormulaire(l, 'dupliquer'); }}>
            Dupliquer cette opération
          </Button>
        )}
      </>
    ),
  });
}

/** Suppression immédiate, avec « Annuler » dans la notification (la ligne revient sous le même identifiant) */
function useSuppression() {
  const ecrire = useEcriture('budget');
  return (l: Ligne) => ecrire.mutate({ path: `/api/${l.type}/${l.id}`, method: 'DELETE' }, {
    onSuccess: ligne => notifierAnnulable(l.type === 'depenses' ? 'Dépense supprimée' : 'Revenu supprimé', () =>
      ecrire.mutate({ path: `/api/${l.type}/restaurer`, method: 'POST', body: ligne, succes: 'Opération rétablie ✓' })),
  });
}

function libelleJour(date: string, avecAnnee = false) {
  if (date === auj()) return "Aujourd'hui";
  if (date === decalerDate(auj(), -1)) return 'Hier';
  const [a, m, j] = date.split('-').map(Number);
  return JOURS_FR[(new Date(a, m - 1, j).getDay() + 6) % 7] + ' ' + j + ' ' + MOIS_FR[m - 1].toLowerCase() + (avecAnnee ? ' ' + a : '');
}

function LigneOperation({ l, supprimer, onTag }: { l: Ligne; supprimer: (l: Ligne) => void; onTag?: (tag: string) => void }) {
  const dep = l.type === 'depenses';
  return (
    <Group className="ligne-op" wrap="nowrap" gap="sm" px={6} py={8}>
      <Pastille icone={dep ? IconArrowUpRight : IconArrowDownLeft} couleur={dep ? 'rose' : 'bleu'} taille={34} />
      <Box style={{ flex: 1, minWidth: 0 }}>
        <Text fz="sm" fw={600} truncate>{l.titre}</Text>
        {l.detail && <Text fz="xs" c="dimmed" truncate>{l.detail}</Text>}
        {l.tags.length > 0 && (
          <Group gap={4} mt={3}>
            {l.tags.map(t => (
              <Badge key={t} size="xs" variant="light" color="gray" radius="sm" tt="none"
                     style={{ cursor: onTag ? 'pointer' : undefined }} onClick={onTag && (() => onTag(t))}>#{t}</Badge>
            ))}
          </Group>
        )}
      </Box>
      <Text className="chiffre" fw={650} fz="sm" c={dep ? T.dep : T.rev} style={{ whiteSpace: 'nowrap' }}>
        {dep ? '−' : '+'} {fmt(l.montant)}
      </Text>
      <Group gap={0} wrap="nowrap">
        <Tooltip label="Modifier" withArrow>
          <ActionIcon variant="subtle" color="gray" onClick={() => ouvrirFormulaire(l, 'modifier')} aria-label="Modifier" className="suppr">
            <IconPencil size={16} stroke={1.7} />
          </ActionIcon>
        </Tooltip>
        <Tooltip label="Dupliquer (nouvelle opération datée d'aujourd'hui)" withArrow>
          <ActionIcon variant="subtle" color="gray" onClick={() => ouvrirFormulaire(l, 'dupliquer')} aria-label="Dupliquer" className="suppr" visibleFrom="xs">
            <IconCopy size={16} stroke={1.7} />
          </ActionIcon>
        </Tooltip>
        <BoutonSuppr onClick={() => supprimer(l)} />
      </Group>
    </Group>
  );
}

/** Lignes regroupées par jour (déjà triées par date décroissante) */
function ParJour({ lignes, supprimer, onTag, avecAnnee }: {
  lignes: Ligne[]; supprimer: (l: Ligne) => void; onTag?: (t: string) => void; avecAnnee?: boolean;
}) {
  const jours: { date: string; lignes: Ligne[] }[] = [];
  for (const l of lignes) {
    if (jours.at(-1)?.date !== l.date) jours.push({ date: l.date, lignes: [] });
    jours.at(-1)!.lignes.push(l);
  }
  return (
    <>
      {jours.map(j => (
        <Box key={j.date}>
          <Text fz={11} fw={700} c="dimmed" tt="uppercase" lts={0.5} mb={4} px={4}>{libelleJour(j.date, avecAnnee)}</Text>
          <Stack gap={2}>
            {j.lignes.map(l => <LigneOperation key={l.type + l.id} l={l} supprimer={supprimer} onTag={onTag} />)}
          </Stack>
        </Box>
      ))}
    </>
  );
}

function Resume({ label, valeur, couleur }: { label: string; valeur: string; couleur?: string }) {
  return (
    <Box>
      <Text fz={11} c="dimmed" fw={500}>{label}</Text>
      <Text className="chiffre" fw={700} fz={{ base: 15, sm: 17 }} c={couleur}>{valeur}</Text>
    </Box>
  );
}

function Totaux({ dep, rev }: { dep: number; rev: number }) {
  return (
    <Group grow gap="sm" p="sm" style={{ borderRadius: 'var(--mantine-radius-md)', background: 'light-dark(var(--mantine-color-gray-0), rgba(154,161,173,.06))' }}>
      <Resume label="Dépenses" valeur={fmt(dep)} couleur={T.dep} />
      <Resume label="Revenus" valeur={fmt(rev)} couleur={T.rev} />
      <Resume label="Solde" valeur={fmt(rev - dep)} couleur={rev - dep >= 0 ? T.ep : T.neg} />
    </Group>
  );
}

/* ---------- Liste d'un mois ---------- */
export function TransactionsDuMois({ mois, titre = 'Transactions du mois', vide = 'Aucune transaction ce mois', onTag }: {
  mois: string; titre?: string; vide?: string; onTag?: (tag: string) => void;
}) {
  const { data, isPending } = useTransactionsMois(mois);
  const supprimer = useSuppression();
  const [filtre, setFiltre] = useState<'tout' | 'depenses' | 'revenus'>('tout');
  // Catégorie (dépenses) ou source (revenus), codée « type:nom » : un même nom peut exister des deux côtés
  const [rubrique, setRubrique] = useState<string | null>(null);

  const lignes: Ligne[] = data
    ? [...data.depenses.map(ligneDepense), ...data.revenus.map(ligneRevenu)].sort((a, b) => b.date.localeCompare(a.date) || b.id - a.id)
    : [];
  const parType = filtre === 'tout' ? lignes : lignes.filter(l => l.type === filtre);
  const visibles = rubrique ? parType.filter(l => l.type + ':' + l.titre === rubrique) : parType;
  // Totaux de ce qui est affiché : ils suivent les filtres
  const totalDep = visibles.filter(l => l.type === 'depenses').reduce((s, l) => s + l.montant, 0);
  const totalRev = visibles.filter(l => l.type === 'revenus').reduce((s, l) => s + l.montant, 0);

  // Choix proposés : seulement les catégories / sources présentes ce mois, pour le type affiché
  // (le choix en cours reste listé en changeant de mois, même sans opération ce mois-là)
  const noms = (type: Ligne['type']) => [...new Set([
    ...parType.filter(l => l.type === type).map(l => l.titre),
    ...(rubrique?.startsWith(type + ':') ? [rubrique.slice(type.length + 1)] : []),
  ])].sort((a, b) => a.localeCompare(b, 'fr')).map(n => ({ value: type + ':' + n, label: n }));
  const choix = [
    { group: 'Catégories de dépenses', items: noms('depenses') },
    { group: 'Sources de revenus', items: noms('revenus') },
  ].filter(g => g.items.length);

  return (
    <Carte titre={titre} description={lignes.length ? `${lignes.length} opération${lignes.length > 1 ? 's' : ''}` : undefined}
      droite={lignes.length > 0 && (
        <Group gap="xs" wrap="wrap">
          <Select size="xs" w={190} placeholder="Toutes les catégories" data={choix} value={rubrique} onChange={setRubrique}
                  clearable searchable nothingFoundMessage="Aucune" aria-label="Filtrer par catégorie ou source" />
          <SegmentedControl size="xs" value={filtre} data={[{ value: 'tout', label: 'Tout' }, { value: 'depenses', label: 'Dépenses' }, { value: 'revenus', label: 'Revenus' }]}
            onChange={v => {
              setFiltre(v as typeof filtre);
              // La catégorie choisie n'a plus de sens si son type est masqué
              if (rubrique && v !== 'tout' && !rubrique.startsWith(v + ':')) setRubrique(null);
            }} />
        </Group>
      )}>
      {isPending ? <Chargement lignes={5} /> : !lignes.length ? (
        <Vide icone={IconReceipt}>{vide}</Vide>
      ) : (
        <Stack gap="md">
          <Totaux dep={totalDep} rev={totalRev} />
          <ParJour lignes={visibles} supprimer={supprimer} onTag={onTag} />
          {!visibles.length && <Vide>Aucune opération ne correspond à ce filtre ce mois</Vide>}
        </Stack>
      )}
    </Carte>
  );
}

/* ---------- Recherche dans tout l'historique ---------- */
const PAGE = 50;

export function ResultatsRecherche({ q, onTag }: { q: string; onTag: (tag: string) => void }) {
  const [page, setPage] = useState(0);
  useEffect(() => setPage(0), [q]);
  const { data, isPending, isFetching } = useRecherche(q, page * PAGE);
  const supprimer = useSuppression();
  const nbPages = data ? Math.ceil(data.nb / PAGE) : 0;

  return (
    <Carte titre={`Recherche « ${q} »`}
           description={data ? `${data.nb} opération${data.nb > 1 ? 's' : ''} dans tout l'historique` : undefined}>
      {isPending ? <Chargement lignes={5} /> : !data?.nb ? (
        <Vide icone={IconSearch}>
          Aucune opération trouvée. Cherche un mot de la description, une catégorie, un montant exact (ex : 250)
          ou un tag (ex : #voyage).
        </Vide>
      ) : (
        <Stack gap="md" style={{ opacity: isFetching ? 0.6 : 1 }}>
          <Totaux dep={data.total_depenses} rev={data.total_revenus} />
          <ParJour lignes={data.resultats.map(ligneRecherche)} supprimer={supprimer} onTag={onTag} avecAnnee />
          {nbPages > 1 && (
            <Group justify="space-between">
              <Button variant="default" size="xs" disabled={page === 0} onClick={() => setPage(p => p - 1)}>Plus récents</Button>
              <Text fz="xs" c="dimmed">Page {page + 1} / {nbPages}</Text>
              <Button variant="default" size="xs" disabled={page + 1 >= nbPages} onClick={() => setPage(p => p + 1)}>Plus anciens</Button>
            </Group>
          )}
        </Stack>
      )}
    </Carte>
  );
}
