import type { UTCTimestamp } from 'lightweight-charts';
import type { ChanBuyPoint, ChanPivot, ChanPoint } from '../../api/kline';
import type { PivotBox } from './chanPivotsPrimitive';

/** 把接口给的北京时间字符串按 UTC 解释，让图上显示的时刻与原始时间一致。 */
export function toChartTime(value: string): UTCTimestamp {
  const match = /^(\d{4})-(\d{2})-(\d{2})(?:[ T](\d{2}):(\d{2}))?/.exec(value);
  if (!match) {
    return (Date.parse(value) / 1000) as UTCTimestamp;
  }
  const [, y, m, d, hh = '0', mm = '0'] = match;
  return (Date.UTC(Number(y), Number(m) - 1, Number(d), Number(hh), Number(mm)) / 1000) as UTCTimestamp;
}

/** 把笔/线段端点映射成折线数据，丢弃越界或时间不递增的点。 */
export function toPolyline(points: ChanPoint[], times: UTCTimestamp[]) {
  const result: Array<{ time: UTCTimestamp; value: number }> = [];
  for (const point of points) {
    const time = times[point.index];
    if (time === undefined) continue;
    if (result.length && time <= result[result.length - 1].time) continue;
    result.push({ time, value: point.price });
  }
  return result;
}

/** 把中枢映射成矩形，丢弃越界或宽度为 0 的中枢。 */
export function toPivotBoxes(pivots: ChanPivot[], times: UTCTimestamp[]): PivotBox[] {
  return pivots.flatMap((pivot) => {
    const from = times[pivot.startIndex];
    const to = times[pivot.endIndex];
    if (from === undefined || to === undefined || to <= from) return [];
    return [{ from, to, top: pivot.zg, bottom: pivot.zd }];
  });
}

/** 把买点映射成按时间升序的标记数据（lightweight-charts 要求标记有序）。 */
export function toBuyPointMarkers(
  points: ChanBuyPoint[],
  times: UTCTimestamp[],
  label: (type: ChanBuyPoint['type']) => string,
  color: string,
) {
  return points
    .flatMap((point) => {
      const time = times[point.index];
      if (time === undefined) return [];
      return [{
        time,
        position: 'belowBar' as const,
        shape: 'arrowUp' as const,
        color,
        text: label(point.type),
      }];
    })
    .sort((a, b) => a.time - b.time);
}
