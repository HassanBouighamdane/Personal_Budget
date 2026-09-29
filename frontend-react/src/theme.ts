/* Thème Mantine « indigo & ardoise » : indigo (marque) · rose (dépenses) · bleu (revenus) · émeraude (épargne). */
import { createTheme, type MantineColorsTuple } from '@mantine/core';

// Couleur de marque : indigo (boutons, navigation, logo)
const marque: MantineColorsTuple = ['#eef2ff', '#e0e7ff', '#c7d2fe', '#a5b4fc', '#818cf8', '#6f73f4', '#6366f1', '#4f46e5', '#4338ca', '#3730a3'];
// Couleurs métier : dépenses, revenus, épargne, négatif, avertissement
const rose: MantineColorsTuple = ['#fff1f2', '#ffe4e6', '#fecdd3', '#fda4af', '#fb7185', '#f75672', '#f43f5e', '#e11d48', '#be123c', '#9f1239'];
const bleu: MantineColorsTuple = ['#eff6ff', '#dbeafe', '#bfdbfe', '#93c5fd', '#60a5fa', '#4b8ff8', '#3b82f6', '#2563eb', '#1d4ed8', '#1e40af'];
const emeraude: MantineColorsTuple = ['#ecfdf5', '#d1fae5', '#a7f3d0', '#6ee7b7', '#34d399', '#1fc88e', '#10b981', '#059669', '#047857', '#065f46'];
const rouge: MantineColorsTuple = ['#fef2f2', '#fee2e2', '#fecaca', '#fca5a5', '#f87171', '#f35656', '#ef4444', '#dc2626', '#b91c1c', '#991b1b'];
const ambre: MantineColorsTuple = ['#fffbeb', '#fef3c7', '#fde68a', '#fcd34d', '#fbbf24', '#f8ad15', '#f59e0b', '#d97706', '#b45309', '#92400e'];
// Échelle ardoise (sombre) : [0] texte, [2] texte atténué, [4] bordures, [6] cartes, [7] fond de page
const ardoise: MantineColorsTuple = ['#e6e8ec', '#c4c8d0', '#9aa1ad', '#6b7280', '#2a2e37', '#21252d', '#171a21', '#0f1115', '#0b0d10', '#07080a'];

export const theme = createTheme({
  primaryColor: 'marque',
  primaryShade: { light: 6, dark: 6 },
  colors: { marque, rose, bleu, emeraude, rouge, ambre, dark: ardoise },
  fontFamily: "'Inter', 'Segoe UI', system-ui, sans-serif",
  fontFamilyMonospace: "'Space Grotesk', monospace",
  headings: {
    fontFamily: "'Inter', 'Segoe UI', sans-serif",
    fontWeight: '700',
    sizes: { h1: { fontSize: '1.625rem', lineHeight: '1.25' }, h2: { fontSize: '1.25rem' }, h3: { fontSize: '1.05rem' }, h4: { fontSize: '0.95rem' } },
  },
  defaultRadius: 'md',
  cursorType: 'pointer',
  components: {
    Card: { defaultProps: { withBorder: true, radius: 'lg', padding: 'lg' } },
    Button: { defaultProps: { radius: 'md' }, styles: { root: { fontWeight: 600 } } },
    TextInput: { defaultProps: { radius: 'md' } },
    NumberInput: { defaultProps: { radius: 'md' } },
    Select: { defaultProps: { radius: 'md' } },
    Autocomplete: { defaultProps: { radius: 'md' } },
    PasswordInput: { defaultProps: { radius: 'md' } },
    DatePickerInput: { defaultProps: { radius: 'md' } },
    InputWrapper: { styles: { label: { fontSize: 13, fontWeight: 600, marginBottom: 6 } } },
    SegmentedControl: { defaultProps: { radius: 'md' } },
    Notification: { defaultProps: { radius: 'md', withBorder: true } },
    Modal: { defaultProps: { radius: 'lg', overlayProps: { backgroundOpacity: 0.55, blur: 3 } } },
    Tooltip: { defaultProps: { withArrow: true, openDelay: 250 } },
    Table: {
      styles: {
        th: {
          fontSize: 11, fontWeight: 600, textTransform: 'uppercase', letterSpacing: 0.4,
          color: 'var(--mantine-color-dimmed)', whiteSpace: 'nowrap',
        },
      },
    },
  },
});
