import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import type { HistoryRange, PriceChartPoint } from '@mv/types';
import { formatCurrency, formatDate, formatShortDate } from '@mv/utils';
import styles from './PriceHistoryChart.module.css';

const RANGE_OPTIONS: { value: HistoryRange; label: string }[] = [
  { value: '7d', label: '7 dias' },
  { value: '30d', label: '30 dias' },
  { value: '90d', label: '90 dias' },
  { value: 'all', label: 'Tudo' },
];

const AXIS_PRICE_FORMATTER = new Intl.NumberFormat('pt-BR', {
  style: 'currency',
  currency: 'BRL',
  maximumFractionDigits: 0,
});

interface TooltipPayload {
  active?: boolean;
  payload?: { payload: PriceChartPoint }[];
}

function ChartTooltip({ active, payload }: TooltipPayload) {
  if (!active || !payload?.length) return null;
  const point = payload[0].payload;
  return (
    <div className={styles.tooltip}>
      <span className={styles.tooltipDate}>{formatDate(point.scrapedAt)}</span>
      <span className={styles.tooltipValue}>
        {point.price != null ? formatCurrency(point.price) : 'Fora de estoque'}
      </span>
    </div>
  );
}

interface PriceHistoryChartProps {
  points: PriceChartPoint[];
  range: HistoryRange;
  onRangeChange: (range: HistoryRange) => void;
  loading?: boolean;
}

interface LowestPriceDotProps {
  cx?: number;
  cy?: number;
  index?: number;
  payload?: PriceChartPoint;
}

export function PriceHistoryChart({ points, range, onRangeChange, loading }: PriceHistoryChartProps) {
  const hasData = points.length > 0;

  const definedPrices = points
    .map((p) => p.price)
    .filter((price): price is number => price != null);
  const lowestPrice = definedPrices.length > 0 ? Math.min(...definedPrices) : null;

  const renderDot = ({ cx, cy, index, payload }: LowestPriceDotProps) => {
    const isLowest = lowestPrice != null && payload?.price === lowestPrice;
    return (
      <circle
        key={`price-dot-${index}`}
        cx={cx}
        cy={cy}
        r={isLowest ? 4 : 0}
        fill="var(--color-accent)"
        stroke="var(--color-surface-2)"
        strokeWidth={isLowest ? 2 : 0}
      />
    );
  };

  return (
    <div className={styles.wrapper}>
      <div className={styles.rangeRow}>
        {RANGE_OPTIONS.map((opt) => (
          <button
            key={opt.value}
            type="button"
            className={[styles.rangeBtn, range === opt.value ? styles.rangeBtnActive : ''].join(' ')}
            onClick={() => onRangeChange(opt.value)}
          >
            {opt.label}
          </button>
        ))}
      </div>

      {loading ? (
        <p className={styles.loading}>Carregando gráfico...</p>
      ) : !hasData ? (
        <p className={styles.empty}>Sem dados suficientes para o período selecionado.</p>
      ) : (
        <div className={styles.chartBox}>
          <ResponsiveContainer width="100%" height={220}>
            <AreaChart data={points} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
              <CartesianGrid vertical={false} stroke="var(--color-border)" strokeDasharray="4 4" />
              <XAxis
                dataKey="scrapedAt"
                tickFormatter={formatShortDate}
                stroke="var(--color-text-faint)"
                fontSize={11}
                tickLine={false}
                axisLine={false}
                minTickGap={24}
              />
              <YAxis
                dataKey="price"
                stroke="var(--color-text-faint)"
                fontSize={11}
                tickLine={false}
                axisLine={false}
                width={68}
                tickFormatter={(v: number) => AXIS_PRICE_FORMATTER.format(v)}
                domain={['auto', 'auto']}
              />
              <Tooltip
                content={<ChartTooltip />}
                cursor={{ stroke: 'var(--color-text-muted)', strokeWidth: 1 }}
              />
              <Area
                type="monotone"
                dataKey="price"
                stroke="var(--color-primary-soft)"
                strokeWidth={2}
                fill="var(--color-primary-soft)"
                fillOpacity={0.1}
                connectNulls={false}
                dot={renderDot}
                activeDot={{ r: 5, fill: 'var(--color-primary-soft)', stroke: 'var(--color-surface-2)', strokeWidth: 2 }}
                isAnimationActive={false}
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
}
