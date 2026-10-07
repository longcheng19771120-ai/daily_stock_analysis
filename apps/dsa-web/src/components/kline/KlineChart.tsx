import type React from 'react';
import { useEffect, useMemo, useRef, useState } from 'react';
import {
  CandlestickSeries,
  ColorType,
  CrosshairMode,
  HistogramSeries,
  LineSeries,
  createChart,
  createSeriesMarkers,
  type IChartApi,
  type MouseEventParams,
} from 'lightweight-charts';
import { useTheme } from 'next-themes';
import type { StockKline } from '../../api/kline';
import { toBuyMarkers, toChartTime, toPolyline } from './klineChartUtils';
import { PivotBoxesPrimitive } from './pivotBoxesPrimitive';
import { useUiLanguage } from '../../contexts/UiLanguageContext';

// A 股习惯：红涨绿跌
const UP_COLOR = '#ef4444';
const DOWN_COLOR = '#22c55e';
const MA_COLORS = ['#f59e0b', '#3b82f6', '#a855f7', '#14b8a6'];
const BI_COLOR = '#0ea5e9';
const SEGMENT_COLOR = '#f97316';
const PIVOT_STYLE = { fill: 'rgba(234,179,8,0.14)', border: 'rgba(234,179,8,0.85)' };
const MACD_DIF_COLOR = '#f59e0b';
const MACD_DEA_COLOR = '#3b82f6';
const MACD_PANE_HEIGHT = 130;
const BUY_COLORS = { buy1: '#dc2626', buy2: '#db2777', buy3: '#9333ea' } as const;
const DEFAULT_VISIBLE_BARS = 180;

export type KlineOverlayOptions = {
  showMa: boolean;
  showBi: boolean;
  showSegments: boolean;
  showPivots: boolean;
  showBuyPoints: boolean;
  showMacd: boolean;
};

type KlineChartProps = {
  data: StockKline;
  overlays: KlineOverlayOptions;
  className?: string;
};

type LegendState = {
  time: string;
  open: number;
  high: number;
  low: number;
  close: number;
  changePct: number | null;
  volume: number | null;
  ma: Array<{ key: string; value: number | null; color: string }>;
  macd: { dif: number; dea: number; hist: number } | null;
};

function formatVolume(value: number | null): string {
  if (value === null || value === undefined) return '-';
  return new Intl.NumberFormat('zh-CN', { notation: 'compact', maximumFractionDigits: 2 }).format(value);
}

export const KlineChart: React.FC<KlineChartProps> = ({ data, overlays, className }) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const { resolvedTheme } = useTheme();
  const { t } = useUiLanguage();
  const isDark = resolvedTheme === 'dark';
  const [hoverIndex, setHoverIndex] = useState<number | null>(null);

  const times = useMemo(() => data.bars.map((bar) => toChartTime(bar.time)), [data.bars]);
  const maEntries = useMemo(
    () => Object.entries(data.movingAverages ?? {}).sort((a, b) => Number(a[0]) - Number(b[0])),
    [data.movingAverages],
  );
  const intraday = data.period === '60m' || data.period === '30m';
  const macd = data.macd && data.macd.hist.length === data.bars.length ? data.macd : null;
  const showMacdPane = overlays.showMacd && macd !== null;

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return undefined;

    const textColor = isDark ? '#cbd5e1' : '#334155';
    const gridColor = isDark ? 'rgba(148,163,184,0.12)' : 'rgba(100,116,139,0.12)';
    const chart = createChart(container, {
      autoSize: true,
      layout: {
        background: { type: ColorType.Solid, color: 'transparent' },
        textColor,
        attributionLogo: false,
      },
      grid: { vertLines: { color: gridColor }, horzLines: { color: gridColor } },
      crosshair: { mode: CrosshairMode.Normal },
      rightPriceScale: { borderVisible: false, scaleMargins: { top: 0.06, bottom: 0.24 } },
      timeScale: { borderVisible: false, timeVisible: intraday, secondsVisible: false },
      localization: { locale: 'zh-CN' },
    });
    chartRef.current = chart;

    const candles = chart.addSeries(CandlestickSeries, {
      upColor: UP_COLOR,
      downColor: DOWN_COLOR,
      borderUpColor: UP_COLOR,
      borderDownColor: DOWN_COLOR,
      wickUpColor: UP_COLOR,
      wickDownColor: DOWN_COLOR,
    });
    candles.setData(
      data.bars.map((bar, i) => ({ time: times[i], open: bar.open, high: bar.high, low: bar.low, close: bar.close })),
    );

    const volume = chart.addSeries(HistogramSeries, {
      priceFormat: { type: 'volume' },
      priceScaleId: 'volume',
      lastValueVisible: false,
      priceLineVisible: false,
    });
    chart.priceScale('volume').applyOptions({ scaleMargins: { top: 0.8, bottom: 0 } });
    volume.setData(
      data.bars.map((bar, i) => ({
        time: times[i],
        value: bar.volume ?? 0,
        color: bar.close >= bar.open ? 'rgba(239,68,68,0.45)' : 'rgba(34,197,94,0.45)',
      })),
    );

    const lineDefaults = {
      lastValueVisible: false,
      priceLineVisible: false,
      crosshairMarkerVisible: false,
    } as const;

    if (overlays.showMa) {
      maEntries.forEach(([, values], idx) => {
        const series = chart.addSeries(LineSeries, {
          ...lineDefaults,
          color: MA_COLORS[idx % MA_COLORS.length],
          lineWidth: 1,
        });
        series.setData(
          values.flatMap((value, i) => (value === null || value === undefined ? [] : [{ time: times[i], value }])),
        );
      });
    }
    if (overlays.showBi && data.chan.bi.length) {
      chart.addSeries(LineSeries, { ...lineDefaults, color: BI_COLOR, lineWidth: 1 }).setData(toPolyline(data.chan.bi, times));
    }
    if (overlays.showSegments && data.chan.segments.length) {
      chart
        .addSeries(LineSeries, { ...lineDefaults, color: SEGMENT_COLOR, lineWidth: 3 })
        .setData(toPolyline(data.chan.segments, times));
    }
    const pivots = data.chan.pivots ?? [];
    if (overlays.showPivots && pivots.length) {
      candles.attachPrimitive(new PivotBoxesPrimitive(pivots, PIVOT_STYLE));
    }
    const buyPoints = data.chan.buyPoints ?? [];
    if (overlays.showBuyPoints && buyPoints.length) {
      createSeriesMarkers(
        candles,
        toBuyMarkers(buyPoints, times, (kind) => t(`kline.buy.${kind}`), (kind) => BUY_COLORS[kind]),
      );
    }

    if (showMacdPane && macd) {
      // MACD 放在独立的第二个窗格：红绿柱 + DIF/DEA 两条线
      chart
        .addSeries(
          HistogramSeries,
          { lastValueVisible: false, priceLineVisible: false, priceFormat: { type: 'price', precision: 2, minMove: 0.01 } },
          1,
        )
        .setData(
          macd.hist.map((value, i) => ({
            time: times[i],
            value,
            color: value >= 0 ? 'rgba(239,68,68,0.7)' : 'rgba(34,197,94,0.7)',
          })),
        );
      chart
        .addSeries(LineSeries, { ...lineDefaults, color: MACD_DIF_COLOR, lineWidth: 1 }, 1)
        .setData(macd.dif.map((value, i) => ({ time: times[i], value })));
      chart
        .addSeries(LineSeries, { ...lineDefaults, color: MACD_DEA_COLOR, lineWidth: 1 }, 1)
        .setData(macd.dea.map((value, i) => ({ time: times[i], value })));
      chart.panes()[1]?.setHeight(MACD_PANE_HEIGHT);
    }

    const total = data.bars.length;
    // 窄屏上按每根 K 线约 5px 估算，避免手机上一屏挤进 180 根
    const visibleBars = Math.max(40, Math.min(DEFAULT_VISIBLE_BARS, Math.floor(container.clientWidth / 5)));
    if (total > visibleBars) {
      chart.timeScale().setVisibleLogicalRange({ from: total - visibleBars, to: total + 2 });
    } else {
      chart.timeScale().fitContent();
    }

    const onMove = (param: MouseEventParams) => {
      if (param.logical === undefined || param.logical === null || !param.point) {
        setHoverIndex(null);
        return;
      }
      const idx = Math.round(param.logical);
      setHoverIndex(idx >= 0 && idx < total ? idx : null);
    };
    chart.subscribeCrosshairMove(onMove);

    return () => {
      chart.unsubscribeCrosshairMove(onMove);
      chart.remove();
      chartRef.current = null;
    };
  }, [
    data,
    times,
    maEntries,
    overlays.showMa,
    overlays.showBi,
    overlays.showSegments,
    overlays.showPivots,
    overlays.showBuyPoints,
    showMacdPane,
    macd,
    isDark,
    intraday,
    t,
  ]);

  const legend: LegendState | null = useMemo(() => {
    if (!data.bars.length) return null;
    const idx = hoverIndex ?? data.bars.length - 1;
    const bar = data.bars[idx];
    const prev = idx > 0 ? data.bars[idx - 1] : null;
    return {
      time: bar.time,
      open: bar.open,
      high: bar.high,
      low: bar.low,
      close: bar.close,
      changePct: prev && prev.close ? ((bar.close - prev.close) / prev.close) * 100 : null,
      volume: bar.volume ?? null,
      ma: maEntries.map(([key, values], i) => ({
        key,
        value: values[idx] ?? null,
        color: MA_COLORS[i % MA_COLORS.length],
      })),
      macd: macd ? { dif: macd.dif[idx], dea: macd.dea[idx], hist: macd.hist[idx] } : null,
    };
  }, [data.bars, hoverIndex, maEntries, macd]);

  return (
    <div className={className}>
      {legend ? (
        <div className="mb-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs tabular-nums text-secondary-text" data-testid="kline-legend">
          <span className="text-foreground">{legend.time}</span>
          <span>{t('kline.legend.open')} {legend.open.toFixed(2)}</span>
          <span>{t('kline.legend.high')} {legend.high.toFixed(2)}</span>
          <span>{t('kline.legend.low')} {legend.low.toFixed(2)}</span>
          <span>{t('kline.legend.close')} {legend.close.toFixed(2)}</span>
          {legend.changePct !== null ? (
            <span style={{ color: legend.changePct >= 0 ? UP_COLOR : DOWN_COLOR }}>
              {legend.changePct >= 0 ? '+' : ''}
              {legend.changePct.toFixed(2)}%
            </span>
          ) : null}
          <span>{t('kline.legend.volume')} {formatVolume(legend.volume)}</span>
          {overlays.showMa
            ? legend.ma.map((item) => (
                <span key={item.key} style={{ color: item.color }}>
                  MA{item.key} {item.value !== null ? item.value.toFixed(2) : '-'}
                </span>
              ))
            : null}
          {showMacdPane && legend.macd ? (
            <>
              <span style={{ color: MACD_DIF_COLOR }}>DIF {legend.macd.dif.toFixed(2)}</span>
              <span style={{ color: MACD_DEA_COLOR }}>DEA {legend.macd.dea.toFixed(2)}</span>
              <span style={{ color: legend.macd.hist >= 0 ? UP_COLOR : DOWN_COLOR }}>MACD {legend.macd.hist.toFixed(2)}</span>
            </>
          ) : null}
        </div>
      ) : null}
      <div
        ref={containerRef}
        className={showMacdPane ? 'h-[520px] w-full sm:h-[640px]' : 'h-[420px] w-full sm:h-[520px]'}
        data-testid="kline-chart"
      />
    </div>
  );
};
