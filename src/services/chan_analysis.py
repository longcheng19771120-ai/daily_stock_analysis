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
- 中枢（箱体）：以笔为次级别走势，连续三笔价格区间的重叠部分
  [ZD, ZG]（ZG 为三笔高点的最小值，ZD 为三笔低点的最大值）且 ZG > ZD 时
  形成中枢；之后的笔只要与 [ZD, ZG] 有重叠就延伸中枢，出现完全不重叠的
  一笔时中枢结束，从下一笔开始寻找新中枢。中枢延伸到九笔时视为升级为
  更大级别中枢，本级别在此截断，避免震荡行情里整段只画出一个箱体。
- 买点（简化版，仅供参考）：
  - 一买：中枢由上方向下进入，之后（中枢内或离开中枢时）某一向下笔跌破 ZD
    并创出低于此前所有低点的新低，且该笔的 MACD 绿柱面积小于进入笔（背驰）。
    MACD 柱相对价格滞后，两笔的面积都统计到下一个笔端点为止；新低之后
    必须已出现反弹笔，确认该低点成立。每个中枢最多一个一买。
  - 二买：一买之后的第一个回调低点，且不低于一买。
  - 三买：向上离开中枢后，回调的一笔低点仍高于 ZG。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence

MIN_BI_BAR_GAP = 4
MIN_SEGMENT_BI = 3
# 中枢延伸到九笔即视为升级为更大级别中枢，本级别在此截断
MAX_PIVOT_BI = 9


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
    """中枢。start_index/end_index 为原始 K 线序号；first_bi/last_bi 为构成中枢的笔序号。"""

    start_index: int
    end_index: int
    zg: float
    zd: float
    first_bi: int
    last_bi: int

    def to_dict(self) -> Dict[str, object]:
        return {"start_index": self.start_index, "end_index": self.end_index, "zg": self.zg, "zd": self.zd}


def find_pivots(bi_points: Sequence[ChanPoint]) -> List[ChanPivot]:
    """由笔端点序列识别中枢。第 k 笔连接 bi_points[k] 与 bi_points[k + 1]。"""
    stroke_count = len(bi_points) - 1
    if stroke_count < 3:
        return []
    highs = [max(bi_points[k].price, bi_points[k + 1].price) for k in range(stroke_count)]
    lows = [min(bi_points[k].price, bi_points[k + 1].price) for k in range(stroke_count)]

    pivots: List[ChanPivot] = []
    k = 0
    while k + 2 < stroke_count:
        zg = min(highs[k:k + 3])
        zd = max(lows[k:k + 3])
        if zg <= zd:
            k += 1
            continue
        last = k + 2
        while (
            last + 1 < stroke_count
            and last + 1 - k < MAX_PIVOT_BI
            and lows[last + 1] <= zg
            and highs[last + 1] >= zd
        ):
            last += 1
        # 方框从第一笔进入区间处开始；若最后一笔终点已离开区间，说明离开从该笔起点开始
        start_index = bi_points[k + 1].index
        exit_point = bi_points[last + 1]
        end_index = exit_point.index if zd <= exit_point.price <= zg else bi_points[last].index
        if end_index > start_index:
            pivots.append(ChanPivot(start_index, end_index, zg, zd, k, last))
        k = last + 1
    return pivots


def _macd_histogram(closes: Sequence[float]) -> List[float]:
    """MACD 柱（DIF - DEA），参数 12/26/9。"""
    def ema(values: Sequence[float], span: int) -> List[float]:
        alpha = 2.0 / (span + 1)
        out: List[float] = []
        for v in values:
            out.append(float(v) if not out else alpha * float(v) + (1 - alpha) * out[-1])
        return out

    fast, slow = ema(closes, 12), ema(closes, 26)
    dif = [f - s for f, s in zip(fast, slow)]
    dea = ema(dif, 9)
    return [d - e for d, e in zip(dif, dea)]


def _down_area(hist: Sequence[float], start: int, end: int) -> float:
    """区间内 MACD 绿柱面积（取绝对值）。"""
    return -sum(v for v in hist[start:end + 1] if v < 0)


def find_buy_points(
    bi_points: Sequence[ChanPoint],
    pivots: Sequence[ChanPivot],
    closes: Sequence[float],
) -> List[Dict[str, object]]:
    """识别一、二、三类买点，返回 {index, price, type} 列表（按 K 线序号升序）。"""
    if not pivots or not closes:
        return []
    hist = _macd_histogram(closes)
    found: Dict[tuple, Dict[str, object]] = {}

    def add(point: ChanPoint, kind: int) -> None:
        found[(point.index, kind)] = {"index": point.index, "price": point.price, "type": kind}

    for pivot in pivots:
        first, last = pivot.first_bi, pivot.last_bi
        exit_point = bi_points[last + 1]

        # 一买：从上方进入（第一笔向下且起点在 ZG 之上），之后向下笔跌破 ZD 创新低且 MACD 面积背驰
        enter_start, enter_end = bi_points[first], bi_points[first + 1]
        if enter_end.kind == "bottom" and enter_start.price > pivot.zg:
            # MACD 柱相对价格滞后，面积统计到下一个笔端点为止
            enter_area = _down_area(hist, enter_start.index, bi_points[first + 2].index)
            lowest = enter_end.price
            # 候选低点为中枢内各笔及离开笔的终点；要求其后已有反弹笔确认
            for j in range(first + 3, min(last + 1, len(bi_points) - 2) + 1, 2):
                point = bi_points[j]
                if point.kind != "bottom" or point.price >= lowest:
                    continue
                lowest = point.price
                if point.price >= pivot.zd:
                    continue
                exit_area = _down_area(hist, bi_points[j - 1].index, bi_points[j + 1].index)
                if 0 < enter_area and exit_area < enter_area:
                    add(point, 1)
                    # 二买：一买之后的第一个回调低点不破一买
                    if j + 2 < len(bi_points) and bi_points[j + 2].price > point.price:
                        add(bi_points[j + 2], 2)
                    break

        # 三买：向上离开中枢后，回调低点仍在 ZG 之上
        if exit_point.kind == "top" and exit_point.price > pivot.zg and last + 2 < len(bi_points):
            pullback = bi_points[last + 2]
            if pullback.kind == "bottom" and pullback.price > pivot.zg:
                add(pullback, 3)

    return sorted(found.values(), key=lambda item: (item["index"], item["type"]))


def analyze_chan(
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Optional[Sequence[float]] = None,
) -> Dict[str, List[Dict[str, object]]]:
    """计算笔、线段、中枢与买点，返回可序列化结果。

    closes 用于计算一买的 MACD 背驰；不传时以 (high + low) / 2 近似。
    """
    bis = find_bis(highs, lows)
    segments = find_segments(bis)
    pivots = find_pivots(bis)
    if closes is None:
        closes = [(float(h) + float(l)) / 2 for h, l in zip(highs, lows)]
    return {
        "bi": [p.to_dict() for p in bis],
        "segments": [p.to_dict() for p in segments],
        "pivots": [p.to_dict() for p in pivots],
        "buy_points": find_buy_points(bis, pivots, closes),
    }
