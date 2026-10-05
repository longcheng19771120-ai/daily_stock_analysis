import type React from 'react';
import { useEffect, useMemo, useRef, useState } from 'react';
import { useTheme } from 'next-themes';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import { cn } from '../../utils/cn';
import { tradingViewLocale, tradingViewScriptUrl, type TradingViewWidgetName } from './tradingViewUtils';

// 脚本加载成功但迟迟没有生成 iframe（如被代理挂起）时，按失败处理
const LOAD_TIMEOUT_MS = 20000;

type TradingViewWidgetProps = {
  widget: TradingViewWidgetName;
  /** 小部件配置；colorTheme、locale、isTransparent 由组件按当前主题和语言补齐 */
  config: Record<string, unknown>;
  height: number;
  className?: string;
};

type LoadState = 'loading' | 'ready' | 'failed';

/**
 * 嵌入 TradingView 免费小部件。数据和脚本都来自 tradingview.com，
 * 网络无法访问时显示提示，不影响页面其他部分。
 */
export const TradingViewWidget: React.FC<TradingViewWidgetProps> = ({ widget, config, height, className }) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const { resolvedTheme } = useTheme();
  const { language, t } = useUiLanguage();
  // 记录状态对应的加载批次，配置变化后自动回到 loading，无需在 effect 里同步重置
  const [result, setResult] = useState<{ key: string; state: LoadState } | null>(null);
  const colorTheme = resolvedTheme === 'dark' ? 'dark' : 'light';
  const locale = tradingViewLocale(language);

  const configJson = useMemo(
    () => JSON.stringify({
      width: '100%',
      height,
      isTransparent: true,
      ...config,
      colorTheme,
      locale,
    }),
    [config, height, colorTheme, locale],
  );
  const loadKey = `${widget}|${configJson}`;
  const state: LoadState = result?.key === loadKey ? result.state : 'loading';

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return undefined;
    container.innerHTML = '';

    const target = document.createElement('div');
    target.className = 'tradingview-widget-container__widget';
    target.style.width = '100%';
    target.style.height = `${height}px`;
    container.appendChild(target);

    const script = document.createElement('script');
    script.src = tradingViewScriptUrl(widget);
    script.async = true;
    script.type = 'text/javascript';
    script.text = configJson;

    let settled = false;
    const finish = (next: LoadState) => {
      if (settled) return;
      settled = true;
      setResult({ key: loadKey, state: next });
    };
    script.onerror = () => finish('failed');
    const observer = new MutationObserver(() => {
      if (container.querySelector('iframe')) finish('ready');
    });
    observer.observe(container, { childList: true, subtree: true });
    const timer = window.setTimeout(() => finish(container.querySelector('iframe') ? 'ready' : 'failed'), LOAD_TIMEOUT_MS);

    container.appendChild(script);

    return () => {
      settled = true;
      observer.disconnect();
      window.clearTimeout(timer);
      container.innerHTML = '';
    };
  }, [widget, configJson, height, loadKey]);

  return (
    <div className={cn('relative w-full', className)} style={{ minHeight: height }}>
      <div ref={containerRef} className="tradingview-widget-container w-full" data-testid={`tradingview-${widget}`} />
      {state !== 'ready' ? (
        <div
          className="absolute inset-0 flex items-center justify-center rounded-lg border border-dashed border-border/70 px-6 text-center text-sm text-secondary-text"
          role={state === 'failed' ? 'status' : undefined}
        >
          {state === 'failed' ? t('tradingview.loadFailed') : t('tradingview.loading')}
        </div>
      ) : null}
      <p className="mt-1 text-right text-[11px] text-secondary-text">
        <a href="https://www.tradingview.com/" target="_blank" rel="noopener nofollow noreferrer" className="hover:text-foreground">
          {t('tradingview.attribution')}
        </a>
      </p>
    </div>
  );
};
