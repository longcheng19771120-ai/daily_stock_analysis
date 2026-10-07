# -*- coding: utf-8 -*-
"""
缠论结构计算（简化实现）：包含处理 -> 分型 -> 笔 -> 线段。

只做确定性的几何计算，输入为按时间升序的 K 线（high/low），输出为
可直接在图表上绘制的分型、笔和线段端点。各步骤的简化规则：

- 包含处理：相邻 K 线存在包含关系时合并，向上趋势取高高、向下趋势取低低。
- 分型：合并后 K 线中，中间一根的高点最高（顶分型）或低点最低（底分型）。
- 笔：顶底分型交替，两个分型之间至少隔一根独立 K 线（合并后序号差 >= 4），
  向上笔终点高于起点且是区间最高点、向下笔终点低于起点且是区间最低点；
  同类分型连续出现时保留更极端者；
  不能成笔的分型若比上一个同类端点更极端，则撤销中间端点、改以该分型为端点。
- 线段：以笔端点为序列。线段内跟踪同向极值，当极值之后的反向走势跌破
  （向上线段）或升破（向下线段）极值前一笔的起点、且线段已有三笔以上时，
  线段在极值处结束；若反向端点越过本线段起点，说明上一条线段尚未结束，
  将其延伸到该点。严格缠论要求线段至少三笔；这里只在序列首段放宽：若首段
  极值落在前一两笔、之后整段数据再未超越且已有三笔以上反向走势，则在极值处
  结束首段，避免整段数据因开头一笔急涨急跌而划不出线段。
  这是对特征序列分型判定的近似，不等同于完整的特征序列算法。
- 校正：笔和线段端点最后都会校正到相邻反向端点之间的真实极值上，保证
  每一笔、每一段的端点就是该区间的最高/最低点。
- 中枢（笔中枢）：连续三笔价格区间的重叠部分 [ZD, ZG]（ZG 取三笔高点最小值、
  ZD 取低点最大值，ZG > ZD 才成立）。之后终点仍在 [ZD, ZG] 内的笔算作中枢内
  震荡；终点离开区间的笔为离开笔，其后的回抽笔回到 [ZD, ZG] 内则中枢延伸，
  否则中枢结束（已确认）；数据末尾中枢未结束时
  标记为未确认：最后一笔仍在区间内则画到最后一根 K 线，已离开、等待回抽则
  画到离开笔起点。中枢之前的一笔是进入笔（首个中枢从
  第二笔开始找），上一个中枢的离开笔就是下一个中枢的进入笔。
- 买点（简化判定，仅供参考）：
  - 一买：中枢的进入笔与离开笔都向下，离开笔创出中枢以来新低，且离开笔的
    MACD 绿柱面积小于进入笔（背驰），买点在离开笔终点。
  - 二买：一买之后的下一个底分型端点不破一买低点。
  - 三买：中枢向上离开后，回抽笔的低点仍高于 ZG（不回中枢），买点在回抽笔终点。
  这里不区分盘整背驰与趋势背驰、也不做区间套，与完整缠论定义有差距。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence

MIN_BI_BAR_GAP = 4
MIN_SEGMENT_BI = 3


@dataclass(frozen=True)
class _MergedBar:
    high: float
    low: float
    # 原始 K 线中该合并 K 线极值所在的序号（用于在图上定位）
    high_index: int
    low_index: int


@dataclass(frozen=True)
class ChanPoint:
    """笔或线段的端点。kind 为 top/bottom，index 为原始 K 线序号。"""

    index: int
    price: float
    kind: str

    def to_dict(self) -> Dict[str, object]:
        return {"index": self.index, "price": self.price, "kind": self.kind}


def _merge_inclusive_bars(highs: Sequence[float], lows: Sequence[float]) -> List[_MergedBar]:
    merged: List[_MergedBar] = []
    for i, (high, low) in enumerate(zip(highs, lows)):
        bar = _MergedBar(high=float(high), low=float(low), high_index=i, low_index=i)
        if not merged:
            merged.append(bar)
            continue
        last = merged[-1]
        contains = (last.high >= bar.high and last.low <= bar.low) or (
            bar.high >= last.high and bar.low <= last.low
        )
        if not contains:
            merged.append(bar)
            continue
        # 方向由前一根合并 K 线决定，第一根时默认向上
        upward = True
        if len(merged) >= 2:
            upward = last.high > merged[-2].high
        if upward:
            high, high_index = (last.high, last.high_index) if last.high >= bar.high else (bar.high, bar.high_index)
            low, low_index = (last.low, last.low_index) if last.low >= bar.low else (bar.low, bar.low_index)
        else:
            high, high_index = (last.high, last.high_index) if last.high <= bar.high else (bar.high, bar.high_index)
            low, low_index = (last.low, last.low_index) if last.low <= bar.low else (bar.low, bar.low_index)
        merged[-1] = _MergedBar(high=high, low=low, high_index=high_index, low_index=low_index)
    return merged


def find_fractals(highs: Sequence[float], lows: Sequence[float]) -> List[Dict[str, object]]:
    """返回分型列表，每项含 merged_index（合并 K 线序号）与端点信息。"""
    merged = _merge_inclusive_bars(highs, lows)
    fractals: List[Dict[str, object]] = []
    for i in range(1, len(merged) - 1):
        prev_bar, bar, next_bar = merged[i - 1], merged[i], merged[i + 1]
        if bar.high > prev_bar.high and bar.high > next_bar.high:
            fractals.append({"merged_index": i, "point": ChanPoint(bar.high_index, bar.high, "top")})
        elif bar.low < prev_bar.low and bar.low < next_bar.low:
            fractals.append({"merged_index": i, "point": ChanPoint(bar.low_index, bar.low, "bottom")})
    return fractals


def _more_extreme(a: ChanPoint, b: ChanPoint) -> bool:
    """b 是否比同类分型 a 更极端。"""
    return b.price > a.price if a.kind == "top" else b.price < a.price


def _snap_to_extremes(
    points: List[ChanPoint], highs: Sequence[float], lows: Sequence[float], max_rounds: int = 5
) -> List[ChanPoint]:
    """把每个端点校正到相邻两个反向端点之间的真实极值 K 线上。

    分型过滤（间隔、包含处理、撤销端点）可能让区间内留下比端点更极端的 K 线，
    这里迭代校正，保证每一笔的终点都是该笔区间内的最高/最低点。
    """
    snapped = list(points)
    for _ in range(max_rounds):
        changed = False
        for i, point in enumerate(snapped):
            left = snapped[i - 1].index if i > 0 else point.index
            right = snapped[i + 1].index if i + 1 < len(snapped) else point.index
            if point.kind == "top":
                best = max(range(left, right + 1), key=lambda k: (highs[k], -abs(k - point.index)))
                price = float(highs[best])
            else:
                best = min(range(left, right + 1), key=lambda k: (lows[k], abs(k - point.index)))
                price = float(lows[best])
            if best != point.index:
                snapped[i] = ChanPoint(best, price, point.kind)
                changed = True
        if not changed:
            break
    # 校正后若出现端点重合或方向失效，丢弃对应端点
    cleaned: List[ChanPoint] = []
    for point in snapped:
        if cleaned and point.index <= cleaned[-1].index:
            continue
        if cleaned and point.kind == cleaned[-1].kind:
            if _more_extreme(cleaned[-1], point):
                cleaned[-1] = point
            continue
        cleaned.append(point)
    return cleaned


def find_bis(highs: Sequence[float], lows: Sequence[float]) -> List[ChanPoint]:
    """返回笔的端点序列（顶底交替）。"""
    fractals = find_fractals(highs, lows)
    points: List[ChanPoint] = []
    merged_indexes: List[int] = []
    for item in fractals:
        point: ChanPoint = item["point"]  # type: ignore[assignment]
        merged_index: int = item["merged_index"]  # type: ignore[assignment]
        if not points:
            points.append(point)
            merged_indexes.append(merged_index)
            continue
        last = points[-1]
        if point.kind == last.kind:
            if _more_extreme(last, point):
                points[-1] = point
                merged_indexes[-1] = merged_index
            continue
        valid_direction = point.price > last.price if point.kind == "top" else point.price < last.price
        if point.kind == "top":
            is_range_extreme = max(highs[last.index:point.index + 1]) <= point.price
        else:
            is_range_extreme = min(lows[last.index:point.index + 1]) >= point.price
        if merged_index - merged_indexes[-1] < MIN_BI_BAR_GAP or not valid_direction or not is_range_extreme:
            # 不能成笔，但若比上一个同类端点更极端，说明上一笔未完成：
            # 撤销最后一个端点，并把同类端点更新为该分型。
            if len(points) >= 2 and _more_extreme(points[-2], point):
                points.pop()
                merged_indexes.pop()
                points[-1] = point
                merged_indexes[-1] = merged_index
            continue
        points.append(point)
        merged_indexes.append(merged_index)
    points = _snap_to_extremes(points, highs, lows)
    return points if len(points) >= 2 else []


def find_segments(bi_points: Sequence[ChanPoint]) -> List[ChanPoint]:
    """由笔端点序列划分线段，返回线段端点序列。"""
    n = len(bi_points)
    if n < MIN_SEGMENT_BI + 1:
        return []

    def beyond(a: ChanPoint, b: ChanPoint, upward: bool) -> bool:
        """b 是否在 upward 方向上超过 a（向上为更高，向下为更低）。"""
        return b.price > a.price if upward else b.price < a.price

    points: List[int] = [0]
    start = 0
    upward = bi_points[1].price > bi_points[0].price
    while start < n - 1:
        extreme = start + 1
        end = None
        restarted = False
        j = extreme + 1
        while j < n:
            point = bi_points[j]
            same_kind = point.kind == ("top" if upward else "bottom")
            if same_kind:
                if beyond(bi_points[extreme], point, upward):
                    extreme = j
            else:
                if beyond(point, bi_points[start], upward):
                    # 反向端点越过本线段起点：上一条线段尚未结束，延伸到该点；
                    # 序列首段则把起点挪到该点。之后从新起点按原方向重新扫描。
                    points[-1] = j
                    start = j
                    restarted = True
                    break
                # 极值前一笔的起点（与极值方向相反的端点）作为破坏参照
                reference = bi_points[extreme - 1]
                broken = beyond(point, reference, not upward)
                if broken and extreme - start >= MIN_SEGMENT_BI:
                    end = extreme
                    break
            j += 1
        if restarted:
            continue
        if end is None:
            # 序列开头：极值落在前一两笔且整段数据再未超越，只要之后已有三笔以上
            # 反向走势，就在极值处结束首段，避免整段数据划不出线段。
            if len(points) == 1 and extreme - start < MIN_SEGMENT_BI and n - 1 - extreme >= MIN_SEGMENT_BI:
                end = extreme
            else:
                break
        points.append(end)
        start = end
        upward = not upward
    if len(points) < 2:
        return []
    # 与笔相同：把线段端点校正到相邻两个反向端点之间最极端的同类笔端点
    for _ in range(5):
        changed = False
        for k, idx in enumerate(points):
            left = points[k - 1] if k > 0 else idx
            right = points[k + 1] if k + 1 < len(points) else idx
            kind = bi_points[idx].kind
            candidates = [i for i in range(left, right + 1) if bi_points[i].kind == kind]
            best = max(candidates, key=lambda i: bi_points[i].price) if kind == "top" else min(
                candidates, key=lambda i: bi_points[i].price
            )
            if best != idx:
                points[k] = best
                changed = True
        if not changed:
            break
    return [bi_points[i] for i in points]


@dataclass(frozen=True)
class ChanPivot:
    """笔中枢。start/end 为原始 K 线序号，first_bi/last_bi 为笔序号（第 k 笔连接端点 k 与 k+1）。"""

    start_index: int
    end_index: int
    zg: float
    zd: float
    gg: float
    dd: float
    first_bi: int
    last_bi: int
    confirmed: bool

    def to_dict(self) -> Dict[str, object]:
        return {
            "start_index": self.start_index,
            "end_index": self.end_index,
            "zg": self.zg,
            "zd": self.zd,
            "gg": self.gg,
            "dd": self.dd,
            "confirmed": self.confirmed,
        }


@dataclass(frozen=True)
class ChanBuyPoint:
    """买点，kind 为 buy1/buy2/buy3，index 为原始 K 线序号。"""

    index: int
    price: float
    kind: str

    def to_dict(self) -> Dict[str, object]:
        return {"index": self.index, "price": self.price, "kind": self.kind}


def _bi_range(bi_points: Sequence[ChanPoint], k: int) -> tuple:
    a, b = bi_points[k].price, bi_points[k + 1].price
    return max(a, b), min(a, b)


def _bi_is_down(bi_points: Sequence[ChanPoint], k: int) -> bool:
    return bi_points[k + 1].kind == "bottom"


def find_pivots(bi_points: Sequence[ChanPoint], last_bar_index: Optional[int] = None) -> List[ChanPivot]:
    """由笔端点序列划分笔中枢。last_bar_index 用于把未结束的中枢画到最后一根 K 线。"""
    bi_count = len(bi_points) - 1
    pivots: List[ChanPivot] = []
    # 第 0 笔留作首个中枢的进入笔
    i = 1
    while i + 2 < bi_count:
        ranges = [_bi_range(bi_points, k) for k in range(i, i + 3)]
        zg = min(h for h, _ in ranges)
        zd = max(lo for _, lo in ranges)
        if zg <= zd:
            i += 1
            continue
        gg = max(h for h, _ in ranges)
        dd = min(lo for _, lo in ranges)
        last = i + 2
        confirmed = False
        departing = False
        k = last + 1
        while k < bi_count:
            k_high, k_low = _bi_range(bi_points, k)
            if zd <= bi_points[k + 1].price <= zg:
                # 终点仍在中枢区间内：中枢内震荡
                gg, dd = max(gg, k_high), min(dd, k_low)
                last = k
                k += 1
                continue
            # 第 k 笔终点离开中枢区间；尚无回抽笔时中枢未结束，但不再向右延伸
            if k + 1 >= bi_count:
                departing = True
                break
            back_high, back_low = _bi_range(bi_points, k + 1)
            if back_low < zg and back_high > zd:
                gg, dd = max(gg, k_high, back_high), min(dd, k_low, back_low)
                last = k + 1
                k += 2
                continue
            confirmed = True
            break
        end_index = bi_points[last + 1].index
        if not confirmed and not departing and last_bar_index is not None:
            end_index = max(end_index, last_bar_index)
        pivots.append(
            ChanPivot(
                start_index=bi_points[i].index,
                end_index=end_index,
                zg=zg,
                zd=zd,
                gg=gg,
                dd=dd,
                first_bi=i,
                last_bi=last,
                confirmed=confirmed,
            )
        )
        # 离开笔作为下一个中枢的进入笔，从回抽笔开始找
        i = last + 2
    return pivots


def compute_macd(closes: Sequence[float]) -> Dict[str, List[float]]:
    """标准 MACD(12, 26, 9)：DIF、DEA 与柱（2 * (DIF - DEA)），与输入逐根对齐。"""
    dif_list: List[float] = []
    dea_list: List[float] = []
    hist: List[float] = []
    ema12 = ema26 = dea = None
    for close in closes:
        close = float(close)
        ema12 = close if ema12 is None else ema12 + (close - ema12) * 2 / 13
        ema26 = close if ema26 is None else ema26 + (close - ema26) * 2 / 27
        dif = ema12 - ema26
        dea = dif if dea is None else dea + (dif - dea) * 2 / 10
        dif_list.append(dif)
        dea_list.append(dea)
        hist.append(2 * (dif - dea))
    return {"dif": dif_list, "dea": dea_list, "hist": hist}


def _macd_histogram(closes: Sequence[float]) -> List[float]:
    return compute_macd(closes)["hist"]


def _bi_macd_area(bi_points: Sequence[ChanPoint], k: int, hist: Sequence[float]) -> float:
    """第 k 笔区间内与笔方向同号的 MACD 柱面积（绝对值之和）。"""
    start, end = bi_points[k].index, bi_points[k + 1].index
    down = _bi_is_down(bi_points, k)
    return sum(abs(v) for v in hist[start:end + 1] if (v < 0 if down else v > 0))


def find_buy_points(
    bi_points: Sequence[ChanPoint], pivots: Sequence[ChanPivot], closes: Sequence[float]
) -> List[ChanBuyPoint]:
    """按中枢与 MACD 背驰判定一买、二买、三买（简化规则见模块说明）。"""
    bi_count = len(bi_points) - 1
    hist = _macd_histogram(closes)
    found: Dict[int, ChanBuyPoint] = {}

    def add(point_index: int, kind: str) -> None:
        point = bi_points[point_index]
        # 同一端点同时满足多种买点时保留序号更小的类别
        if point.index in found and found[point.index].kind <= kind:
            return
        found[point.index] = ChanBuyPoint(point.index, point.price, kind)

    for pivot in pivots:
        entry, departure = pivot.first_bi - 1, pivot.last_bi + 1
        if departure >= bi_count:
            continue
        if entry >= 0 and _bi_is_down(bi_points, entry) and _bi_is_down(bi_points, departure):
            dep_low = bi_points[departure + 1].price
            if dep_low < pivot.dd and _bi_macd_area(bi_points, departure, hist) < _bi_macd_area(
                bi_points, entry, hist
            ):
                add(departure + 1, "buy1")
                # 二买：一买之后下一个底分型端点不破一买低点
                second = departure + 3
                if second < len(bi_points) and bi_points[second].price > dep_low:
                    add(second, "buy2")
        if not _bi_is_down(bi_points, departure) and departure + 2 < len(bi_points):
            pullback_low = bi_points[departure + 2].price
            if bi_points[departure + 1].price > pivot.zg and pullback_low > pivot.zg:
                add(departure + 2, "buy3")
    return sorted(found.values(), key=lambda p: p.index)


def analyze_chan(
    highs: Sequence[float], lows: Sequence[float], closes: Optional[Sequence[float]] = None
) -> Dict[str, List[Dict[str, object]]]:
    """计算笔、线段、中枢与买点，返回可序列化结果。closes 缺省时用高低点中值代替。"""
    if closes is None:
        closes = [(float(h) + float(lo)) / 2 for h, lo in zip(highs, lows)]
    bis = find_bis(highs, lows)
    segments = find_segments(bis)
    pivots = find_pivots(bis, last_bar_index=len(highs) - 1 if len(highs) else None)
    buy_points = find_buy_points(bis, pivots, closes)
    return {
        "bi": [p.to_dict() for p in bis],
        "segments": [p.to_dict() for p in segments],
        "pivots": [p.to_dict() for p in pivots],
        "buy_points": [p.to_dict() for p in buy_points],
    }
