/* Thème Mantine : nuit d'encre · safran (dépenses) · menthe (épargne) · océan (revenus). */
import { createTheme, type MantineColorsTuple } from '@mantine/core';

const safran: MantineColorsTuple = ['#fff0e8', '#ffdfd1', '#fbbda2', '#f8996f', '#f57b45', '#f2682b', '#eb6834', '#c44613', '#a83b0f', '#8c300b'];
const menthe: MantineColorsTuple = ['#e3fbf2', '#d0f4e6', '#a3e8cc', '#72dbb0', '#4ad099', '#31c98a', '#0f9e6e', '#0b8a5f', '#067a53', '#006a46'];
const ocean: MantineColorsTuple = ['#e2f7ff', '#cdeafb', '#9fd3f3', '#6dbbeb', '#44a7e5', '#2a9ae1', '#0e8bbd', '#0a7aa8', '#006c96', '#005d84'];
const rouge: MantineColorsTuple = ['#ffeaec', '#fdd4d6', '#f4a7ab', '#ec777e', '#e64f58', '#e2363f', '#d64550', '#c3303a', '#ae2732', '#991b28'];
const violet: MantineColorsTuple = ['#f0edff', '#dcd7fb', '#b6acf3', '#8d7eeb', '#6b58e5', '#5640e1', '#4a3aa7', '#3f2ec8', '#3628b3', '#2b209e'];
// Échelle sombre : [0] texte, [2] texte atténué, [4] bordures, [6] cartes, [7] fond de page
const nuit: MantineColorsTuple = ['#e8edf7', '#c3cadb', '#8d98b4', '#5d6a8a', '#232d47', '#1a2338', '#121a2d', '#0b1120', '#080d19', '#050912'];

export const theme = createTheme({
  primaryColor: 'safran',
  primaryShade: { light: 6, dark: 6 },
  colors: { safran, menthe, ocean, rouge, violet, dark: nuit },
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
