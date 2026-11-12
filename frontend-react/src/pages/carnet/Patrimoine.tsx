/* Suivi — patrimoine net : liquidités, Bourse, autres actifs (valeur saisie à la main), dettes et prêts.
 * Trois indicateurs en découlent : la réserve de sécurité, une estimation de la zakat et la liberté financière. */
import { useEffect, useState, type ReactNode } from 'react';
import {
  ActionIcon, Alert, Badge, Box, Button, Checkbox, Divider, Grid, Group, NumberInput, Progress, SegmentedControl, Select, SimpleGrid, Stack, Text,
  TextInput, Tooltip,
} from '@mantine/core';
import { DatePickerInput } from '@mantine/dates';
import { modals } from '@mantine/modals';
import {
  IconBuildingBank, IconChartLine, IconCoin, IconInfoCircle, IconMoonStars, IconPencil, IconShieldCheck, IconSunrise, IconWallet,
} from '@tabler/icons-react';

import { toast } from '../../lib/api';
import { auj, dateFr, fmt, jjmm, jjmmaa, libelleMois, lireMontant } from '../../lib/format';
import { C, T, signe } from '../../lib/palette';
import type { ChartData } from 'chart.js';
import type { Actif, Patrimoine, Reconstitution } from '../../lib/types';
import { useCoursPasses, useEcriture, useHistoriquePatrimoine, usePatrimoine } from '../../lib/queries';
import { Graphique, optionsSeries } from '../../components/Graphique';
import { ChampDate, ChampMontant } from '../../components/champs';
import { BoutonSuppr, Carte, Chargement, confirmer, Info, Kpi, Pastille, Vide } from '../../components/ui';

const texte = (n: number) => String(n).replace('.', ',');
const nombre = (n: number) => String(n).replace('.', ',');

/* ---------- Autres actifs ---------- */
function FormActif({ p, existant, onTermine }: { p: Patrimoine; existant?: Actif; onTermine?: () => void }) {
  const ecrire = useEcriture('patrimoine');
  const [nom, setNom] = useState(existant?.nom ?? '');
  const [type, setType] = useState(existant?.type ?? p.types_actifs[0].type);
  const [valeur, setValeur] = useState(existant ? texte(existant.valeur) : '');
  const [verse, setVerse] = useState(existant?.verse ? texte(existant.verse) : '');
  const [zakat, setZakat] = useState(existant?.zakat ?? p.types_actifs[0].zakat);
  const [date, setDate] = useState(existant?.maj_le ?? auj());
  const [note, setNote] = useState(existant?.note ?? '');
  const types = [...new Set([...p.types_actifs.map(t => t.type), ...(existant ? [existant.type] : [])])];

  function enregistrer() {
    const v = lireMontant(valeur);
    const s = verse.trim() ? lireMontant(verse) : 0;
    if (!nom.trim()) return toast('Indique le nom', false);
    if (isNaN(v) || v < 0) return toast('Valeur invalide', false);
    if (isNaN(s) || s < 0) return toast('Montant versé invalide', false);
    const body = { nom: nom.trim(), type, valeur: v, verse: s, zakat, maj_le: date, note: note.trim() };
    ecrire.mutate(
      existant ? { path: `/api/patrimoine/actifs/${existant.id}`, method: 'PUT', body, succes: 'Actif mis à jour ✓' }
               : { path: '/api/patrimoine/actifs', method: 'POST', body, succes: 'Actif ajouté ✓' },
      { onSuccess: () => { if (!existant) { setNom(''); setValeur(''); setVerse(''); setNote(''); } onTermine?.(); } },
    );
  }

  return (
    <Stack gap="sm">
      <TextInput label="Nom" placeholder="ex : Livret CIH, lingot 10 g, appartement" value={nom} onChange={e => setNom(e.currentTarget.value)} maxLength={100} />
      <Select label="Type" data={types} value={type} allowDeselect={false}
              onChange={v => { if (v) { setType(v); setZakat(p.types_actifs.find(t => t.type === v)?.zakat ?? zakat); } }} />
      <SimpleGrid cols={{ base: 1, xs: 2 }} spacing="sm">
        <ChampMontant label="Valeur actuelle" value={valeur} onChange={setValeur} />
        <ChampDate label="Valeur relevée le" value={date} onChange={setDate} />
      </SimpleGrid>
      <ChampMontant label="Argent versé depuis ton épargne" placeholder="0" value={verse} onChange={setVerse}
                    description="Ce que tu y as mis sans le saisir en dépense. Laisse vide s'il date d'avant l'application, ou si tu l'as saisi en dépense." />
      <Checkbox label="Compte pour la zakat" checked={zakat} onChange={e => setZakat(e.currentTarget.checked)} />
      <TextInput label="Note (optionnel)" value={note} onChange={e => setNote(e.currentTarget.value)} maxLength={1000} />
      <Button mt="xs" onClick={enregistrer} loading={ecrire.isPending}>{existant ? 'Enregistrer' : "Ajouter l'actif"}</Button>
    </Stack>
  );
}

function LigneActif({ a, p }: { a: Actif; p: Patrimoine }) {
  const ecrire = useEcriture('patrimoine');
  const gain = a.verse > 0 ? a.valeur - a.verse : null;
  const ouvrir = (titre: string, contenu: (fermer: () => void) => ReactNode) => {
    const id = modals.open({ title: <Text fw={650}>{titre}</Text>, centered: true, children: contenu(() => modals.close(id)) });
  };
  return (
    <Group className="ligne-op" wrap="nowrap" gap="sm" px={6} py={8} align="flex-start">
      <Pastille icone={IconCoin} couleur="marque" taille={34} />
      <Box style={{ flex: 1, minWidth: 0 }}>
        <Group justify="space-between" wrap="nowrap" gap="xs">
          <Text fz="sm" fw={600} truncate>{a.nom}</Text>
          <Text fz="sm" fw={700} className="chiffre" style={{ whiteSpace: 'nowrap' }}>{fmt(a.valeur)}</Text>
        </Group>
        <Text fz="xs" c="dimmed" truncate>{a.type} · valeur du {dateFr(a.maj_le)}</Text>
        {a.note && <Text fz="xs" c="dimmed" fs="italic" lineClamp={2} mt={2}>{a.note}</Text>}
        {gain !== null && (
          <Badge size="xs" variant="light" color={gain >= 0 ? 'emeraude' : 'rouge'} mt={4}>
            {gain >= 0 ? '+' : '−'}{fmt(Math.abs(gain))} sur {fmt(a.verse)} versés
          </Badge>
        )}
      </Box>
      <Group gap={0} wrap="nowrap">
        <Tooltip label="Mettre à jour" withArrow>
          <ActionIcon variant="subtle" color="gray" className="suppr" aria-label="Mettre à jour"
                      onClick={() => ouvrir(a.nom, fermer => <FormActif p={p} existant={a} onTermine={fermer} />)}>
            <IconPencil size={16} stroke={1.7} />
          </ActionIcon>
        </Tooltip>
        <BoutonSuppr onClick={() => confirmer(`Supprimer « ${a.nom} » de ton patrimoine ?`, () =>
          ecrire.mutate({ path: `/api/patrimoine/actifs/${a.id}`, method: 'DELETE', succes: 'Actif supprimé' }))} />
      </Group>
    </Group>
  );
}

/* ---------- Composition ---------- */
function Composition({ p }: { p: Patrimoine }) {
  const lignes: { nom: string; aide: string; valeur: number }[] = [
    { nom: 'Liquidités', aide: 'Solde de départ + épargne du Budget, moins ce qui est parti en Bourse, dans tes actifs ou en prêts', valeur: p.liquidites },
    { nom: 'Compte Bourse', aide: 'Titres à leur valeur de marché + espèces', valeur: p.bourse },
    { nom: 'Autres actifs', aide: 'Valeurs saisies ci-dessous', valeur: p.autres_actifs },
    { nom: 'On me doit', aide: 'Prêts en cours (onglet Dettes et prêts)', valeur: p.creances },
    { nom: 'Je dois', aide: 'Emprunts en cours', valeur: -p.dettes },
  ].filter(l => l.valeur !== 0);
  const base = lignes.reduce((s, l) => s + Math.abs(l.valeur), 0) || 1;
  return (
    <Stack gap="sm">
      {!lignes.length && <Info>Rien à afficher pour l'instant.</Info>}
      {lignes.map(l => (
        <Box key={l.nom}>
          <Group justify="space-between" wrap="nowrap" gap="xs">
            <Tooltip label={l.aide} multiline w={260} withArrow><Text fz="sm">{l.nom}</Text></Tooltip>
            <Text fz="sm" fw={600} className="chiffre" c={l.valeur < 0 ? T.neg : undefined}>{fmt(l.valeur)}</Text>
          </Group>
          <Progress value={Math.abs(l.valeur) / base * 100} color={l.valeur < 0 ? 'rouge' : 'marque'} size={6} radius="xl" mt={4} />
        </Box>
      ))}
    </Stack>
  );
}

/* ---------- Réglages : solde de départ ---------- */
function reglages(p: Patrimoine) {
  return { solde_depart: p.solde_depart, prix_or_gramme: p.zakat.prix_or_gramme, debut_hawl: p.zakat.debut_hawl };
}

function SoldeDepart({ p }: { p: Patrimoine }) {
  const ecrire = useEcriture('patrimoine');
  const [solde, setSolde] = useState(texte(p.solde_depart));
  useEffect(() => setSolde(texte(p.solde_depart)), [p.solde_depart]);
  function enregistrer() {
    const v = solde.trim() ? lireMontant(solde) : 0;
    if (isNaN(v)) return toast('Montant invalide', false);
    ecrire.mutate({ path: '/api/patrimoine/reglages', method: 'PUT', body: { ...reglages(p), solde_depart: v }, succes: 'Solde de départ enregistré ✓' });
  }
  return (
    <Stack gap="xs">
      <Group gap="xs" wrap="nowrap" align="flex-end">
        <ChampMontant label="Solde de départ" style={{ flex: 1 }} value={solde} onChange={setSolde} />
        <Button variant="default" onClick={enregistrer} loading={ecrire.isPending}>Enregistrer</Button>
      </Group>
      <Info>L'argent que tu avais déjà (banque, espèces) avant ta première saisie dans l'application : sans lui, tes liquidités ne comptent que l'épargne faite depuis.</Info>
    </Stack>
  );
}

/* ---------- Réserve de sécurité (aussi affichée sur l'accueil) ---------- */
/** Vert à partir de 6 mois de dépenses couverts, ambre de 3 à 6, rouge en dessous ; gris sans estimation */
export const couleurReserve = (mois: number | null) =>
  mois === null ? 'gray' : mois >= 6 ? 'emeraude' : mois >= 3 ? 'ambre' : 'rouge';

export function Reserve({ p }: { p: Patrimoine }) {
  const r = p.reserve;
  if (r.mois_couverts === null) {
    return <Info>Il faut au moins un mois terminé avec des dépenses pour estimer combien de temps ton argent te ferait tenir.</Info>;
  }
  const couleur = couleurReserve(r.mois_couverts);
  const conseil = r.mois_couverts >= 6 ? 'Réserve confortable : au-delà de 6 mois, le surplus peut travailler ailleurs.'
    : r.mois_couverts >= 3 ? 'Réserve correcte. On vise en général entre 3 et 6 mois de dépenses.'
    : `Réserve fragile : il manque ${fmt(Math.max(0, r.depense_moyenne * 3 - r.disponible))} pour atteindre 3 mois de dépenses.`;
  return (
    <Stack gap="sm">
      <Text fz="sm">
        Ton argent disponible couvre <Text span fw={700} className="chiffre">{nombre(r.mois_couverts)} mois</Text> de dépenses.
      </Text>
      <Progress value={Math.min(100, r.mois_couverts / 6 * 100)} color={couleur} size={10} radius="xl" />
      <Info>
        {fmt(r.disponible)} disponibles (liquidités et comptes épargne), pour {fmt(r.depense_moyenne)} dépensés par mois en moyenne
        sur {r.nb_mois_base === 1 ? 'le dernier mois terminé' : `les ${r.nb_mois_base} derniers mois terminés`}. {conseil}
      </Info>
    </Stack>
  );
}

/* ---------- Zakat ---------- */
function Zakat({ p }: { p: Patrimoine }) {
  const z = p.zakat;
  const ecrire = useEcriture('patrimoine');
  const [prix, setPrix] = useState(z.prix_or_gramme ? texte(z.prix_or_gramme) : '');
  const [debut, setDebut] = useState<string | null>(z.debut_hawl);
  useEffect(() => { setPrix(z.prix_or_gramme ? texte(z.prix_or_gramme) : ''); setDebut(z.debut_hawl); }, [z.prix_or_gramme, z.debut_hawl]);

  function enregistrer(nouveauDebut: string | null = debut, succes = 'Réglages de la zakat enregistrés ✓') {
    const v = prix.trim() ? lireMontant(prix) : 0;
    if (isNaN(v) || v < 0) return toast("Prix de l'or invalide", false);
    ecrire.mutate({ path: '/api/patrimoine/reglages', method: 'PUT', body: { ...reglages(p), prix_or_gramme: v, debut_hawl: nouveauDebut }, succes });
  }
  const detail: [string, number][] = [
    ['Liquidités', z.detail.liquidites], ['Compte Bourse', z.detail.bourse], ['Actifs cochés', z.detail.actifs],
    ['On me doit', z.detail.creances], ['Je dois', -z.detail.dettes],
  ];

  return (
    <Stack gap="sm">
      <SimpleGrid cols={{ base: 1, xs: 2 }} spacing="sm">
        <ChampMontant label="Prix du gramme d'or" value={prix} onChange={setPrix} />
        <DatePickerInput label="Début de l'année en cours" placeholder="—"
                         value={debut} onChange={setDebut} clearable valueFormat="DD/MM/YYYY" maxDate={auj()} popoverProps={{ withinPortal: true }} />
      </SimpleGrid>
      <Group gap="sm" wrap="nowrap" align="flex-start">
        <Button variant="default" onClick={() => enregistrer()} loading={ecrire.isPending} style={{ flexShrink: 0 }}>Enregistrer</Button>
        <Text fz="xs" c="dimmed" lh={1.5}>Le nisab vaut 85 g d'or. L'année démarre le jour où ton avoir l'a atteint, ou à ta dernière zakat.</Text>
      </Group>

      {z.nisab === null ? <Info>Indique le prix du gramme d'or pour comparer ton avoir au nisab.</Info> : (
        <>
          <Divider color="var(--bordure-douce)" />
          <Group justify="space-between" align="flex-end" wrap="wrap" gap="xs">
            <Box>
              <Text fz="xs" c="dimmed">{z.atteint ? 'Zakat estimée (2,5 %)' : 'Sous le nisab : rien à payer'}</Text>
              <Text className="chiffre" fz={24} fw={700} c={z.atteint ? T.ep : 'dimmed'}>{fmt(z.montant)}</Text>
            </Box>
            <Text fz="xs" c="dimmed" ta="right">avoir compté : {fmt(z.assiette)}<br />nisab : {fmt(z.nisab)}</Text>
          </Group>
          <Progress value={Math.min(100, z.assiette / z.nisab * 100)} color={z.atteint ? 'emeraude' : 'gray'} size={8} radius="xl" />
          <Box>
            {detail.filter(([, v]) => v !== 0).map(([nom, v]) => (
              <Group key={nom} justify="space-between" gap="xs">
                <Text fz="xs" c="dimmed">{nom}</Text>
                <Text fz="xs" className="chiffre" c={v < 0 ? T.neg : 'dimmed'}>{fmt(v)}</Text>
              </Group>
            ))}
          </Box>
          {z.atteint && z.echeance && z.jours_restants !== null && (
            <Alert variant="light" color={z.jours_restants <= 0 ? 'ambre' : 'gray'} p="xs" icon={<IconMoonStars size={18} />}>
              <Group justify="space-between" gap="xs" wrap="wrap">
                <Text fz="sm">
                  {z.jours_restants > 0 ? <>À payer le <b>{dateFr(z.echeance)}</b>, dans {z.jours_restants} jour{z.jours_restants > 1 ? 's' : ''}.</>
                    : z.jours_restants === 0 ? <>À payer <b>aujourd'hui</b>.</>
                    : <>Due depuis le <b>{dateFr(z.echeance)}</b>.</>}
                </Text>
                {z.jours_restants <= 0 && (
                  <Button size="compact-sm" variant="light" color="emeraude"
                          onClick={() => confirmer("Démarrer une nouvelle année à partir d'aujourd'hui ?", () => enregistrer(auj(), 'Nouvelle année démarrée ✓'), 'Zakat payée')}>
                    Zakat payée
                  </Button>
                )}
              </Group>
            </Alert>
          )}
          {z.atteint && !z.echeance && <Info>Indique le début de l'année en cours pour connaître la date d'échéance (une année lunaire, 354 jours, plus tard).</Info>}
        </>
      )}
      <Alert variant="light" color="gray" p="xs" icon={<IconInfoCircle size={18} />}>
        <Text fz="xs" c="dimmed" lh={1.55}>
          Estimation à vérifier : les règles varient selon les avis (actions gardées longtemps, dettes déductibles, nisab calculé sur l'or
          ou sur l'argent). Le compte Bourse est pris à sa valeur de marché ; décoche un actif pour le sortir du calcul.
        </Text>
      </Alert>
    </Stack>
  );
}

/* ---------- Liberté financière ---------- */
const pct = (v: number) => (Math.round(v * 1000) / 10).toLocaleString('fr-FR') + ' %';
const annees = (v: number) => `${nombre(v)} an${v >= 2 ? 's' : ''}`;

function Liberte({ p }: { p: Patrimoine }) {
  const l = p.liberte;
  const ecrire = useEcriture('patrimoine');
  const [retrait, setRetrait] = useState<string | number>(l.taux_retrait * 100);
  const [rendement, setRendement] = useState<string | number>(l.rendement * 100);
  useEffect(() => { setRetrait(l.taux_retrait * 100); setRendement(l.rendement * 100); }, [l.taux_retrait, l.rendement]);

  function enregistrer() {
    const r = Number(retrait), d = Number(rendement);
    if (!(r > 0 && r <= 20)) return toast('Taux de retrait entre 0 et 20 %', false);
    if (isNaN(d) || d < -10 || d > 30) return toast('Rendement entre −10 et 30 %', false);
    ecrire.mutate({ path: '/api/patrimoine/reglages', method: 'PUT',
                    body: { ...reglages(p), taux_retrait: r / 100, rendement: d / 100 }, succes: 'Réglages enregistrés ✓' });
  }

  const reglagesForm = (
    <Group gap="xs" wrap="nowrap" align="flex-end">
      <NumberInput label="Taux de retrait" value={retrait} onChange={setRetrait} min={0.5} max={20} step={0.5} decimalScale={2}
                   decimalSeparator="," rightSection="%" style={{ flex: 1 }} />
      <NumberInput label="Rendement après inflation" value={rendement} onChange={setRendement} min={-10} max={30} step={0.5} decimalScale={2}
                   decimalSeparator="," rightSection="%" style={{ flex: 1 }} />
      <Button variant="default" onClick={enregistrer} loading={ecrire.isPending} style={{ flexShrink: 0 }}>Enregistrer</Button>
    </Group>
  );

  if (l.cible === undefined || l.depense_annuelle === undefined || l.epargne_annuelle === undefined) {
    return <Info>Il faut au moins un mois terminé avec des dépenses pour estimer ton objectif de liberté financière.</Info>;
  }
  const multiple = Math.round(1 / l.taux_retrait * 10) / 10;
  return (
    <Stack gap="sm">
      <Text fz="sm">
        Ton patrimoine couvre <Text span fw={700} className="chiffre">{annees(l.annees_couvertes ?? 0)}</Text> de ton train de vie.
      </Text>
      <Box>
        <Group justify="space-between" gap="xs" mb={4}>
          <Text fz="xs" c="dimmed">{fmt(Math.max(l.patrimoine, 0))} sur {fmt(l.cible)}</Text>
          <Text fz="xs" fw={700} className="chiffre">{pct(l.progression ?? 0)}</Text>
        </Group>
        <Progress value={Math.min(100, (l.progression ?? 0) * 100)} color="emeraude" size={10} radius="xl" />
      </Box>
      <Info>
        Objectif : {nombre(multiple)} × tes {fmt(l.depense_annuelle)} de dépenses par an (retrait de {pct(l.taux_retrait)} par an).{' '}
        {l.date_atteinte && l.annees_restantes !== null && l.annees_restantes !== undefined
          ? (l.annees_restantes === 0 ? <b>Objectif atteint.</b>
            : <>En épargnant {fmt(l.epargne_annuelle)} par an à {pct(l.rendement)} de rendement, tu l'atteindrais
                vers <b>{libelleMois(l.date_atteinte.slice(0, 7)).toLowerCase()}</b>, dans {annees(l.annees_restantes)}.</>)
          : l.epargne_annuelle <= 0 ? <>Ton épargne des derniers mois est nulle ou négative : à ce rythme, l'objectif n'est pas atteignable.</>
          : <>À ce rythme, l'objectif n'est pas atteint avant 100 ans.</>}
      </Info>
      {l.annees_gagnees !== null && l.annees_gagnees !== undefined && l.annees_gagnees > 0 && (
        <Alert variant="light" color="emeraude" p="xs" icon={<IconSunrise size={18} />}>
          <Text fz="sm">
            Dépenser {fmt(l.economie_simulee ?? 0)} de moins par mois te ferait gagner <b>{annees(l.annees_gagnees)}</b> :
            ton patrimoine grossit plus vite <i>et</i> ton objectif baisse.
          </Text>
        </Alert>
      )}
      <Divider color="var(--bordure-douce)" />
      {reglagesForm}
      <Text fz="xs" c="dimmed" lh={1.55}>
        Moyennes sur {l.nb_mois_base === 1 ? 'le dernier mois terminé' : `les ${l.nb_mois_base} derniers mois terminés`}.
        {l.exclus > 0 && <> Logement et véhicule ({fmt(l.exclus)}) exclus : ils ne produisent pas de quoi vivre.</>}
        {' '}La règle des 4 % vient d'études américaines : 3,5 % est plus prudent.
      </Text>
    </Stack>
  );
}

/* ---------- Évolution (patrimoine noté chaque jour) ---------- */
const PERIODES_COURBE = [{ value: '90', label: '3 mois' }, { value: '365', label: '1 an' }, { value: 'tout', label: 'Tout' }];

/** Date AAAA-MM-JJ ↔ abscisse en millisecondes (UTC) : l'axe respecte ainsi le temps réel entre des
 *  fins de mois reconstituées et des points quotidiens */
const abscisse = (d: string) => Date.UTC(+d.slice(0, 4), +d.slice(5, 7) - 1, +d.slice(8, 10));
const dateAbscisse = (x: number) => new Date(x).toISOString().slice(0, 10);

/** Cours relevés sur les relevés du courtier, pour une fin de mois reconstituée */
function TableCoursPasses({ jour, fermer }: { jour: string; fermer: () => void }) {
  const { data, isPending } = useCoursPasses(jour);
  const ecrire = useEcriture('patrimoine');
  const [valeurs, setValeurs] = useState<Record<string, string>>({});
  useEffect(() => {
    if (data) setValeurs(Object.fromEntries(data.map(c => [c.titre, c.saisi === null ? '' : texte(c.saisi)])));
  }, [data]);
  if (isPending || !data) return <Chargement lignes={3} />;
  if (!data.length) return <Info>Aucun titre détenu le {dateFr(jour)} : la Bourse de ce jour-là n'est faite que d'espèces.</Info>;

  function enregistrer() {
    const cours = data!.map(c => ({ titre: c.titre, v: (valeurs[c.titre] ?? '').trim() }))
      .map(({ titre, v }) => ({ titre, cours: v ? lireMontant(v) : null }));
    if (cours.some(c => c.cours !== null && (isNaN(c.cours) || c.cours <= 0))) return toast('Cours invalide', false);
    ecrire.mutate({ path: '/api/patrimoine/cours-passes', method: 'PUT', body: { jour, cours }, succes: 'Cours enregistrés, courbe recalculée ✓' },
                  { onSuccess: fermer });
  }

  return (
    <Stack gap="sm">
      {data.map(c => (
        <ChampMontant key={c.titre} label={`${c.titre} · ${nombre(c.quantite)} titre${c.quantite > 1 ? 's' : ''}`}
                      value={valeurs[c.titre] ?? ''} onChange={v => setValeurs(s => ({ ...s, [c.titre]: v }))}
                      placeholder={c.estime === null ? '' : texte(c.estime)}
                      description={c.estime === null ? 'Aucun cours connu à cette date'
                        : `Sans saisie : ${fmt(c.estime)} (${c.source === 'actuel' ? 'cours relevé' : 'dernière transaction'} du ${dateFr(c.source_date!)})`} />
      ))}
      <Text size="xs" c="dimmed">Laisse vide pour garder le cours de la dernière transaction.</Text>
      <Button mt="xs" onClick={enregistrer} loading={ecrire.isPending}>Enregistrer et recalculer</Button>
    </Stack>
  );
}

function CoursFinDeMois({ jours, fermer }: { jours: string[]; fermer: () => void }) {
  const [jour, setJour] = useState(jours[0]);
  return (
    <Stack gap="md">
      <Text size="sm" c="dimmed">
        Sans saisie, chaque titre est compté au prix de ta dernière transaction. Le relevé de portefeuille de fin de mois
        de ton courtier donne le vrai cours : il remplace l'estimation pour ce mois.
      </Text>
      <Select label="Fin de mois" data={jours.map(j => ({ value: j, label: `${libelleMois(j)} (${dateFr(j)})` }))}
              value={jour} allowDeselect={false} searchable onChange={v => v && setJour(v)} />
      <TableCoursPasses key={jour} jour={jour} fermer={fermer} />
    </Stack>
  );
}

function Evolution() {
  const [periode, setPeriode] = useState('365');
  const { data, isPending } = useHistoriquePatrimoine(periode === 'tout' ? null : Number(periode));
  const tout = useHistoriquePatrimoine(null);   // pour savoir s'il existe des mois reconstitués hors de la période
  const ecrire = useEcriture('patrimoine');
  const choix = <SegmentedControl size="xs" value={periode} onChange={setPeriode} data={PERIODES_COURBE} />;
  const points = data ?? [];
  const estimes = (tout.data ?? []).filter(p => p.estime).map(p => p.date).reverse();
  const premier = points[0], dernier = points.at(-1);
  const ecart = premier && dernier ? dernier.total - premier.total : 0;
  // Plus d'un an affiché : l'année devient utile sous chaque date
  const format = premier && dernier && dernier.date.slice(0, 4) !== premier.date.slice(0, 4) ? jjmmaa : jjmm;
  const enPointilles = points.some(p => p.estime);

  function reconstituer() {
    ecrire.mutate({ path: '/api/patrimoine/historique/reconstituer', method: 'POST' }, {
      onSuccess: r => {
        const n = (r as Reconstitution).points;
        toast(n ? `${n} fin${n > 1 ? 's' : ''} de mois reconstituée${n > 1 ? 's' : ''} ✓` : 'Aucun mois passé à reconstituer');
        if (n) setPeriode('tout');
      },
    });
  }
  function ouvrirCours() {
    const id = modals.open({ title: <Text fw={650}>Cours de fin de mois</Text>, centered: true,
                             children: <CoursFinDeMois jours={estimes} fermer={() => modals.close(id)} /> });
  }

  const actions = estimes.length ? (
    <Group justify="space-between" gap="xs" mt="sm">
      <Text size="xs" c="dimmed" style={{ flex: '1 1 220px' }}>
        Pointillés : fins de mois reconstituées, titres au cours de la dernière transaction sauf cours saisi. Recalculées chaque matin.
      </Text>
      <Group gap="xs">
        <Button size="compact-sm" variant="light" onClick={ouvrirCours}>Cours de fin de mois</Button>
        <Button size="compact-sm" variant="subtle" onClick={reconstituer} loading={ecrire.isPending}>Recalculer</Button>
      </Group>
    </Group>
  ) : (
    <Group justify="space-between" gap="xs" mt="sm">
      <Text size="xs" c="dimmed" style={{ flex: '1 1 220px' }}>
        Les mois d'avant peuvent être estimés à partir de tes saisies : un point par fin de mois.
      </Text>
      <Button size="compact-sm" variant="light" onClick={reconstituer} loading={ecrire.isPending}>Reconstituer les mois passés</Button>
    </Group>
  );

  const base = optionsSeries();
  return (
    <Carte titre="Évolution" icone={<Pastille icone={IconChartLine} couleur="emeraude" />} droite={choix}
           description={points.length >= 2
             ? <>Depuis le {dateFr(premier!.date)} : <Text span inherit fw={600} c={signe(ecart)}>{ecart >= 0 ? '+' : '−'}{fmt(Math.abs(ecart))}</Text></>
             : 'Ton patrimoine, noté chaque jour'}>
      {isPending ? <Chargement lignes={3} /> : points.length < 2 ? (
        <Info>
          {points.length
            ? <>La courbe se construit jour après jour depuis le {dateFr(points[0].date)} : ton patrimoine est noté chaque matin et à chaque ouverture de cet écran.</>
            : <>Ton patrimoine sera noté chaque jour à partir d'aujourd'hui.</>}
        </Info>
      ) : (
        <Graphique type="line" hauteur={240} options={{
          ...base,
          scales: { ...base.scales, x: { type: 'linear', border: { display: false }, grid: { display: false },
            min: abscisse(premier!.date), max: abscisse(dernier!.date),
            ticks: { maxTicksLimit: 7, callback: v => format(dateAbscisse(Number(v))) } } },
          plugins: { legend: { position: 'top', align: 'end' }, tooltip: { callbacks: {
            title: items => items.length ? (p => dateFr(p.date) + (p.estime ? ' · estimé' : ''))(points[items[0].dataIndex]) : '',
            label: ctx => `${ctx.dataset.label} : ${fmt(ctx.parsed.y ?? 0)}`,
          } } },
        }} data={{
          datasets: [
            { label: 'Patrimoine net', data: points.map(p => ({ x: abscisse(p.date), y: p.total })), borderColor: C.ep,
              backgroundColor: 'rgba(16,185,129,.12)', fill: true, tension: .25,
              pointRadius: points.map(p => p.estime || points.length > 60 ? 0 : 2),
              segment: enPointilles ? { borderDash: (ctx: { p1DataIndex: number }) => points[ctx.p1DataIndex]?.estime ? [6, 4] : undefined } : undefined },
            ...(points.some(p => p.bourse) ? [{ label: 'dont Bourse', data: points.map(p => ({ x: abscisse(p.date), y: p.bourse })),
              borderColor: C.rev, borderWidth: 1.5, tension: .25, pointRadius: 0 }] : []),
          ],
        } as ChartData}
        />
      )}
      {!isPending && actions}
    </Carte>
  );
}

/* ---------- Page ---------- */
export function VuePatrimoine() {
  const { data: p, isPending } = usePatrimoine();
  if (isPending || !p) return <Chargement lignes={6} />;
  const r = p.reserve;

  return (
    <Stack gap="lg">
      <SimpleGrid cols={{ base: 2, sm: 4 }} spacing={{ base: 'xs', sm: 'md' }}>
        <Kpi label="Patrimoine net" valeur={fmt(p.total)} couleur={signe(p.total)} icone={IconBuildingBank} teinte="emeraude"
             aide="Tout ce que tu possèdes, moins ce que tu dois" />
        <Kpi label="Réserve de sécurité" icone={IconShieldCheck} teinte="marque"
             valeur={r.mois_couverts === null ? '—' : `${nombre(r.mois_couverts)} mois`}
             couleur={r.mois_couverts === null ? undefined : r.mois_couverts >= 3 ? T.ep : T.neg}
             aide={r.mois_couverts === null ? 'pas encore de mois terminé' : `de dépenses couverts par ${fmt(r.disponible)}`} />
        <Kpi label="Zakat estimée" icone={IconMoonStars} teinte="ambre"
             valeur={p.zakat.nisab === null ? '—' : fmt(p.zakat.montant)}
             aide={p.zakat.nisab === null ? "indique le prix de l'or" : p.zakat.atteint
               ? (p.zakat.echeance ? `à payer le ${dateFr(p.zakat.echeance)}` : 'nisab atteint') : 'sous le nisab'} />
        <Kpi label="Liberté financière" icone={IconSunrise} teinte="emeraude"
             valeur={p.liberte.progression === undefined ? '—' : pct(p.liberte.progression)}
             aide={p.liberte.progression === undefined ? 'pas encore de mois terminé'
               : p.liberte.date_atteinte ? (p.liberte.annees_restantes === 0 ? 'objectif atteint' : `vers ${p.liberte.date_atteinte.slice(0, 4)}`)
               : "de l'objectif"} />
      </SimpleGrid>
      <Evolution />
      <Grid gap="lg" align="flex-start">
        <Grid.Col span={{ base: 12, md: 5 }}>
          <Stack gap="lg">
            <Carte titre="Ajouter un actif" description="Or, compte épargne, placement, bien immobilier : ce qui n'est ni dans le Budget ni en Bourse"
                   icone={<Pastille icone={IconCoin} couleur="marque" />}>
              <FormActif p={p} />
            </Carte>
            <Carte titre="Argent d'avant l'application" icone={<Pastille icone={IconWallet} couleur="gray" />}>
              <SoldeDepart p={p} />
            </Carte>
          </Stack>
        </Grid.Col>
        <Grid.Col span={{ base: 12, md: 7 }}>
          <Stack gap="lg">
            <Carte titre="Composition" description="Survole un nom pour voir ce qu'il contient"
                   droite={<Text className="chiffre" fz="xl" fw={700} c={signe(p.total)}>{fmt(p.total)}</Text>}>
              <Composition p={p} />
            </Carte>
            <Carte titre="Autres actifs" description={p.actifs.length ? 'Mets leur valeur à jour de temps en temps' : undefined}
                   droite={p.actifs.length > 0 && <Text className="chiffre" fw={700}>{fmt(p.autres_actifs)}</Text>}>
              {!p.actifs.length ? <Vide icone={IconCoin}>Aucun actif saisi : ajoute ton or, ton compte épargne ou un bien</Vide>
                : <Stack gap={2}>{p.actifs.map(a => <LigneActif key={a.id} a={a} p={p} />)}</Stack>}
            </Carte>
            <Carte titre="Réserve de sécurité" description="Combien de temps tu tiendrais sans revenu" icone={<Pastille icone={IconShieldCheck} couleur="marque" />}>
              <Reserve p={p} />
            </Carte>
            <Carte titre="Liberté financière" description="Vivre de ton patrimoine sans salaire : où tu en es, et quand"
                   icone={<Pastille icone={IconSunrise} couleur="emeraude" />}>
              <Liberte p={p} />
            </Carte>
            <Carte titre="Zakat" description="Ton avoir comparé au nisab, et la date d'échéance" icone={<Pastille icone={IconMoonStars} couleur="ambre" />}>
              <Zakat p={p} />
            </Carte>
          </Stack>
        </Grid.Col>
      </Grid>
    </Stack>
  );
}
