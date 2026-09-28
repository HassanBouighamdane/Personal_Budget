import { useState, type FormEvent } from 'react';
import { Box, Button, Card, Center, Group, PasswordInput, Stack, Text, TextInput, ThemeIcon, Title } from '@mantine/core';
import { IconChartPie, IconLock, IconShieldCheck, IconTrendingUp, IconUser } from '@tabler/icons-react';
import { api, toast } from '../lib/api';
import { Logo } from '../components/Logo';

const ATOUTS = [
  { Icone: IconChartPie, texte: 'Budget, épargne et tableaux de bord' },
  { Icone: IconTrendingUp, texte: 'Portefeuille Bourse de Casablanca' },
  { Icone: IconShieldCheck, texte: 'Données privées, session sécurisée' },
];

export function Connexion({ onConnecte }: { onConnecte: () => void }) {
  const [utilisateur, setUtilisateur] = useState('');
  const [motDePasse, setMotDePasse] = useState('');
  const [envoi, setEnvoi] = useState(false);

  async function connexion(e: FormEvent) {
    e.preventDefault();
    const nom = utilisateur.trim();
    if (!nom || !motDePasse) return toast('Utilisateur et mot de passe requis', false);
    setEnvoi(true);
    try {
      // sessionRequise: false — un 401 ici veut dire « identifiants incorrects » : on affiche le message
      await api('/api/login', { method: 'POST', body: { utilisateur: nom, mot_de_passe: motDePasse }, sessionRequise: false });
    } catch {
      setEnvoi(false);
      return;   // le message d'erreur est déjà affiché
    }
    setMotDePasse('');
    onConnecte();
  }

  return (
    <Center mih="100vh" p="md">
      <Stack w="100%" maw={400} gap="lg">
        <Center><Logo taille={42} /></Center>
        <Card padding="xl" radius="xl" shadow="xl">
          <form onSubmit={connexion}>
            <Stack gap="md">
              <Box>
                <Title order={2} fz={20}>Connexion</Title>
                <Text c="dimmed" fz="sm" mt={4}>Connecte-toi pour accéder à ton budget</Text>
              </Box>
              <TextInput label="Utilisateur" autoComplete="username" autoFocus size="md"
                         leftSection={<IconUser size={17} stroke={1.7} />}
                         value={utilisateur} onChange={e => setUtilisateur(e.currentTarget.value)} />
              <PasswordInput label="Mot de passe" autoComplete="current-password" size="md"
                             leftSection={<IconLock size={17} stroke={1.7} />}
                             value={motDePasse} onChange={e => setMotDePasse(e.currentTarget.value)} />
              <Button type="submit" mt={4} fullWidth size="md" loading={envoi}>Se connecter</Button>
            </Stack>
          </form>
        </Card>
        <Stack gap={8} px="xs">
          {ATOUTS.map(({ Icone, texte }) => (
            <Group key={texte} gap="sm" wrap="nowrap">
              <ThemeIcon variant="light" color="gray" size={26} radius="md"><Icone size={15} stroke={1.8} /></ThemeIcon>
              <Text fz="sm" c="dimmed">{texte}</Text>
            </Group>
          ))}
        </Stack>
      </Stack>
    </Center>
  );
}
