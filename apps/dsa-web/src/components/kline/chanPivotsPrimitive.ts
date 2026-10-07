import type {
  IChartApi,
  IPrimitivePaneRenderer,
  IPrimitivePaneView,
  ISeriesApi,
  ISeriesPrimitive,
  SeriesAttachedParameter,
  SeriesType,
  Time,
} from 'lightweight-charts';

export type PivotBox = {
  from: Time;
  to: Time;
  top: number;
  bottom: number;
};

type PixelBox = { x1: number; x2: number; y1: number; y2: number };
type DrawTarget = Parameters<IPrimitivePaneRenderer['draw']>[0];

class PivotBoxRenderer implements IPrimitivePaneRenderer {
  private readonly boxes: PixelBox[];
  private readonly fill: string;
  private readonly stroke: string;

  constructor(boxes: PixelBox[], fill: string, stroke: string) {
    this.boxes = boxes;
    this.fill = fill;
    this.stroke = stroke;
  }

  draw(target: DrawTarget): void {
    target.useBitmapCoordinateSpace(({ context, horizontalPixelRatio: hr, verticalPixelRatio: vr }) => {
      context.save();
      context.fillStyle = this.fill;
      context.strokeStyle = this.stroke;
      context.lineWidth = Math.max(1, Math.round(hr));
      for (const box of this.boxes) {
        const x = Math.round(Math.min(box.x1, box.x2) * hr);
        const y = Math.round(Math.min(box.y1, box.y2) * vr);
        const w = Math.round(Math.abs(box.x2 - box.x1) * hr);
        const h = Math.round(Math.abs(box.y2 - box.y1) * vr);
        context.fillRect(x, y, w, h);
        context.strokeRect(x + 0.5, y + 0.5, w, h);
      }
      context.restore();
    });
  }
}

class PivotBoxView implements IPrimitivePaneView {
  private readonly source: ChanPivotsPrimitive;

  constructor(source: ChanPivotsPrimitive) {
    this.source = source;
  }

  zOrder() {
    return 'bottom' as const;
  }

  renderer(): IPrimitivePaneRenderer | null {
    const pixels = this.source.pixelBoxes();
    return pixels.length ? new PivotBoxRenderer(pixels, this.source.fill, this.source.stroke) : null;
  }
}

/** 在 K 线下方绘制缠论中枢（ZD~ZG 价格区间的矩形）。 */
export class ChanPivotsPrimitive implements ISeriesPrimitive<Time> {
  private chart: IChartApi | null = null;
  private series: ISeriesApi<SeriesType> | null = null;
  private readonly views = [new PivotBoxView(this)];
  private readonly boxes: PivotBox[];
  readonly fill: string;
  readonly stroke: string;

  constructor(boxes: PivotBox[], fill: string, stroke: string) {
    this.boxes = boxes;
    this.fill = fill;
    this.stroke = stroke;
  }

  attached(param: SeriesAttachedParameter<Time>): void {
    this.chart = param.chart as IChartApi;
    this.series = param.series as ISeriesApi<SeriesType>;
  }

  detached(): void {
    this.chart = null;
    this.series = null;
  }

  paneViews(): readonly IPrimitivePaneView[] {
    return this.views;
  }

  pixelBoxes(): PixelBox[] {
    if (!this.chart || !this.series) return [];
    const timeScale = this.chart.timeScale();
    const result: PixelBox[] = [];
    for (const box of this.boxes) {
      const x1 = timeScale.timeToCoordinate(box.from);
      const x2 = timeScale.timeToCoordinate(box.to);
      const y1 = this.series.priceToCoordinate(box.top);
      const y2 = this.series.priceToCoordinate(box.bottom);
      if (x1 === null || x2 === null || y1 === null || y2 === null) continue;
      result.push({ x1, x2, y1, y2 });
    }
    return result;
  }
}
