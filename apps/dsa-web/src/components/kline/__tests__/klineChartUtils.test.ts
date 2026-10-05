import { describe, expect, it } from 'vitest';
import type { UTCTimestamp } from 'lightweight-charts';
import { toChartTime, toPolyline } from '../klineChartUtils';

describe('klineChartUtils', () => {
  it('treats daily and minute strings as wall-clock UTC timestamps', () => {
    expect(toChartTime('2026-09-30')).toBe(Date.UTC(2026, 8, 30) / 1000);
    expect(toChartTime('2026-09-30 14:30')).toBe(Date.UTC(2026, 8, 30, 14, 30) / 1000);
  });

  it('maps chan points to strictly increasing polyline points', () => {
    const times = [100, 200, 300, 400] as UTCTimestamp[];
    const line = toPolyline(
      [
        { index: 0, price: 10, kind: 'bottom' },
        { index: 2, price: 20, kind: 'top' },
        { index: 2, price: 15, kind: 'bottom' },
        { index: 9, price: 30, kind: 'top' },
        { index: 3, price: 12, kind: 'bottom' },
      ],
      times,
    );
    expect(line).toEqual([
      { time: 100, value: 10 },
      { time: 300, value: 20 },
      { time: 400, value: 12 },
    ]);
  });
});
