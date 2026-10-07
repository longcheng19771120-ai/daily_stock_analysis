import apiClient from './index';
import { toCamelCase } from './utils';

export type KlinePeriod = 'daily' | 'weekly' | '60m' | '30m';

export type ChartBar = {
  /** 日线 YYYY-MM-DD，分钟线 YYYY-MM-DD HH:MM（北京时间） */
  time: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume?: number | null;
  amount?: number | null;
};

export type ChanPoint = {
  index: number;
  price: number;
  kind: 'top' | 'bottom';
};

export type ChanPivot = {
  startIndex: number;
  endIndex: number;
  /** 中枢上沿 */
  zg: number;
  /** 中枢下沿 */
  zd: number;
};

export type ChanBuyPoint = {
  index: number;
  price: number;
  /** 1=一买 2=二买 3=三买 */
  type: 1 | 2 | 3;
};

export type StockKline = {
  stockCode: string;
  stockName?: string | null;
  period: KlinePeriod;
  source?: string | null;
  bars: ChartBar[];
  movingAverages: Record<string, Array<number | null>>;
  chan: {
    bi: ChanPoint[];
    segments: ChanPoint[];
    pivots?: ChanPivot[];
    buyPoints?: ChanBuyPoint[];
  };
};

export const klineApi = {
  async getKline(stockCode: string, period: KlinePeriod, days = 365): Promise<StockKline> {
    const response = await apiClient.get<Record<string, unknown>>(
      `/api/v1/stocks/${encodeURIComponent(stockCode)}/kline`,
      { params: { period, days }, timeout: 60000 },
    );
    return toCamelCase<StockKline>(response.data);
  },
};
