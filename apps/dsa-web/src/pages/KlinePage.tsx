import type React from 'react';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { RefreshCw, Search } from 'lucide-react';
import { useSearchParams } from 'react-router-dom';
import { klineApi, type KlinePeriod, type StockKline } from '../api/kline';
import { getParsedApiError, type ParsedApiError } from '../api/error';
import { ApiErrorAlert, AppPage, Card, EmptyState, PageHeader } from '../components/common';
import { KlineChart, type KlineOverlayOptions } from '../components/kline/KlineChart';
import { StockAutocomplete } from '../components/StockAutocomplete';
import { TradingViewWidget } from '../components/tradingview/TradingViewWidget';
import { toTradingViewSymbol } from '../components/tradingview/tradingViewUtils';
import { useUiLanguage } from '../contexts/UiLanguageContext';
import type { UiTextKey } from '../i18n/uiText';
import { cn } from '../utils/cn';

const PERIODS: Array<{ value: KlinePeriod; labelKey: UiTextKey }> = [
  { value: '30m', labelKey: 'kline.period.30m' },
  { value: '60m', labelKey: 'kline.period.60m' },
  { value: 'daily', labelKey: 'kline.period.daily' },
  { value: 'weekly', labelKey: 'kline.period.weekly' },
];

const OVERLAYS: Array<{ key: keyof KlineOverlayOptions; labelKey: UiTextKey }> = [
  { key: 'showMa', labelKey: 'kline.overlay.ma' },
  { key: 'showBi', labelKey: 'kline.overlay.bi' },
  { key: 'showSegments', labelKey: 'kline.overlay.segments' },
  { key: 'showPivots', labelKey: 'kline.overlay.pivots' },
  { key: 'showBuyPoints', labelKey: 'kline.overlay.buyPoints' },
];

const DEFAULT_CODE = '600519';

function isKlinePeriod(value: string | null): value is KlinePeriod {
  return value === 'daily' || value === 'weekly' || value === '60m' || value === '30m';
}

const KlinePage: React.FC = () => {
  const { t } = useUiLanguage();
  const [searchParams, setSearchParams] = useSearchParams();
  const code = (searchParams.get('code') || DEFAULT_CODE).trim();
  const periodParam = searchParams.get('period');
  const period: KlinePeriod = isKlinePeriod(periodParam) ? periodParam : 'daily';

  const [inputCode, setInputCode] = useState(code);
  const [data, setData] = useState<StockKline | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<ParsedApiError | null>(null);
  const [overlays, setOverlays] = useState<KlineOverlayOptions>({
    showMa: true,
    showBi: true,
    showSegments: true,
    showPivots: true,
    showBuyPoints: true,
  });

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setData(await klineApi.getKline(code, period));
    } catch (err) {
      setData(null);
      setError(getParsedApiError(err));
    } finally {
      setLoading(false);
    }
  }, [code, period]);

  useEffect(() => {
    void load();
  }, [load]);

  const updateParams = (next: { code?: string; period?: KlinePeriod }) => {
    setSearchParams({ code: next.code ?? code, period: next.period ?? period });
  };

  const onSubmit = (event: React.FormEvent) => {
    event.preventDefault();
    const nextCode = inputCode.trim();
    if (nextCode) updateParams({ code: nextCode });
  };

  const tvSymbol = toTradingViewSymbol(code);
  const tvConfigs = useMemo(() => (tvSymbol ? {
    technical: { symbol: tvSymbol, interval: '1D', showIntervalTabs: true, displayMode: 'single' },
    profile: { symbol: tvSymbol },
    financials: { symbol: tvSymbol, displayMode: 'regular' },
  } : null), [tvSymbol]);

  const title = data?.stockName ? `${data.stockName} (${data.stockCode})` : code;

  return (
    <AppPage>
      <div className="space-y-5">
        <PageHeader
          eyebrow={t('kline.eyebrow')}
          title={t('kline.title')}
          description={t('kline.description')}
          actions={(
            <form className="flex flex-wrap items-center gap-2" onSubmit={onSubmit}>
              <div className="w-56 min-w-0">
                <StockAutocomplete
                  value={inputCode}
                  onChange={setInputCode}
                  onSubmit={(nextCode) => {
                    setInputCode(nextCode);
                    if (nextCode.trim()) updateParams({ code: nextCode.trim() });
                  }}
                  placeholder={t('kline.codePlaceholder')}
                  ariaLabel={t('kline.codeLabel')}
                />
              </div>
              <button type="submit" className="btn-secondary inline-flex items-center gap-2">
                <Search className="h-4 w-4" />
                {t('kline.view')}
              </button>
              <button
                type="button"
                className="btn-secondary inline-flex items-center gap-2"
                onClick={() => void load()}
                disabled={loading}
                aria-label={t('kline.refresh')}
              >
                <RefreshCw className={cn('h-4 w-4', loading ? 'animate-spin' : '')} />
              </button>
            </form>
          )}
        />

        <Card padding="sm" className="rounded-lg">
          <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
            <div className="min-w-0">
              <h2 className="truncate text-base font-semibold text-foreground">{title}</h2>
              {data?.source ? (
                <p className="mt-0.5 text-xs text-secondary-text">{t('kline.source', { source: data.source })}</p>
              ) : null}
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <div className="inline-flex rounded-xl border border-border/70 bg-card/70 p-1">
                {PERIODS.map((option) => (
                  <button
                    key={option.value}
                    type="button"
                    onClick={() => updateParams({ period: option.value })}
                    className={cn(
                      'rounded-lg px-3 py-1.5 text-sm transition-colors',
                      period === option.value
                        ? 'bg-cyan text-background shadow-soft-card'
                        : 'text-secondary-text hover:bg-hover hover:text-foreground',
                    )}
                  >
                    {t(option.labelKey)}
                  </button>
                ))}
              </div>
              <div className="inline-flex rounded-xl border border-border/70 bg-card/70 p-1">
                {OVERLAYS.map((option) => (
                  <button
                    key={option.key}
                    type="button"
                    aria-pressed={overlays[option.key]}
                    onClick={() => setOverlays((prev) => ({ ...prev, [option.key]: !prev[option.key] }))}
                    className={cn(
                      'rounded-lg px-3 py-1.5 text-sm transition-colors',
                      overlays[option.key]
                        ? 'bg-hover text-foreground'
                        : 'text-secondary-text line-through hover:text-foreground',
                    )}
                  >
                    {t(option.labelKey)}
                  </button>
                ))}
              </div>
            </div>
          </div>

          {error ? <ApiErrorAlert error={error} actionLabel={t('common.retry')} onAction={() => void load()} /> : null}
          {!error && data && data.bars.length ? <KlineChart data={data} overlays={overlays} /> : null}
          {!error && !loading && data && !data.bars.length ? (
            <EmptyState title={t('kline.emptyTitle')} description={t('kline.emptyDescription')} />
          ) : null}
          {loading && !data ? <p className="py-24 text-center text-sm text-secondary-text">{t('common.loading')}</p> : null}

          <p className="mt-3 text-xs text-secondary-text">{t('kline.chanNote')}</p>
        </Card>

        {tvConfigs ? (
          <section className="space-y-3" aria-label={t('kline.tv.title')}>
            <div>
              <h2 className="text-base font-semibold text-foreground">{t('kline.tv.title')}</h2>
              <p className="mt-0.5 text-xs text-secondary-text">{t('kline.tv.description', { symbol: tvSymbol ?? '' })}</p>
            </div>
            <div className="grid gap-5 lg:grid-cols-2 2xl:grid-cols-3">
              <Card padding="sm" className="min-w-0 rounded-lg">
                <h3 className="mb-2 text-sm font-semibold text-foreground">{t('kline.tv.technical')}</h3>
                <TradingViewWidget widget="technical-analysis" config={tvConfigs.technical} height={420} />
              </Card>
              <Card padding="sm" className="min-w-0 rounded-lg">
                <h3 className="mb-2 text-sm font-semibold text-foreground">{t('kline.tv.profile')}</h3>
                <TradingViewWidget widget="symbol-profile" config={tvConfigs.profile} height={420} />
              </Card>
              <Card padding="sm" className="min-w-0 rounded-lg lg:col-span-2 2xl:col-span-1">
                <h3 className="mb-2 text-sm font-semibold text-foreground">{t('kline.tv.financials')}</h3>
                <TradingViewWidget widget="financials" config={tvConfigs.financials} height={420} />
              </Card>
            </div>
          </section>
        ) : null}
      </div>
    </AppPage>
  );
};

export default KlinePage;
