import {
  Area,
  CartesianGrid,
  ComposedChart,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import type { HistoryRange, PriceChartPoint } from '@mv/types';
import { formatCurrency, formatDate, formatShortDate } from '@mv/utils';
import { describeSeller, isThirdParty } from '../seller';
import styles from './PriceHistoryChart.module.css';

/**
 * Ponto do gráfico com o preço separado por série: `ownPrice` (vendido pela própria loja ou
 * vendedor não identificado) e `thirdPartyPrice` (terceiros). Os preços de terceiros ficam no
 * gráfico para mostrar o mercado, mas numa linha à parte.
 */
interface ChartRow extends PriceChartPoint {
  ownPrice: number | null;
  thirdPartyPrice: number | null;
  /** Ponto da própria loja sem vizinhos da mesma série: precisa de marcador para aparecer. */
  ownIsolated: boolean;
}

function toChartRows(points: PriceChartPoint[]): ChartRow[] {
  const rows = points.map((p) => {
    const thirdParty = isThirdParty(p.sellerType);
    return {
      ...p,
      ownPrice: thirdParty ? null : p.price,
      thirdPartyPrice: thirdParty ? p.price : null,
      ownIsolated: false,
    };
  });
  return rows.map((row, i) => ({
    ...row,
    ownIsolated:
      row.ownPrice != null && rows[i - 1]?.ownPrice == null && rows[i + 1]?.ownPrice == null,
  }));
}

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
  payload?: { payload: ChartRow }[];
}

function ChartTooltip({ active, payload }: TooltipPayload) {
  if (!active || !payload?.length) return null;
  const point = payload[0].payload;
  const seller = point.price != null ? describeSeller(point.sellerType, point.sellerName) : null;
  return (
    <div className={styles.tooltip}>
      <span className={styles.tooltipDate}>{formatDate(point.scrapedAt)}</span>
      <span className={styles.tooltipValue}>
        {point.price != null ? formatCurrency(point.price) : 'Fora de estoque'}
      </span>
      {seller && (
        <span
          className={[
            styles.tooltipSeller,
            isThirdParty(point.sellerType) ? styles.tooltipSellerThirdParty : '',
          ].join(' ')}
        >
          {seller}
        </span>
      )}
    </div>
  );
}

interface PriceHistoryChartProps {
  points: PriceChartPoint[];
  range: HistoryRange;
  onRangeChange: (range: HistoryRange) => void;
  loading?: boolean;
}

interface OwnPriceDotProps {
  cx?: number;
  cy?: number;
  index?: number;
  payload?: ChartRow;
}

export function PriceHistoryChart({ points, range, onRangeChange, loading }: PriceHistoryChartProps) {
  const hasData = points.length > 0;
  const rows = toChartRows(points);
  const hasThirdParty = rows.some((row) => row.thirdPartyPrice != null);

  // Menor preço marcado com a mesma regra das estatísticas: só a própria loja, a não ser que
  // o período só tenha preços de terceiros.
  const ownPrices = rows.map((r) => r.ownPrice).filter((price): price is number => price != null);
  const thirdPartyPrices = rows
    .map((r) => r.thirdPartyPrice)
    .filter((price): price is number => price != null);
  const lowestCandidates = ownPrices.length > 0 ? ownPrices : thirdPartyPrices;
  const lowestPrice = lowestCandidates.length > 0 ? Math.min(...lowestCandidates) : null;
  const lowestIsThirdParty = ownPrices.length === 0;

  const renderOwnDot = ({ cx, cy, index, payload }: OwnPriceDotProps) => {
    const isLowest = !lowestIsThirdParty && lowestPrice != null && payload?.ownPrice === lowestPrice;
    const visible = isLowest || !!payload?.ownIsolated;
    return (
      <circle
        key={`price-dot-${index}`}
        cx={cx}
        cy={cy}
        r={isLowest ? 4 : visible ? 3 : 0}
        fill={isLowest ? 'var(--color-accent)' : 'var(--color-primary-soft)'}
        stroke="var(--color-surface-2)"
        strokeWidth={visible ? 2 : 0}
      />
    );
  };

  const renderThirdPartyDot = ({ cx, cy, index, payload }: OwnPriceDotProps) => {
    if (payload?.thirdPartyPrice == null) return <g key={`third-party-dot-${index}`} />;
    const isLowest = lowestIsThirdParty && payload.thirdPartyPrice === lowestPrice;
    return (
      <circle
        key={`third-party-dot-${index}`}
        cx={cx}
        cy={cy}
        r={isLowest ? 4 : 3}
        fill={isLowest ? 'var(--color-accent)' : 'var(--color-warning)'}
        stroke="var(--color-surface-2)"
        strokeWidth={2}
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
            <ComposedChart data={rows} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
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
                dataKey="ownPrice"
                name="Amazon"
                stroke="var(--color-primary-soft)"
                strokeWidth={2}
                fill="var(--color-primary-soft)"
                fillOpacity={0.1}
                connectNulls={false}
                dot={renderOwnDot}
                activeDot={{ r: 5, fill: 'var(--color-primary-soft)', stroke: 'var(--color-surface-2)', strokeWidth: 2 }}
                isAnimationActive={false}
              />
              {hasThirdParty && (
                <Line
                  type="monotone"
                  dataKey="thirdPartyPrice"
                  name="Terceiros"
                  stroke="var(--color-warning)"
                  strokeWidth={2}
                  strokeDasharray="5 4"
                  connectNulls={false}
                  dot={renderThirdPartyDot}
                  activeDot={{ r: 5, fill: 'var(--color-warning)', stroke: 'var(--color-surface-2)', strokeWidth: 2 }}
                  isAnimationActive={false}
                />
              )}
            </ComposedChart>
          </ResponsiveContainer>
        </div>
      )}

      {!loading && hasThirdParty && (
        <div className={styles.legend}>
          <span className={styles.legendItem}>
            <span className={styles.legendOwn} />
            Amazon
          </span>
          <span className={styles.legendItem}>
            <span className={styles.legendThirdParty} />
            Terceiros (Amazon esgotada ou outro vendedor)
          </span>
        </div>
      )}
    </div>
  );
}
