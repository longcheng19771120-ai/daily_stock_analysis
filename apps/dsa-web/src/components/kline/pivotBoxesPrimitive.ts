import type {
  IChartApiBase,
  IPrimitivePaneRenderer,
  IPrimitivePaneView,
  ISeriesApi,
  ISeriesPrimitive,
  Logical,
  SeriesAttachedParameter,
  SeriesType,
  Time,
} from 'lightweight-charts';
import type { CanvasRenderingTarget2D } from 'fancy-canvas';
import type { ChanPivot } from '../../api/kline';

type BoxStyle = {
  fill: string;
  border: string;
};

/** 把缠论中枢画成 [ZD, ZG] 的半透明矩形；未结束的中枢用虚线边框。 */
export class PivotBoxesPrimitive implements ISeriesPrimitive<Time> {
  private chart: IChartApiBase<Time> | null = null;
  private series: ISeriesApi<SeriesType, Time> | null = null;
  private readonly views: IPrimitivePaneView[];
  private readonly pivots: ChanPivot[];
  private readonly style: BoxStyle;

  constructor(pivots: ChanPivot[], style: BoxStyle) {
    this.pivots = pivots;
    this.style = style;
    const renderer: IPrimitivePaneRenderer = { draw: (target) => this.draw(target) };
    this.views = [{ renderer: () => renderer, zOrder: () => 'bottom' }];
  }

  attached({ chart, series }: SeriesAttachedParameter<Time, SeriesType>): void {
    this.chart = chart;
    this.series = series;
  }

  detached(): void {
    this.chart = null;
    this.series = null;
  }

  paneViews(): readonly IPrimitivePaneView[] {
    return this.views;
  }

  private draw(target: CanvasRenderingTarget2D): void {
    const chart = this.chart;
    const series = this.series;
    if (!chart || !series || !this.pivots.length) return;
    const timeScale = chart.timeScale();
    target.useBitmapCoordinateSpace(({ context: ctx, horizontalPixelRatio: hr, verticalPixelRatio: vr }) => {
      ctx.save();
      ctx.lineWidth = Math.max(1, Math.round(hr));
      for (const pivot of this.pivots) {
        const x1 = timeScale.logicalToCoordinate(pivot.startIndex as Logical);
        const x2 = timeScale.logicalToCoordinate(pivot.endIndex as Logical);
        const yTop = series.priceToCoordinate(pivot.zg);
        const yBottom = series.priceToCoordinate(pivot.zd);
        if (x1 === null || x2 === null || yTop === null || yBottom === null) continue;
        const left = Math.round(Math.min(x1, x2) * hr);
        const top = Math.round(Math.min(yTop, yBottom) * vr);
        const width = Math.max(1, Math.round(Math.abs(x2 - x1) * hr));
        const height = Math.max(1, Math.round(Math.abs(yBottom - yTop) * vr));
        ctx.fillStyle = this.style.fill;
        ctx.fillRect(left, top, width, height);
        ctx.strokeStyle = this.style.border;
        ctx.setLineDash(pivot.confirmed ? [] : [Math.round(4 * hr), Math.round(3 * hr)]);
        ctx.strokeRect(left + 0.5, top + 0.5, width - 1, height - 1);
      }
      ctx.restore();
    });
  }
}
