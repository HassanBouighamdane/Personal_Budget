import { useState, type FormEvent } from 'react';
import { Button, Card, Center, PasswordInput, Stack, Text, TextInput, Title } from '@mantine/core';
import { api, toast } from '../lib/api';

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
      <Card w="100%" maw={380} padding="xl" shadow="md">
        <form onSubmit={connexion}>
          <Stack gap="sm">
            <Title order={1} ta="center" fz={28}>💰 Mon <Text span inherit c="var(--c-dep)">Budget</Text></Title>
            <Text c="dimmed" ta="center" fz="sm" mb="xs">Connecte-toi pour accéder à ton budget</Text>
            <TextInput label="Utilisateur" autoComplete="username" data-autofocus autoFocus
                       value={utilisateur} onChange={e => setUtilisateur(e.currentTarget.value)} />
            <PasswordInput label="Mot de passe" autoComplete="current-password"
                           value={motDePasse} onChange={e => setMotDePasse(e.currentTarget.value)} />
            <Button type="submit" mt="sm" fullWidth loading={envoi}>Se connecter</Button>
          </Stack>
        </form>
      </Card>
    </Center>
  );
}
