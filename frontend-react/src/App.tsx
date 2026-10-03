import { useEffect, useState } from 'react';
import {
  ActionIcon, AppShell, Avatar, Box, Center, Container, Divider, Group, Loader, NavLink, Stack, Text, Tooltip,
  UnstyledButton, useComputedColorScheme, useMantineColorScheme,
} from '@mantine/core';
import { useMediaQuery } from '@mantine/hooks';
import { useQueryClient } from '@tanstack/react-query';
import {
  IconBook2, IconChartPie, IconLogout, IconMoon, IconPencilPlus, IconSettings, IconSun, IconTrendingUp,
} from '@tabler/icons-react';

import { api, definirSurNonAuthentifie, toast } from './lib/api';
import { appliquerThemeGraphiques } from './components/Graphique';
import { Logo } from './components/Logo';
import { Protection } from './components/Protection';
import { Connexion } from './pages/Connexion';
import { Saisie } from './pages/Saisie';
import { Dashboard, useNavDashboard } from './pages/dashboard/Dashboard';
import { Bourse, useNavBourse } from './pages/bourse/Bourse';
import { Lectures, useNavLectures } from './pages/lectures/Lectures';
import { Parametres } from './pages/Parametres';

type Onglet = 'saisie' | 'dash' | 'bourse' | 'lectures' | 'params';

const ONGLETS: { id: Onglet; label: string; aide: string; Icone: typeof IconChartPie }[] = [
  { id: 'saisie', label: 'Saisie', aide: 'Dépenses et revenus', Icone: IconPencilPlus },
  { id: 'dash', label: 'Dashboard', aide: 'Analyse du budget', Icone: IconChartPie },
  { id: 'bourse', label: 'Bourse', aide: 'Portefeuille BVC', Icone: IconTrendingUp },
  { id: 'lectures', label: 'Lectures', aide: 'Livres lus', Icone: IconBook2 },
  { id: 'params', label: 'Paramètres', aide: 'Catégories, compte', Icone: IconSettings },
];

export default function App() {
  const [etat, setEtat] = useState<'verification' | 'connecte' | 'deconnecte'>('verification');
  const [utilisateur, setUtilisateur] = useState('');
  const [onglet, setOnglet] = useState<Onglet>('saisie');
  // État de navigation conservé quand on change d'onglet (comme les variables globales de l'ancien app.js)
  const navDash = useNavDashboard();
  const navBourse = useNavBourse();
  const navLectures = useNavLectures();
  const qc = useQueryClient();
  const mobile = useMediaQuery('(max-width: 47.99em)') ?? false;

  const schema = useComputedColorScheme('dark');
  const { setColorScheme } = useMantineColorScheme();
  appliquerThemeGraphiques(schema);
  const basculerTheme = () => setColorScheme(schema === 'light' ? 'dark' : 'light');

  function verifierSession() {
    return api<{ utilisateur: string }>('/api/me').then(r => { setUtilisateur(r.utilisateur); setEtat('connecte'); });
  }

  useEffect(() => {
    // Toute réponse 401 (session expirée) ramène à l'écran de connexion
    definirSurNonAuthentifie(() => {
      qc.clear();
      setEtat('deconnecte');
    });
    verifierSession().catch(() => setEtat('deconnecte'));
  }, [qc]);

  function demarrer() {
    setOnglet('saisie');
    verifierSession().catch(() => setEtat('deconnecte'));
  }

  async function deconnexion() {
    try {
      await api('/api/logout', { method: 'POST' });
    } catch { return; }
    toast('À bientôt 👋');
    qc.clear();
    setEtat('deconnecte');
  }

  if (etat === 'verification') return <Center h="100vh"><Loader color="marque" type="dots" /></Center>;
  if (etat === 'deconnecte') return <Connexion onConnecte={demarrer} />;

  const jour = new Date().toLocaleDateString('fr-FR', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' });
  const BoutonTheme = (
    <Tooltip label={schema === 'light' ? 'Mode nuit' : 'Mode jour'}>
      <ActionIcon variant="default" size="lg" radius="md" aria-label="Mode jour / nuit" onClick={basculerTheme}>
        {schema === 'light' ? <IconMoon size={18} stroke={1.7} /> : <IconSun size={18} stroke={1.7} />}
      </ActionIcon>
    </Tooltip>
  );
  const BoutonDeconnexion = (
    <Tooltip label="Se déconnecter">
      <ActionIcon variant="default" size="lg" radius="md" aria-label="Se déconnecter" onClick={deconnexion}>
        <IconLogout size={18} stroke={1.7} />
      </ActionIcon>
    </Tooltip>
  );

  return (
    <AppShell
      navbar={{ width: 250, breakpoint: 'sm', collapsed: { mobile: true } }}
      header={{ height: 58, collapsed: !mobile }}
      footer={{ height: 64, collapsed: !mobile }}
      padding={{ base: 'sm', sm: 'lg' }}
    >
      {/* ---------- Mobile : en-tête compact ---------- */}
      <AppShell.Header withBorder style={{ backdropFilter: 'blur(12px)', background: 'color-mix(in srgb, var(--mantine-color-body) 82%, transparent)' }}>
        <Group h="100%" px="sm" justify="space-between" wrap="nowrap">
          <Logo taille={30} />
          <Group gap={6} wrap="nowrap">{BoutonTheme}{BoutonDeconnexion}</Group>
        </Group>
      </AppShell.Header>

      {/* ---------- Ordinateur : barre latérale ---------- */}
      <AppShell.Navbar p="md" withBorder style={{ background: 'var(--surface-navbar)' }}>
        <AppShell.Section>
          <Box px={6} pt={4} pb="lg"><Logo /></Box>
        </AppShell.Section>
        <AppShell.Section grow>
          <Text fz={11} fw={700} c="dimmed" tt="uppercase" lts={0.6} px={12} mb={6}>Navigation</Text>
          <Stack gap={4}>
            {ONGLETS.map(({ id, label, aide, Icone }) => (
              <NavLink key={id} className="nav-lien" label={label} description={aide} active={onglet === id}
                       onClick={() => setOnglet(id)} variant="light" color="marque"
                       leftSection={<Icone size={20} stroke={1.7} />} aria-current={onglet === id ? 'page' : undefined} />
            ))}
          </Stack>
        </AppShell.Section>
        <AppShell.Section>
          <Divider mb="md" color="var(--bordure-douce)" />
          <Text fz="xs" c="dimmed" tt="capitalize" px={6} mb="sm">{jour}</Text>
          <Group justify="space-between" wrap="nowrap" px={2}>
            <Group gap={10} wrap="nowrap" style={{ minWidth: 0 }}>
              <Avatar color="marque" radius="xl" size={34}>{utilisateur.slice(0, 2).toUpperCase()}</Avatar>
              <Box style={{ minWidth: 0 }}>
                <Text fz="sm" fw={600} truncate>{utilisateur}</Text>
                <Text fz="xs" c="dimmed">Connecté</Text>
              </Box>
            </Group>
            <Group gap={6} wrap="nowrap">{BoutonTheme}{BoutonDeconnexion}</Group>
          </Group>
        </AppShell.Section>
      </AppShell.Navbar>

      <AppShell.Main>
        <Container size={1180} px={0} pb="md">
          {/* key = onglet : changer d'onglet efface une éventuelle erreur d'affichage */}
          <Protection key={onglet}>
            {onglet === 'saisie' && <Saisie />}
            {onglet === 'dash' && <Dashboard nav={navDash} />}
            {onglet === 'bourse' && <Bourse nav={navBourse} />}
            {onglet === 'lectures' && <Lectures nav={navLectures} />}
            {onglet === 'params' && <Parametres onMdpChange={() => setTimeout(() => { qc.clear(); setEtat('deconnecte'); }, 1200)} />}
          </Protection>
        </Container>
      </AppShell.Main>

      {/* ---------- Mobile : barre d'onglets du bas ---------- */}
      <AppShell.Footer withBorder style={{ background: 'var(--surface-navbar)' }}>
        <Group h="100%" grow gap={4} px="xs">
          {ONGLETS.map(({ id, label, Icone }) => {
            const actif = onglet === id;
            return (
              <UnstyledButton key={id} onClick={() => setOnglet(id)} aria-current={actif ? 'page' : undefined}
                style={{
                  borderRadius: 'var(--mantine-radius-md)', padding: '6px 0', textAlign: 'center',
                  color: actif ? 'var(--c-brand)' : 'var(--mantine-color-dimmed)',
                  transition: 'color .15s',
                }}>
                <Box mx="auto" w={48} py={3} style={{
                  borderRadius: 999, transition: 'background .15s',
                  background: actif ? 'color-mix(in srgb, var(--c-brand) 14%, transparent)' : undefined,
                }}>
                  <Icone size={21} stroke={actif ? 2.1 : 1.6} style={{ display: 'block', margin: '0 auto' }} />
                </Box>
                <Text fz={11} fw={actif ? 700 : 500} mt={2}>{label}</Text>
              </UnstyledButton>
            );
          })}
        </Group>
      </AppShell.Footer>
    </AppShell>
  );
}
