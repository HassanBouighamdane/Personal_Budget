import { useId } from 'react';
import { Group, Text } from '@mantine/core';

/** Symbole de l'application : barres croissantes (budget) + courbe de croissance (épargne).
 *  Même dessin que public/favicon.svg — les deux doivent rester identiques. */
export function SymboleLogo({ taille = 34 }: { taille?: number }) {
  // Identifiant unique du dégradé (plusieurs logos peuvent coexister sur la page) ; les caractères
  // spéciaux de useId() sont retirés pour rester valides dans url(#...)
  const id = 'logo' + useId().replace(/[^a-zA-Z0-9_-]/g, '');
  return (
    <svg width={taille} height={taille} viewBox="0 0 64 64" role="img" aria-label="Mon Budget" style={{ display: 'block', flexShrink: 0 }}>
      <defs>
        <linearGradient id={id} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#818cf8" />
          <stop offset="1" stopColor="#4f46e5" />
        </linearGradient>
      </defs>
      <rect width="64" height="64" rx="15" fill={`url(#${id})`} />
      <rect x="13" y="37" width="9" height="14" rx="3" fill="#ffffff" fillOpacity="0.55" />
      <rect x="27.5" y="29" width="9" height="22" rx="3" fill="#ffffff" fillOpacity="0.78" />
      <rect x="42" y="21" width="9" height="30" rx="3" fill="#ffffff" />
      <path d="M11 30 L24.5 20.5 L33 24 L48.5 11.5" fill="none" stroke="#34d399" strokeWidth="4"
            strokeLinecap="round" strokeLinejoin="round" />
      <circle cx="48.5" cy="11.5" r="3.6" fill="#34d399" stroke="#4f46e5" strokeWidth="1.6" />
    </svg>
  );
}

export function Logo({ taille = 34 }: { taille?: number }) {
  return (
    <Group gap={10} wrap="nowrap">
      <SymboleLogo taille={taille} />
      <Text fw={750} fz={taille > 36 ? 22 : 17} lts={-0.3}>
        Mon <Text span inherit c="var(--c-brand)">Budget</Text>
      </Text>
    </Group>
  );
}
