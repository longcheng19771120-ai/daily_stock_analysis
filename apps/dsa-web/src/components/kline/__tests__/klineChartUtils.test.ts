import { describe, expect, it } from 'vitest';
import type { UTCTimestamp } from 'lightweight-charts';
import { computeMacd, toBuyMarkers, toChartTime, toPolyline } from '../klineChartUtils';

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

  it('maps buy points to sorted below-bar markers and drops out-of-range points', () => {
    const times = [100, 200, 300] as UTCTimestamp[];
    const markers = toBuyMarkers(
      [
        { index: 2, price: 12, kind: 'buy2' },
        { index: 7, price: 9, kind: 'buy3' },
        { index: 0, price: 10, kind: 'buy1' },
      ],
      times,
      (kind) => kind.toUpperCase(),
      () => '#f00',
    );
    expect(markers).toEqual([
      { time: 100, position: 'belowBar', shape: 'arrowUp', color: '#f00', text: 'BUY1' },
      { time: 300, position: 'belowBar', shape: 'arrowUp', color: '#f00', text: 'BUY2' },
    ]);
  });

  it('computes MACD with first-close seeded EMAs and a doubled histogram', () => {
    const flat = computeMacd([10, 10, 10]);
    expect(flat.dif).toEqual([0, 0, 0]);
    expect(flat.hist).toEqual([0, 0, 0]);

    const macd = computeMacd([10, 11]);
    // EMA12 = 10 + 1 * 2/13, EMA26 = 10 + 1 * 2/27
    const dif = 2 / 13 - 2 / 27;
    expect(macd.dif[1]).toBeCloseTo(dif, 10);
    expect(macd.dea[1]).toBeCloseTo(dif * 0.2, 10);
    expect(macd.hist[1]).toBeCloseTo(2 * (dif - dif * 0.2), 10);

    const rising = computeMacd(Array.from({ length: 60 }, (_, i) => 10 + i));
    expect(rising.dif[59]).toBeGreaterThan(0);
    expect(rising.hist).toHaveLength(60);
  });
});
