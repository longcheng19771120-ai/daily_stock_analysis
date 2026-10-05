/**
 * TradingView 免费嵌入小部件的辅助函数。
 *
 * 小部件脚本与行情数据都来自 TradingView（s3.tradingview.com），不经过本项目后端。
 */

export const TRADINGVIEW_SCRIPT_BASE = 'https://s3.tradingview.com/external-embedding/embed-widget-';

export type TradingViewWidgetName =
  | 'market-overview'
  | 'stock-heatmap'
  | 'timeline'
  | 'technical-analysis'
  | 'symbol-profile'
  | 'financials'
  | 'symbol-info';

export function tradingViewScriptUrl(widget: TradingViewWidgetName): string {
  return `${TRADINGVIEW_SCRIPT_BASE}${widget}.js`;
}

/** 本项目 UI 语言到 TradingView locale 的映射。 */
export function tradingViewLocale(language: string): string {
  return language === 'en' ? 'en' : 'zh_CN';
}

/**
 * 把本项目的股票代码转换为 TradingView 的 EXCHANGE:SYMBOL 形式。
 *
 * - A 股：6/9 开头为上交所（SSE），0/2/3 开头为深交所（SZSE），4/8/920 开头为北交所（BSE）
 * - 港股：HK00700 / hk700 -> HKEX:700
 * - 美股等字母代码：原样大写交给 TradingView 自行解析交易所
 *
 * 无法识别时返回 null，调用方应不渲染小部件。
 */
export function toTradingViewSymbol(code: string): string | null {
  const raw = code.trim().toUpperCase();
  if (!raw) return null;

  const prefixed = raw.match(/^(SH|SZ|BJ)\.?(\d{6})$/);
  if (prefixed) {
    const exchange = { SH: 'SSE', SZ: 'SZSE', BJ: 'BSE' }[prefixed[1] as 'SH' | 'SZ' | 'BJ'];
    return `${exchange}:${prefixed[2]}`;
  }

  if (/^\d{6}$/.test(raw)) {
    if (raw.startsWith('920') || raw.startsWith('4') || raw.startsWith('8')) return `BSE:${raw}`;
    if (raw.startsWith('6') || raw.startsWith('9')) return `SSE:${raw}`;
    if (raw.startsWith('0') || raw.startsWith('2') || raw.startsWith('3')) return `SZSE:${raw}`;
    return null;
  }

  const hk = raw.match(/^HK\.?(\d{1,5})$/) ?? raw.match(/^(\d{1,5})\.HK$/);
  if (hk) {
    const digits = hk[1].replace(/^0+/, '');
    return digits ? `HKEX:${digits}` : null;
  }

  if (/^[A-Z][A-Z0-9.-]{0,9}$/.test(raw)) {
    return raw;
  }
  return null;
}
