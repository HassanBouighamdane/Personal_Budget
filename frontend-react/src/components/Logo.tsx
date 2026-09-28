import { Group, Text, ThemeIcon } from '@mantine/core';
import { IconWallet } from '@tabler/icons-react';

export function Logo({ taille = 34 }: { taille?: number }) {
  return (
    <Group gap={10} wrap="nowrap">
      <ThemeIcon size={taille} radius="md" variant="gradient" gradient={{ from: 'safran.5', to: 'safran.8', deg: 135 }}>
        <IconWallet size={Math.round(taille * 0.56)} stroke={1.9} />
      </ThemeIcon>
      <Text fw={750} fz={taille > 36 ? 22 : 17} lts={-0.3}>
        Mon <Text span inherit c="var(--c-dep)">Budget</Text>
      </Text>
    </Group>
  );
}
