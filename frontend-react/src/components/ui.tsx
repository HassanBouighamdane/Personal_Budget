/* Briques d'interface partagées par tous les écrans */
import { useMemo, useState, type ReactNode } from 'react';
import {
  ActionIcon, Alert, Badge, Box, Card, Group, SimpleGrid, Skeleton, Stack, Table, Text, ThemeIcon, Title, Tooltip, UnstyledButton,
} from '@mantine/core';
import { modals } from '@mantine/modals';
import { IconArrowDownRight, IconArrowUpRight, IconChevronDown, IconChevronUp, IconInbox, IconInfoCircle, IconSelector, IconTrash } from '@tabler/icons-react';

/* ---------- En-tête de page ---------- */
export function EnTetePage({ titre, description, actions }: { titre: ReactNode; description?: ReactNode; actions?: ReactNode }) {
  return (
    <Group justify="space-between" align="flex-end" gap="sm" wrap="wrap" mb={4}>
      <Box>
        <Title order={1} fz={{ base: 22, sm: 26 }} lts={-0.3}>{titre}</Title>
        {description && <Text c="dimmed" fz="sm" mt={2}>{description}</Text>}
      </Box>
      {actions}
    </Group>
  );
}

/* ---------- Cartes ---------- */
export function Carte({ titre, description, icone, droite, children, className }: {
  titre?: ReactNode; description?: ReactNode; icone?: ReactNode; droite?: ReactNode; children: ReactNode; className?: string;
}) {
  return (
    <Card className={className}>
      {(titre || droite) && (
        <Group justify="space-between" mb="md" gap="xs" wrap="wrap" align="flex-start">
          <Group gap="sm" wrap="nowrap" align="flex-start">
            {icone}
            <Box>
              {titre && <Title order={3} fz="md" fw={650}>{titre}</Title>}
              {description && <Text c="dimmed" fz="xs" mt={2}>{description}</Text>}
            </Box>
          </Group>
          {droite}
        </Group>
      )}
      {children}
    </Card>
  );
}

/** Pastille d'icône colorée (cartes, KPI, listes) */
export function Pastille({ icone: Icone, couleur, taille = 36 }: { icone: typeof IconTrash; couleur: string; taille?: number }) {
  return (
    <ThemeIcon variant="light" color={couleur} size={taille} radius="md">
      <Icone size={Math.round(taille * 0.5)} stroke={1.8} />
    </ThemeIcon>
  );
}

export function Info({ children }: { children: ReactNode }) {
  return <Text c="dimmed" fz="sm" lh={1.65}>{children}</Text>;
}

/** Encadré d'aide discret (remplace les cartes « ℹ️ ») */
export function Aide({ titre, children }: { titre: ReactNode; children: ReactNode }) {
  return (
    <Alert variant="light" color="gray" radius="lg" icon={<IconInfoCircle size={18} />} title={titre}
           styles={{ title: { fontSize: 14 }, message: { fontSize: 13, lineHeight: 1.65, color: 'var(--mantine-color-dimmed)' } }}>
      {children}
    </Alert>
  );
}

export function Vide({ children, icone: Icone = IconInbox }: { children: ReactNode; icone?: typeof IconTrash }) {
  return (
    <Stack align="center" gap={8} py={36}>
      <ThemeIcon variant="light" color="gray" size={44} radius="xl"><Icone size={22} stroke={1.6} /></ThemeIcon>
      <Text c="dimmed" fz="sm" ta="center" maw={320}>{children}</Text>
    </Stack>
  );
}

export const Chargement = ({ lignes = 4 }: { lignes?: number }) => (
  <Stack gap="xs">{Array.from({ length: lignes }, (_, i) => <Skeleton key={i} h={32} radius="md" />)}</Stack>
);

/* ---------- KPI ---------- */
export function Kpi({ label, valeur, couleur, aide, badge, icone, teinte }: {
  label: ReactNode; valeur: ReactNode; couleur?: string; aide?: ReactNode; badge?: ReactNode;
  icone?: typeof IconTrash; teinte?: string;
}) {
  return (
    <Card padding="md">
      <Group justify="space-between" align="flex-start" wrap="nowrap" gap="xs">
        <Text fz={{ base: 11, sm: 12 }} c="dimmed" fw={500} lh={1.3}>{label}</Text>
        {icone && <Box visibleFrom="xs"><Pastille icone={icone} couleur={teinte ?? 'gray'} taille={30} /></Box>}
      </Group>
      <Group gap={8} mt={6} align="center" wrap="wrap">
        <Text className="chiffre" fz={{ base: 19, sm: 24 }} fw={700} c={couleur} lh={1.15}>{valeur}</Text>
        {badge}
      </Group>
      {aide && <Text fz="xs" c="dimmed" mt={6} lh={1.45}>{aide}</Text>}
    </Card>
  );
}

export function GrilleKpi({ children }: { children: ReactNode }) {
  return <SimpleGrid cols={{ base: 2, md: 3, lg: 4 }} spacing={{ base: 'xs', sm: 'md' }}>{children}</SimpleGrid>;
}

/** Titre de section entre deux blocs */
export function TitreSection({ children }: { children: ReactNode }) {
  return <Text fz="xs" fw={700} tt="uppercase" c="dimmed" lts={0.6} mt="sm">{children}</Text>;
}

/** Variation par rapport à la période précédente (repris de badge() de l'ancien app.js) */
export function Variation({ actuel, precedent, inverse = false }: { actuel: number; precedent: number; inverse?: boolean }) {
  if (!precedent) return null;
  const delta = (actuel - precedent) / precedent * 100;
  if (Math.abs(delta) < 0.5) return <Badge variant="light" color="gray" size="sm" radius="sm">＝ 0%</Badge>;
  const hausse = delta > 0;
  const bon = inverse ? hausse : !hausse;   // hausse de revenus = bon ; hausse de dépenses = mauvais
  const Fleche = hausse ? IconArrowUpRight : IconArrowDownRight;
  return (
    <Tooltip label="par rapport à la période précédente">
      <Badge variant="light" color={bon ? 'menthe' : 'rouge'} size="sm" radius="sm" leftSection={<Fleche size={12} stroke={2.4} />}>
        {Math.abs(delta).toFixed(0)}%
      </Badge>
    </Tooltip>
  );
}

export function Grille2({ children }: { children: ReactNode }) {
  return <SimpleGrid cols={{ base: 1, md: 2 }} spacing="md">{children}</SimpleGrid>;
}

/* ---------- Confirmation ---------- */
export function confirmer(message: string, action: () => void, libelle = 'Supprimer') {
  modals.openConfirmModal({
    title: <Text fw={650}>Confirmer</Text>,
    centered: true,
    size: 'sm',
    children: <Text fz="sm" c="dimmed">{message}</Text>,
    labels: { confirm: libelle, cancel: 'Annuler' },
    confirmProps: { color: 'rouge' },
    onConfirm: action,
  });
}

export function BoutonSuppr({ onClick, label = 'Supprimer' }: { onClick: () => void; label?: string }) {
  return (
    <Tooltip label={label} withArrow>
      <ActionIcon variant="subtle" color="gray" onClick={onClick} aria-label={label} className="suppr">
        <IconTrash size={16} stroke={1.7} />
      </ActionIcon>
    </Tooltip>
  );
}

/* ---------- Tableaux triables ---------- */
export type Tri<K extends string> = { cle: K; desc: boolean };

export function useTri<T, K extends string>(lignes: T[] | undefined, valeur: (l: T, cle: K) => string | number, initial: Tri<K>) {
  const [tri, setTri] = useState(initial);
  const triees = useMemo(() => {
    if (!lignes) return [];
    const copie = [...lignes];
    copie.sort((a, b) => {
      const va = valeur(a, tri.cle), vb = valeur(b, tri.cle);
      const c = typeof va === 'number' && typeof vb === 'number' ? va - vb : String(va).localeCompare(String(vb), 'fr');
      return tri.desc ? -c : c;
    });
    return copie;
  }, [lignes, tri, valeur]);
  // Nouvelle colonne : texte en A→Z, nombres et dates du plus grand au plus petit
  const basculer = (cle: K) => setTri(t => {
    if (t.cle === cle) return { cle, desc: !t.desc };
    const exemple = lignes?.[0] && valeur(lignes[0], cle);
    return { cle, desc: typeof exemple === 'number' || /^\d{4}-\d{2}-\d{2}/.test(String(exemple)) };
  });
  return { triees, tri, basculer };
}

export function ThTri<K extends string>({ cle, tri, basculer, num, children }: {
  cle: K; tri: Tri<K>; basculer: (k: K) => void; num?: boolean; children: ReactNode;
}) {
  const actif = tri.cle === cle;
  const Icone = actif ? (tri.desc ? IconChevronDown : IconChevronUp) : IconSelector;
  return (
    <Table.Th className={num ? 'num' : undefined}>
      <UnstyledButton onClick={() => basculer(cle)} style={{ font: 'inherit', color: 'inherit' }}>
        <Group gap={4} wrap="nowrap" justify={num ? 'flex-end' : 'flex-start'}>
          {children}
          <Icone size={14} opacity={actif ? 1 : 0.4} />
        </Group>
      </UnstyledButton>
    </Table.Th>
  );
}

/** Tableau responsive : défilement horizontal sur mobile */
export function Tableau({ minWidth = 0, children }: { minWidth?: number; children: ReactNode }) {
  return (
    <Table.ScrollContainer minWidth={minWidth}>
      <Table highlightOnHover verticalSpacing={10} horizontalSpacing="sm" fz="sm">{children}</Table>
    </Table.ScrollContainer>
  );
}
