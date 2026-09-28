/* Champs de formulaire communs */
import { TextInput, type TextInputProps } from '@mantine/core';
import { DatePickerInput } from '@mantine/dates';
import { IconCalendar } from '@tabler/icons-react';

/** Date AAAA-MM-JJ (format attendu par l'API), affichée JJ/MM/AAAA */
export function ChampDate({ label = 'Date', value, onChange }: { label?: string; value: string; onChange: (v: string) => void }) {
  return (
    <DatePickerInput
      label={label}
      value={value}
      onChange={v => v && onChange(v)}
      valueFormat="DD/MM/YYYY"
      leftSection={<IconCalendar size={16} />}
      popoverProps={{ withinPortal: true }}
    />
  );
}

/** Montant saisi en texte : accepte virgule ou point (lu avec lireMontant) */
export function ChampMontant({ onChange, ...props }: Omit<TextInputProps, 'onChange'> & { onChange: (v: string) => void }) {
  return (
    <TextInput
      inputMode="decimal"
      placeholder="0,00"
      rightSection={<span style={{ fontSize: 12, opacity: 0.6 }}>DH</span>}
      onChange={e => onChange(e.currentTarget.value)}
      {...props}
    />
  );
}
