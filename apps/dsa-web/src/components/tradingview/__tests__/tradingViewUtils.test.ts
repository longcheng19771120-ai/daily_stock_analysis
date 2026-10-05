import { describe, expect, it } from 'vitest';
import { toTradingViewSymbol, tradingViewLocale, tradingViewScriptUrl } from '../tradingViewUtils';

describe('toTradingViewSymbol', () => {
  it.each([
    ['600519', 'SSE:600519'],
    ['688981', 'SSE:688981'],
    ['000001', 'SZSE:000001'],
    ['300750', 'SZSE:300750'],
    ['430047', 'BSE:430047'],
    ['920118', 'BSE:920118'],
    ['sh600519', 'SSE:600519'],
    ['SZ.000858', 'SZSE:000858'],
    ['HK00700', 'HKEX:700'],
    ['hk09988', 'HKEX:9988'],
    ['00700.HK', 'HKEX:700'],
    ['aapl', 'AAPL'],
    ['BRK.B', 'BRK.B'],
  ])('maps %s to %s', (input, expected) => {
    expect(toTradingViewSymbol(input)).toBe(expected);
  });

  it.each(['', '   ', '12345', 'HK00000', '中文', '1ABC'])('returns null for %j', (input) => {
    expect(toTradingViewSymbol(input)).toBeNull();
  });
});

describe('tradingView helpers', () => {
  it('builds the embed script url', () => {
    expect(tradingViewScriptUrl('technical-analysis')).toBe(
      'https://s3.tradingview.com/external-embedding/embed-widget-technical-analysis.js',
    );
  });

  it('maps ui language to tradingview locale', () => {
    expect(tradingViewLocale('zh')).toBe('zh_CN');
    expect(tradingViewLocale('en')).toBe('en');
  });
});
