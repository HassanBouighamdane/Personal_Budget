/* Filet de sécurité : une erreur d'affichage inattendue montre un message au lieu d'une page blanche */
import { Component, type ReactNode } from 'react';
import { Button, Card, Stack, Text, Title } from '@mantine/core';

type Props = { children: ReactNode };
type Etat = { erreur: Error | null };

export class Protection extends Component<Props, Etat> {
  state: Etat = { erreur: null };

  static getDerivedStateFromError(erreur: Error): Etat {
    return { erreur };
  }

  componentDidCatch(erreur: Error) {
    console.error(erreur);
  }

  render() {
    if (!this.state.erreur) return this.props.children;
    return (
      <Card maw={520} mx="auto" mt="xl">
        <Stack gap="sm">
          <Title order={3} fz="lg">Oups, cet écran n'a pas pu s'afficher</Title>
          <Text c="dimmed" fz="sm">Tes données ne sont pas touchées. Recharge la page pour réessayer.</Text>
          <Text c="dimmed" fz="xs" ff="monospace">{this.state.erreur.message}</Text>
          <Button onClick={() => window.location.reload()} style={{ alignSelf: 'flex-start' }}>Recharger</Button>
        </Stack>
      </Card>
    );
  }
}
