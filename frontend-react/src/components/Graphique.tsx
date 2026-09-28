/* Graphiques Chart.js (même bibliothèque que l'ancien frontend), via react-chartjs-2 :
 * les données sont mises à jour sur place au lieu de détruire/recréer le graphique. */
import 'chart.js/auto';
import { Chart as ChartJS, type ChartData, type ChartOptions, type ChartType } from 'chart.js';
import { Chart } from 'react-chartjs-2';
import { useComputedColorScheme } from '@mantine/core';
import { useMediaQuery } from '@mantine/hooks';
import { fmt, nombreFr } from '../lib/format';

const COULEURS = {
  light: { texte: '#64708c', grille: 'rgba(27,36,55,.07)', infobulle: '#1b2437' },
  dark: { texte: '#8d98b4', grille: 'rgba(141,152,180,.12)', infobulle: '#1f2942' },
};

/** À appeler au rendu de la racine : les graphiques lisent ces valeurs par défaut à leur création */
export function appliquerThemeGraphiques(schema: 'light' | 'dark') {
  const c = COULEURS[schema];
  ChartJS.defaults.color = c.texte;
  ChartJS.defaults.borderColor = c.grille;
  ChartJS.defaults.font.family = "'Inter', 'Segoe UI', system-ui, sans-serif";
  ChartJS.defaults.font.size = 11.5;
  const tip = ChartJS.defaults.plugins.tooltip;
  tip.backgroundColor = c.infobulle;
  tip.titleColor = '#e8edf7';
  tip.bodyColor = '#c3cadb';
  tip.padding = 10;
  tip.cornerRadius = 8;
  tip.boxPadding = 4;
  tip.usePointStyle = true;
  const leg = ChartJS.defaults.plugins.legend.labels;
  leg.usePointStyle = true;
  leg.pointStyle = 'circle';
  leg.boxWidth = 8;
  leg.boxHeight = 8;
  leg.padding = 14;
}

type Props = {
  type: ChartType;
  data: ChartData;
  options?: ChartOptions;
  hauteur?: number;
};

export function Graphique({ type, data, options, hauteur = 260 }: Props) {
  const schema = useComputedColorScheme('dark');
  return (
    <div style={{ position: 'relative', height: hauteur }}>
      {/* key = schéma : le graphique est recréé au changement de thème pour reprendre les couleurs */}
      <Chart key={schema} type={type} data={data}
             options={{ responsive: true, maintainAspectRatio: false, ...options } as ChartOptions} />
    </div>
  );
}

/* ---------- Options communes ---------- */
const axeMontants = { border: { display: false }, ticks: { callback: (v: string | number) => nombreFr(v), maxTicksLimit: 6 } };
const axeLibelles = { border: { display: false }, grid: { display: false } };
const survol = { interaction: { mode: 'index' as const, intersect: false } };

export const optionsSeries = (horizontal = false): ChartOptions => horizontal
  ? { indexAxis: 'y', plugins: { legend: { display: false } }, scales: { x: axeMontants, y: axeLibelles } }
  : { ...survol, plugins: { legend: { position: 'top', align: 'end' } }, scales: { y: axeMontants, x: axeLibelles } };

// Légende + infobulle avec le pourcentage de chaque part, en plus de la valeur.
function optionsDonut(texte: string, etroit: boolean): ChartOptions<'doughnut'> {
  const pct = (valeur: number, data: number[]) => {
    const total = data.reduce((a, b) => a + b, 0);
    return total ? (valeur / total * 100).toFixed(1) : '0.0';
  };
  return {
    cutout: '68%',
    plugins: {
      legend: {
        // Écran étroit : légende sous le graphique pour lui laisser toute la largeur
        position: etroit ? 'bottom' : 'right',
        labels: {
          // generateLabels personnalisé : n'hérite pas de Chart.defaults.color, couleur fixée explicitement
          color: texte, boxWidth: 8, boxHeight: 8, usePointStyle: true, pointStyle: 'circle', padding: 12, font: { size: 12 },
          generateLabels: chart => {
            const ds = chart.data.datasets[0];
            const data = ds.data as number[];
            const bg = ds.backgroundColor as string[];
            return (chart.data.labels as string[]).map((label, i) => ({
              text: `${label} — ${pct(data[i], data)} %`,
              fillStyle: bg[i], strokeStyle: bg[i], fontColor: texte, index: i, pointStyle: 'circle' as const,
            }));
          },
        },
      },
      tooltip: {
        callbacks: { label: ctx => `${ctx.label} : ${fmt(ctx.parsed)} (${pct(ctx.parsed, ctx.dataset.data as number[])} %)` },
      },
    },
  };
}

/** Donut de répartition (catégories, titres, secteurs) */
export function Donut({ labels, valeurs, couleurs }: { labels: string[]; valeurs: number[]; couleurs: string[] }) {
  const schema = useComputedColorScheme('dark');
  const etroit = useMediaQuery('(max-width: 600px)') ?? false;
  return (
    <Graphique
      type="doughnut"
      hauteur={etroit ? 300 : 260}
      data={{ labels, datasets: [{ data: valeurs, backgroundColor: couleurs, borderWidth: 0, hoverOffset: 6, spacing: 2, borderRadius: 4 }] }}
      options={optionsDonut(COULEURS[schema].texte, etroit) as ChartOptions}
    />
  );
}
