import { useTranslation } from 'react-i18next';
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
  type TooltipContentProps,
} from 'recharts';

import { formatMoney } from '../../lib/money';
import { useReducedMotion } from '../../lib/motion';

function DayTooltip({ active, payload, label }: TooltipContentProps) {
  const { i18n } = useTranslation();
  const amount = payload[0]?.value;
  if (!active || amount === undefined) return null;
  return (
    <div className="rounded-lg border border-line bg-canvas px-3 py-2 text-sm shadow-[var(--shadow-float)]">
      <p className="text-muted">{label}</p>
      <p className="font-medium tabular-nums">
        {formatMoney(String(amount), i18n.resolvedLanguage)}
      </p>
    </div>
  );
}

// Loaded on its own, so the chart library is only fetched by people who see a chart.
export default function SalesChart({ days }: { days: { date: string; amount: string }[] }) {
  const { i18n } = useTranslation();
  const reduced = useReducedMotion();
  const data = days.map((day) => ({ ...day, amount: Number(day.amount) }));
  const compact = new Intl.NumberFormat(i18n.resolvedLanguage, { notation: 'compact' });
  const rtl = i18n.dir() === 'rtl';
  return (
    <div className="h-64" dir="ltr">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
          <CartesianGrid vertical={false} stroke="var(--color-line)" />
          <XAxis
            dataKey="date"
            reversed={rtl}
            tickFormatter={(value: string) => value.slice(8)}
            interval={4}
            tickLine={false}
            axisLine={{ stroke: 'var(--color-line-strong)' }}
            tick={{ fill: 'var(--color-muted)', fontSize: 12 }}
          />
          <YAxis
            orientation={rtl ? 'right' : 'left'}
            width={48}
            tickFormatter={(value: number) => compact.format(value)}
            tickLine={false}
            axisLine={false}
            tick={{ fill: 'var(--color-muted)', fontSize: 12 }}
          />
          <Tooltip content={DayTooltip} cursor={{ fill: 'var(--color-raised)' }} />
          <Bar
            dataKey="amount"
            fill="var(--color-azure)"
            maxBarSize={24}
            radius={[4, 4, 0, 0]}
            isAnimationActive={!reduced}
          />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
