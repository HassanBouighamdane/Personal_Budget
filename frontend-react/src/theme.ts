/* Thème Mantine calqué sur les jetons de l'ancien style.css :
 * nuit d'encre · safran (dépenses) · menthe (épargne) · océan (revenus). */
import { createTheme, type MantineColorsTuple } from '@mantine/core';

const safran: MantineColorsTuple = ['#fff0e8', '#ffdfd1', '#fbbda2', '#f8996f', '#f57b45', '#f2682b', '#eb6834', '#c44613', '#a83b0f', '#8c300b'];
const menthe: MantineColorsTuple = ['#e3fbf2', '#d0f4e6', '#a3e8cc', '#72dbb0', '#4ad099', '#31c98a', '#0f9e6e', '#0b8a5f', '#067a53', '#006a46'];
const ocean: MantineColorsTuple = ['#e2f7ff', '#cdeafb', '#9fd3f3', '#6dbbeb', '#44a7e5', '#2a9ae1', '#0e8bbd', '#0a7aa8', '#006c96', '#005d84'];
const rouge: MantineColorsTuple = ['#ffeaec', '#fdd4d6', '#f4a7ab', '#ec777e', '#e64f58', '#e2363f', '#d64550', '#c3303a', '#ae2732', '#991b28'];
// Échelle sombre : [0] texte, [2] texte atténué, [4] bordures, [6] cartes, [7] fond de page
const nuit: MantineColorsTuple = ['#e8edf7', '#c3cadb', '#8d98b4', '#5d6a8a', '#263250', '#1d2740', '#141c30', '#0b1120', '#080d19', '#050912'];

export const theme = createTheme({
  primaryColor: 'safran',
  primaryShade: { light: 6, dark: 6 },
  colors: { safran, menthe, ocean, rouge, dark: nuit },
  fontFamily: "'Inter', 'Segoe UI', system-ui, sans-serif",
  fontFamilyMonospace: "'Space Grotesk', monospace",
  headings: { fontFamily: "'Space Grotesk', 'Inter', sans-serif", fontWeight: '700' },
  defaultRadius: 'md',
  cursorType: 'pointer',
  components: {
    Card: { defaultProps: { withBorder: true, radius: 'lg', padding: 'lg', shadow: 'sm' } },
    Button: { defaultProps: { radius: 'md' } },
    Notification: { defaultProps: { radius: 'md', withBorder: true } },
  },
});
