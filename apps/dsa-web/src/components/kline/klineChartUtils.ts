import type { UTCTimestamp } from 'lightweight-charts';
import type { ChanBuyPoint, ChanPoint } from '../../api/kline';

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

/** 把买点映射成 K 线下方的向上箭头标记，按时间升序并丢弃越界点。 */
export function toBuyMarkers(
  points: ChanBuyPoint[],
  times: UTCTimestamp[],
  labelFor: (kind: ChanBuyPoint['kind']) => string,
  colorFor: (kind: ChanBuyPoint['kind']) => string,
) {
  return points
    .filter((point) => times[point.index] !== undefined)
    .sort((a, b) => a.index - b.index)
    .map((point) => ({
      time: times[point.index],
      position: 'belowBar' as const,
      shape: 'arrowUp' as const,
      color: colorFor(point.kind),
      text: labelFor(point.kind),
    }));
}
