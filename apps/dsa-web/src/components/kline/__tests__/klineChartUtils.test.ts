import { describe, expect, it } from 'vitest';
import type { UTCTimestamp } from 'lightweight-charts';
import { toBuyPointMarkers, toChartTime, toPivotBoxes, toPolyline } from '../klineChartUtils';

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

  it('maps pivots to boxes and drops out-of-range or empty ones', () => {
    const times = [100, 200, 300, 400] as UTCTimestamp[];
    const boxes = toPivotBoxes(
      [
        { startIndex: 1, endIndex: 3, zg: 12, zd: 10 },
        { startIndex: 2, endIndex: 2, zg: 12, zd: 10 },
        { startIndex: 3, endIndex: 7, zg: 12, zd: 10 },
      ],
      times,
    );
    expect(boxes).toEqual([{ from: 200, to: 400, top: 12, bottom: 10 }]);
  });

  it('maps buy points to time-sorted below-bar markers', () => {
    const times = [100, 200, 300, 400] as UTCTimestamp[];
    const markers = toBuyPointMarkers(
      [
        { index: 3, price: 11, type: 2 },
        { index: 1, price: 9, type: 1 },
        { index: 8, price: 9, type: 3 },
      ],
      times,
      (type) => `B${type}`,
      '#f00',
    );
    expect(markers.map((m) => [m.time, m.text, m.position, m.shape])).toEqual([
      [200, 'B1', 'belowBar', 'arrowUp'],
      [400, 'B2', 'belowBar', 'arrowUp'],
    ]);
  });
});
