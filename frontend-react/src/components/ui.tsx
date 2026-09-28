/* Briques d'interface partagées par tous les écrans */
import { useMemo, useState, type ReactNode } from 'react';
import {
  ActionIcon, Badge, Card, Center, Group, SimpleGrid, Skeleton, Stack, Table, Text, Title, Tooltip, UnstyledButton,
} from '@mantine/core';
import { modals } from '@mantine/modals';
import { IconChevronDown, IconChevronUp, IconSelector, IconTrash } from '@tabler/icons-react';

/* ---------- Cartes ---------- */
export function Carte({ titre, droite, children }: { titre?: ReactNode; droite?: ReactNode; children: ReactNode }) {
  return (
    <Card>
      {(titre || droite) && (
        <Group justify="space-between" mb="md" gap="xs" wrap="wrap">
          {titre && <Title order={4} fz="md">{titre}</Title>}
          {droite}
        </Group>
      )}
      {children}
    </Card>
  );
}

export function Info({ children }: { children: ReactNode }) {
  return <Text c="dimmed" fz="sm" lh={1.6}>{children}</Text>;
}

export function Vide({ children }: { children: ReactNode }) {
  return <Center py="xl"><Text c="dimmed" fz="sm" ta="center">{children}</Text></Center>;
}

export const Chargement = ({ lignes = 4 }: { lignes?: number }) => (
  <Stack gap="xs">{Array.from({ length: lignes }, (_, i) => <Skeleton key={i} h={28} radius="sm" />)}</Stack>
);

/* ---------- KPI ---------- */
export function Kpi({ label, valeur, couleur, aide, badge }: {
  label: ReactNode; valeur: ReactNode; couleur?: string; aide?: ReactNode; badge?: ReactNode;
}) {
  return (
    <Card padding="md">
      <Text fz={{ base: 10, sm: 'xs' }} c="dimmed" tt="uppercase" fw={600} lts={0.4}>{label}</Text>
      <Group gap={6} mt={4} align="center" wrap="wrap">
        <Text className="chiffre" fz={{ base: 18, sm: 22 }} fw={700} c={couleur} lh={1.2}>{valeur}</Text>
        {badge}
      </Group>
      {aide && <Text fz="xs" c="dimmed" mt={4}>{aide}</Text>}
    </Card>
  );
}

export function GrilleKpi({ children }: { children: ReactNode }) {
  return <SimpleGrid cols={{ base: 2, md: 3, lg: 4 }} spacing="sm">{children}</SimpleGrid>;
}

/** Variation par rapport à la période précédente (repris de badge() de l'ancien app.js) */
export function Variation({ actuel, precedent, inverse = false }: { actuel: number; precedent: number; inverse?: boolean }) {
  if (!precedent) return null;
  const delta = (actuel - precedent) / precedent * 100;
  if (Math.abs(delta) < 0.5) return <Badge variant="light" color="gray" size="sm">＝</Badge>;
  const hausse = delta > 0;
  const bon = inverse ? hausse : !hausse;   // hausse de revenus = bon ; hausse de dépenses = mauvais
  return (
    <Badge variant="light" color={bon ? 'menthe' : 'rouge'} size="sm">
      {hausse ? '▲' : '▼'} {Math.abs(delta).toFixed(0)}%
    </Badge>
  );
}

export function Grille2({ children }: { children: ReactNode }) {
  return <SimpleGrid cols={{ base: 1, md: 2 }} spacing="md">{children}</SimpleGrid>;
}

/* ---------- Confirmation ---------- */
export function confirmer(message: string, action: () => void, libelle = 'Supprimer') {
  modals.openConfirmModal({
    title: 'Confirmation',
    centered: true,
    children: <Text fz="sm">{message}</Text>,
    labels: { confirm: libelle, cancel: 'Annuler' },
    confirmProps: { color: 'rouge' },
    onConfirm: action,
  });
}

export function BoutonSuppr({ onClick, label = 'Supprimer' }: { onClick: () => void; label?: string }) {
  return (
    <Tooltip label={label} withArrow>
      <ActionIcon variant="subtle" color="gray" onClick={onClick} aria-label={label}>
        <IconTrash size={16} />
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
      <Table highlightOnHover verticalSpacing={8} fz="sm">{children}</Table>
    </Table.ScrollContainer>
  );
}
