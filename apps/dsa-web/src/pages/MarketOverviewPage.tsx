import type React from 'react';
import { useMemo, useState } from 'react';
import { AppPage, Card, PageHeader } from '../components/common';
import { TradingViewWidget } from '../components/tradingview/TradingViewWidget';
import { useUiLanguage } from '../contexts/UiLanguageContext';
import type { UiTextKey } from '../i18n/uiText';
import { cn } from '../utils/cn';

const HEATMAP_SOURCES: Array<{ value: string; labelKey: UiTextKey }> = [
  { value: 'SPX500', labelKey: 'market.heatmap.spx500' },
  { value: 'NASDAQ100', labelKey: 'market.heatmap.nasdaq100' },
];

const MarketOverviewPage: React.FC = () => {
  const { t } = useUiLanguage();
  const [heatmapSource, setHeatmapSource] = useState(HEATMAP_SOURCES[0].value);

  const overviewConfig = useMemo(() => ({
    dateRange: '12M',
    showChart: true,
    showSymbolLogo: true,
    showFloatingTooltip: true,
    tabs: [
      {
        title: t('market.tab.china'),
        symbols: [
          { s: 'SSE:000001', d: t('market.symbol.sseComposite') },
          { s: 'SZSE:399001', d: t('market.symbol.szseComponent') },
          { s: 'SZSE:399006', d: t('market.symbol.chinext') },
          { s: 'SSE:000300', d: t('market.symbol.csi300') },
          { s: 'HSI:HSI', d: t('market.symbol.hangSeng') },
        ],
      },
      {
        title: t('market.tab.us'),
        symbols: [
          { s: 'FOREXCOM:SPXUSD', d: 'S&P 500' },
          { s: 'FOREXCOM:NSXUSD', d: 'Nasdaq 100' },
          { s: 'FOREXCOM:DJI', d: 'Dow Jones' },
          { s: 'INDEX:NKY', d: 'Nikkei 225' },
          { s: 'INDEX:DEU40', d: 'DAX' },
        ],
      },
      {
        title: t('market.tab.commodities'),
        symbols: [
          { s: 'COMEX:GC1!', d: t('market.symbol.gold') },
          { s: 'NYMEX:CL1!', d: t('market.symbol.crude') },
          { s: 'FX_IDC:USDCNH', d: 'USD/CNH' },
          { s: 'BITSTAMP:BTCUSD', d: 'BTC/USD' },
        ],
      },
    ],
  }), [t]);

  const heatmapConfig = useMemo(() => ({
    dataSource: heatmapSource,
    blockSize: 'market_cap_basic',
    blockColor: 'change',
    grouping: 'sector',
    hasTopBar: false,
    isDataSetEnabled: false,
    isZoomEnabled: true,
    hasSymbolTooltip: true,
    isMonoSize: false,
  }), [heatmapSource]);

  const newsConfig = useMemo(() => ({ displayMode: 'regular', feedMode: 'market', market: 'stock' }), []);

  return (
    <AppPage>
      <div className="space-y-5">
        <PageHeader eyebrow={t('market.eyebrow')} title={t('market.title')} description={t('market.description')} />

        <div className="grid gap-5 xl:grid-cols-3">
          <Card padding="sm" className="rounded-lg xl:col-span-2">
            <h2 className="mb-3 text-base font-semibold text-foreground">{t('market.section.overview')}</h2>
            <TradingViewWidget widget="market-overview" config={overviewConfig} height={560} />
          </Card>
          <Card padding="sm" className="rounded-lg">
            <h2 className="mb-3 text-base font-semibold text-foreground">{t('market.section.news')}</h2>
            <TradingViewWidget widget="timeline" config={newsConfig} height={560} />
          </Card>
        </div>

        <Card padding="sm" className="rounded-lg">
          <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
            <h2 className="text-base font-semibold text-foreground">{t('market.section.heatmap')}</h2>
            <div className="inline-flex rounded-xl border border-border/70 bg-card/70 p-1">
              {HEATMAP_SOURCES.map((option) => (
                <button
                  key={option.value}
                  type="button"
                  aria-pressed={heatmapSource === option.value}
                  onClick={() => setHeatmapSource(option.value)}
                  className={cn(
                    'rounded-lg px-3 py-1.5 text-sm transition-colors',
                    heatmapSource === option.value
                      ? 'bg-cyan text-background shadow-soft-card'
                      : 'text-secondary-text hover:bg-hover hover:text-foreground',
                  )}
                >
                  {t(option.labelKey)}
                </button>
              ))}
            </div>
          </div>
          <TradingViewWidget widget="stock-heatmap" config={heatmapConfig} height={560} />
        </Card>

        <p className="text-xs text-secondary-text">{t('market.note')}</p>
      </div>
    </AppPage>
  );
};

export default MarketOverviewPage;
