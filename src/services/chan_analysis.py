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
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Sequence

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


def analyze_chan(highs: Sequence[float], lows: Sequence[float]) -> Dict[str, List[Dict[str, object]]]:
    """计算笔与线段，返回可序列化结果。"""
    bis = find_bis(highs, lows)
    segments = find_segments(bis)
    return {
        "bi": [p.to_dict() for p in bis],
        "segments": [p.to_dict() for p in segments],
    }
