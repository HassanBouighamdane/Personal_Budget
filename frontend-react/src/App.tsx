import { useEffect, useState } from 'react';
import {
  ActionIcon, AppShell, Center, Container, Group, Loader, Text, Title, Tooltip, UnstyledButton,
  useComputedColorScheme, useMantineColorScheme,
} from '@mantine/core';
import { useQueryClient } from '@tanstack/react-query';
import { IconChartPie, IconMoon, IconPencilPlus, IconPower, IconSettings, IconSun, IconTrendingUp } from '@tabler/icons-react';

import { api, definirSurNonAuthentifie, toast } from './lib/api';
import { appliquerThemeGraphiques } from './components/Graphique';
import { Protection } from './components/Protection';
import { Connexion } from './pages/Connexion';
import { Saisie } from './pages/Saisie';
import { Dashboard, useNavDashboard } from './pages/dashboard/Dashboard';
import { Bourse, useNavBourse } from './pages/bourse/Bourse';
import { Parametres } from './pages/Parametres';

type Onglet = 'saisie' | 'dash' | 'bourse' | 'params';

const ONGLETS: { id: Onglet; label: string; Icone: typeof IconChartPie }[] = [
  { id: 'saisie', label: 'Saisie', Icone: IconPencilPlus },
  { id: 'dash', label: 'Dashboard', Icone: IconChartPie },
  { id: 'bourse', label: 'Bourse', Icone: IconTrendingUp },
  { id: 'params', label: 'Paramètres', Icone: IconSettings },
];

export default function App() {
  const [etat, setEtat] = useState<'verification' | 'connecte' | 'deconnecte'>('verification');
  const [onglet, setOnglet] = useState<Onglet>('saisie');
  // État de navigation conservé quand on change d'onglet (comme les variables globales de l'ancien app.js)
  const navDash = useNavDashboard();
  const navBourse = useNavBourse();
  const qc = useQueryClient();

  const schema = useComputedColorScheme('dark');
  const { setColorScheme } = useMantineColorScheme();
  appliquerThemeGraphiques(schema);

  useEffect(() => {
    // Toute réponse 401 (session expirée) ramène à l'écran de connexion
    definirSurNonAuthentifie(() => {
      qc.clear();
      setEtat('deconnecte');
    });
    api('/api/me').then(() => setEtat('connecte'), () => setEtat('deconnecte'));
  }, [qc]);

  function demarrer() {
    setOnglet('saisie');
    setEtat('connecte');
  }

  async function deconnexion() {
    try {
      await api('/api/logout', { method: 'POST' });
    } catch { return; }
    toast('À bientôt 👋');
    qc.clear();
    setEtat('deconnecte');
  }

  if (etat === 'verification') return <Center h="100vh"><Loader color="safran" /></Center>;
  if (etat === 'deconnecte') return <Connexion onConnecte={demarrer} />;

  const jour = new Date().toLocaleDateString('fr-FR', { weekday: 'long', day: 'numeric', month: 'long' });

  return (
    <AppShell header={{ height: 60 }} footer={{ height: 64 }} padding="md">
      <AppShell.Header withBorder style={{ backdropFilter: 'blur(10px)', background: 'color-mix(in srgb, var(--mantine-color-body) 80%, transparent)' }}>
        <Container size="lg" h="100%">
          <Group h="100%" justify="space-between" wrap="nowrap">
            <Title order={1} fz={{ base: 20, sm: 24 }}>💰 Mon <Text span inherit c="var(--c-dep)">Budget</Text></Title>
            <Group gap="xs" wrap="nowrap">
              <Text c="dimmed" fz="sm" tt="capitalize" visibleFrom="xs">{jour}</Text>
              <Tooltip label="Mode jour / nuit" withArrow>
                <ActionIcon variant="default" size="lg" radius="md" aria-label="Mode jour / nuit"
                            onClick={() => setColorScheme(schema === 'light' ? 'dark' : 'light')}>
                  {schema === 'light' ? <IconMoon size={18} /> : <IconSun size={18} />}
                </ActionIcon>
              </Tooltip>
              <Tooltip label="Se déconnecter" withArrow>
                <ActionIcon variant="default" size="lg" radius="md" aria-label="Se déconnecter" onClick={deconnexion}>
                  <IconPower size={18} />
                </ActionIcon>
              </Tooltip>
            </Group>
          </Group>
        </Container>
      </AppShell.Header>

      <AppShell.Main>
        <Container size="lg" px={0} pb="md">
          {/* key = onglet : changer d'onglet efface une éventuelle erreur d'affichage */}
          <Protection key={onglet}>
            {onglet === 'saisie' && <Saisie />}
            {onglet === 'dash' && <Dashboard nav={navDash} />}
            {onglet === 'bourse' && <Bourse nav={navBourse} />}
            {onglet === 'params' && <Parametres onMdpChange={() => setTimeout(() => { qc.clear(); setEtat('deconnecte'); }, 1200)} />}
          </Protection>
        </Container>
      </AppShell.Main>

      <AppShell.Footer withBorder>
        <Container size="sm" h="100%" px="xs">
          <Group h="100%" grow gap={4}>
            {ONGLETS.map(({ id, label, Icone }) => {
              const actif = onglet === id;
              return (
                <UnstyledButton key={id} onClick={() => setOnglet(id)} aria-current={actif ? 'page' : undefined}
                  style={{
                    borderRadius: 'var(--mantine-radius-md)', padding: '6px 0', textAlign: 'center',
                    color: actif ? 'var(--c-dep)' : 'var(--mantine-color-dimmed)',
                    background: actif ? 'color-mix(in srgb, var(--c-dep) 12%, transparent)' : undefined,
                    transition: 'background .15s, color .15s',
                  }}>
                  <Icone size={22} stroke={actif ? 2.2 : 1.6} style={{ display: 'block', margin: '0 auto' }} />
                  <Text fz={11} fw={actif ? 700 : 500} mt={2}>{label}</Text>
                </UnstyledButton>
              );
            })}
          </Group>
        </Container>
      </AppShell.Footer>
    </AppShell>
  );
}
