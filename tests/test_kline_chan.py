# -*- coding: utf-8 -*-
"""K 线图数据服务、缠论结构计算与 /kline 接口测试。"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest
from fastapi.testclient import TestClient

import src.auth as auth
from api.app import create_app
from src.config import Config
from src.services.chan_analysis import (
    ChanPoint,
    analyze_chan,
    find_bis,
    find_buy_points,
    find_pivots,
    find_segments,
)
from src.services.kline_service import (
    KlineService,
    KlineUnsupportedError,
    aggregate_weekly,
    build_kline_payload,
    to_sina_minute_symbol,
)
from src.storage import DatabaseManager


def _zigzag(pivots, step=1.0):
    """按折点生成逐根 K 线（每根高低差 0.4），用于构造可预期的笔。"""
    closes = []
    for a, b in zip(pivots, pivots[1:]):
        n = int(abs(b - a) / step)
        direction = 1 if b > a else -1
        for k in range(n):
            closes.append(a + direction * step * k)
    closes.append(pivots[-1])
    highs = [c + 0.2 for c in closes]
    lows = [c - 0.2 for c in closes]
    return highs, lows


def _bars_frame(highs, lows, start="2025-01-01", freq="D"):
    dates = pd.date_range(start, periods=len(highs), freq=freq)
    closes = [(h + lo) / 2 for h, lo in zip(highs, lows)]
    return pd.DataFrame(
        {
            "date": dates,
            "open": closes,
            "high": highs,
            "low": lows,
            "close": closes,
            "volume": [1000.0] * len(highs),
        }
    )


# ---------------------------------------------------------------- chan


def test_find_bis_alternates_and_hits_pivots():
    highs, lows = _zigzag([10, 20, 12, 25, 15, 30])
    bis = find_bis(highs, lows)
    # 首尾两根 K 线无法构成分型，因此笔从 20 的顶开始、到 15 的底结束
    assert [(p.kind, round(p.price, 1)) for p in bis] == [
        ("top", 20.2),
        ("bottom", 11.8),
        ("top", 25.2),
        ("bottom", 14.8),
    ]
    assert all(a.kind != b.kind for a, b in zip(bis, bis[1:]))
    # 上升笔终点高于起点、下降笔终点低于起点
    for a, b in zip(bis, bis[1:]):
        assert (b.price > a.price) == (b.kind == "top")


def test_find_bis_skips_too_close_fractals():
    # 只有 3 根的小反弹不足以成笔
    highs, lows = _zigzag([10, 20, 18, 30, 15, 25])
    bis = find_bis(highs, lows)
    assert [(p.kind, round(p.price, 1)) for p in bis] == [("top", 30.2), ("bottom", 14.8)]


def test_find_bis_handles_short_or_flat_input():
    assert find_bis([], []) == []
    assert find_bis([1.0, 1.0, 1.0], [0.5, 0.5, 0.5]) == []


def _points(prices):
    kinds = ["bottom", "top"] if prices[1] > prices[0] else ["top", "bottom"]
    return [ChanPoint(index=i * 5, price=p, kind=kinds[i % 2]) for i, p in enumerate(prices)]


def test_find_segments_requires_break_of_last_bi_start():
    # 上升线段 10->30（三笔以上），之后跌破最后一笔起点 22 结束于 30；再下跌三笔后反转
    bi = _points([10, 18, 14, 24, 22, 30, 20, 26, 12, 16, 8, 20, 15, 28])
    segments = find_segments(bi)
    prices = [p.price for p in segments]
    assert prices[:3] == [10, 30, 8]
    for a, b in zip(segments, segments[1:]):
        assert a.kind != b.kind


def test_find_segments_allows_extreme_in_first_bis_at_series_start():
    # 开头一笔急涨就是最高点，后续反向走势超过三笔且跌破起点前参照
    bi = _points([10, 40, 30, 35, 25, 32, 20, 28, 15])
    segments = find_segments(bi)
    assert [p.price for p in segments][:2] == [10, 40]


def test_find_segments_too_few_bis():
    assert find_segments(_points([10, 20, 15])) == []


@pytest.mark.parametrize("seed", range(40))
def test_bi_and_segment_endpoints_are_range_extremes(seed):
    import numpy as np

    rng = np.random.default_rng(seed)
    closes = 100 * np.exp(np.cumsum(rng.normal(0, 0.02, 300)))
    highs = closes * (1 + np.abs(rng.normal(0, 0.01, 300)))
    lows = closes * (1 - np.abs(rng.normal(0, 0.01, 300)))
    bis = find_bis(highs, lows)
    segments = find_segments(bis)
    for points in (bis, segments):
        for a, b in zip(points, points[1:]):
            assert a.kind != b.kind and a.index < b.index
            top, bottom = (b, a) if b.kind == "top" else (a, b)
            assert top.price >= highs[a.index:b.index + 1].max() - 1e-9
            assert bottom.price <= lows[a.index:b.index + 1].min() + 1e-9


# ---------------------------------------------------------------- service


def _chan_points(spec):
    """spec: [(index, price, kind), ...] -> ChanPoint 列表。"""
    return [ChanPoint(i, float(p), k) for i, p, k in spec]


def _interp_closes(points, length):
    """在笔端点之间线性插值收盘价，用于构造 MACD。"""
    closes = [points[0].price] * length
    for a, b in zip(points, points[1:]):
        for i in range(a.index, b.index + 1):
            t = (i - a.index) / (b.index - a.index)
            closes[i] = a.price + (b.price - a.price) * t
    for i in range(points[-1].index, length):
        closes[i] = points[-1].price
    return closes


def test_find_pivots_overlap_extend_and_third_buy():
    bi = _chan_points([
        (0, 20, "top"), (5, 10, "bottom"), (10, 16, "top"), (15, 12, "bottom"),
        (20, 17, "top"), (25, 13, "bottom"), (30, 25, "top"), (35, 19, "bottom"),
    ])
    pivots = find_pivots(bi)
    assert len(pivots) == 1
    pivot = pivots[0]
    assert (pivot.zg, pivot.zd) == (16.0, 12.0)
    # 第 5 笔 13 -> 25 从区间内离开，方框止于它的起点
    assert (pivot.start_index, pivot.end_index) == (5, 25)
    assert (pivot.first_bi, pivot.last_bi) == (0, 5)

    buys = find_buy_points(bi, pivots, _interp_closes(bi, 40))
    assert buys == [{"index": 35, "price": 19.0, "type": 3}]


def test_find_pivots_requires_three_strokes():
    bi = _chan_points([(0, 10, "bottom"), (5, 14, "top"), (10, 13, "bottom")])
    assert find_pivots(bi) == []
    assert find_pivots([]) == []


def test_find_pivots_caps_extension_at_nine_strokes():
    # 12 笔在同一区间来回震荡：第一个中枢截断在九笔，剩下的笔另起中枢
    spec = [(i * 5, 20 if i % 2 == 0 else 10, "top" if i % 2 == 0 else "bottom") for i in range(13)]
    pivots = find_pivots(_chan_points(spec))
    assert len(pivots) == 2
    assert (pivots[0].first_bi, pivots[0].last_bi) == (0, 8)
    assert pivots[1].first_bi == 9


def _down_pivot_points(exit_bar):
    """从上方进入中枢、向下离开并创新低的结构；exit_bar 控制离开笔的长度（越长越缓）。"""
    return _chan_points([
        (0, 30, "top"), (10, 20, "bottom"), (15, 25, "top"), (20, 21, "bottom"),
        (25, 24, "top"), (exit_bar, 19, "bottom"), (exit_bar + 5, 20.5, "top"), (exit_bar + 10, 19.5, "bottom"),
    ])


def test_first_and_second_buy_on_divergence():
    bi = _down_pivot_points(exit_bar=70)
    pivots = find_pivots(bi)
    assert len(pivots) == 1 and (pivots[0].zg, pivots[0].zd) == (25.0, 21.0)
    buys = find_buy_points(bi, pivots, _interp_closes(bi, 90))
    assert buys == [
        {"index": 70, "price": 19.0, "type": 1},
        {"index": 80, "price": 19.5, "type": 2},
    ]


def test_no_first_buy_without_divergence():
    # 离开笔比进入笔更陡，MACD 绿柱面积更大，不构成背驰
    bi = _chan_points([
        (0, 26, "top"), (20, 20, "bottom"), (25, 25, "top"), (30, 21, "bottom"),
        (35, 24, "top"), (39, 8, "bottom"), (44, 10, "top"), (49, 9, "bottom"),
    ])
    pivots = find_pivots(bi)
    assert len(pivots) == 1
    assert find_buy_points(bi, pivots, _interp_closes(bi, 60)) == []


def test_first_buy_inside_extended_pivot_and_needs_rebound():
    # 新低后反弹回到中枢区间，中枢继续延伸；一买仍应在新低处识别
    bi = _chan_points([
        (0, 30, "top"), (10, 20, "bottom"), (15, 25, "top"), (20, 21, "bottom"),
        (25, 24, "top"), (70, 19, "bottom"), (75, 22, "top"), (80, 20, "bottom"), (85, 23, "top"),
    ])
    pivots = find_pivots(bi)
    assert len(pivots) == 1 and pivots[0].last_bi >= 6
    buys = find_buy_points(bi, pivots, _interp_closes(bi, 90))
    assert buys == [
        {"index": 70, "price": 19.0, "type": 1},
        {"index": 80, "price": 20.0, "type": 2},
    ]
    # 新低尚未出现反弹笔时不确认一买
    tail = bi[:6]
    assert find_buy_points(tail, find_pivots(tail), _interp_closes(tail, 90)) == []


@pytest.mark.parametrize("seed", range(20))
def test_pivots_and_buy_points_are_consistent(seed):
    import random

    rng = random.Random(seed)
    price, highs, lows, closes = 100.0, [], [], []
    for i in range(400):
        price *= 1 + rng.gauss(0, 0.015) + 0.01 * __import__("math").sin(i / 9)
        spread = abs(rng.gauss(0, 0.006)) * price
        highs.append(price + spread)
        lows.append(price - spread)
        closes.append(price)
    chan = analyze_chan(highs, lows, closes)
    bottoms = {(p["index"], p["price"]) for p in chan["bi"] if p["kind"] == "bottom"}
    for pivot in chan["pivots"]:
        assert pivot["zg"] > pivot["zd"]
        assert 0 <= pivot["start_index"] < pivot["end_index"] < len(highs)
    for buy in chan["buy_points"]:
        assert (buy["index"], buy["price"]) in bottoms
        assert buy["type"] in (1, 2, 3)
    starts = [p["start_index"] for p in chan["pivots"]]
    assert starts == sorted(starts)


def test_to_sina_minute_symbol():
    assert to_sina_minute_symbol("600519") == "sh600519"
    assert to_sina_minute_symbol("000001") == "sz000001"
    assert to_sina_minute_symbol("SH600519") == "sh600519"
    assert to_sina_minute_symbol("600519.SH") == "sh600519"
    assert to_sina_minute_symbol("sh000300") == "sh000300"
    assert to_sina_minute_symbol("HK00700") is None
    assert to_sina_minute_symbol("AAPL") is None


def test_aggregate_weekly_uses_last_trading_day():
    df = _bars_frame([2, 3, 4, 5, 6, 7, 8], [1, 1, 2, 2, 3, 3, 4], start="2026-09-21", freq="B")
    weekly = aggregate_weekly(df)
    assert len(weekly) == 2
    first = weekly.iloc[0]
    assert first["date"] == pd.Timestamp("2026-09-25")
    assert first["high"] == 6 and first["low"] == 1
    assert first["volume"] == 5000.0


def test_build_payload_ma_alignment_and_nan_handling():
    highs, lows = _zigzag([10, 20, 12, 25])
    df = _bars_frame(highs, lows)
    df.loc[3, "volume"] = float("nan")
    payload = build_kline_payload(df, period="daily", ma_windows=(5,))
    assert len(payload["moving_averages"]["5"]) == len(payload["bars"])
    assert payload["moving_averages"]["5"][:4] == [None] * 4
    assert payload["moving_averages"]["5"][4] is not None
    assert payload["bars"][3]["volume"] is None
    assert payload["bars"][0]["time"] == "2025-01-01"
    for point in payload["chan"]["bi"]:
        assert 0 <= point["index"] < len(payload["bars"])


class _FakeManager:
    def __init__(self, df):
        self.df = df
        self.calls = []

    def get_daily_data(self, code, days=30):
        self.calls.append((code, days))
        return self.df, "FakeFetcher"

    def get_stock_name(self, code):
        return "测试股"


def test_service_daily_and_weekly():
    highs, lows = _zigzag([10, 20, 12, 25, 15, 30])
    manager = _FakeManager(_bars_frame(highs, lows))
    service = KlineService(manager_factory=lambda: manager)
    daily = service.get_kline("600519", period="daily", days=200)
    assert daily["source"] == "FakeFetcher"
    assert daily["stock_name"] == "测试股"
    assert len(daily["bars"]) == len(highs)
    weekly = service.get_kline("600519", period="weekly", days=200)
    assert len(weekly["bars"]) < len(highs)
    assert manager.calls == [("600519", 200), ("600519", 1000)]


def test_service_minute_uses_sina_columns_and_rejects_non_a_share():
    raw = pd.DataFrame(
        {
            "day": ["2026-09-30 10:30:00", "2026-09-30 11:30:00", "2026-09-30 14:00:00"],
            "open": ["1.0", "1.1", "1.2"],
            "high": ["1.2", "1.3", "1.4"],
            "low": ["0.9", "1.0", "1.1"],
            "close": ["1.1", "1.2", "1.3"],
            "volume": ["100", "200", "300"],
        }
    )
    calls = []

    def fetch(symbol, period):
        calls.append((symbol, period))
        return raw

    service = KlineService(manager_factory=lambda: _FakeManager(pd.DataFrame()), minute_fetcher=fetch)
    payload = service.get_kline("600519", period="60m")
    assert calls == [("sh600519", "60")]
    assert payload["bars"][0]["time"] == "2026-09-30 10:30"
    assert payload["bars"][2]["close"] == 1.3

    with pytest.raises(KlineUnsupportedError):
        service.get_kline("HK00700", period="30m")
    with pytest.raises(KlineUnsupportedError):
        service.get_kline("600519", period="5m")


# ---------------------------------------------------------------- api


def _reset_auth_globals():
    auth._auth_enabled = None
    auth._session_secret = None
    auth._password_hash_salt = None
    auth._password_hash_stored = None
    auth._rate_limit = {}


def test_kline_endpoint_contract():
    highs, lows = _zigzag([10, 20, 12, 25, 15, 30])
    payload = KlineService(manager_factory=lambda: _FakeManager(_bars_frame(highs, lows))).get_kline("600519")
    _reset_auth_globals()
    with tempfile.TemporaryDirectory() as temp_dir:
        try:
            os.environ["DATABASE_PATH"] = str(Path(temp_dir) / "kline.db")
            os.environ["ADMIN_AUTH_ENABLED"] = "false"
            Config.reset_instance()
            DatabaseManager.reset_instance()
            client = TestClient(create_app(static_dir=Path(temp_dir) / "empty-static"))
            with patch("api.v1.endpoints.stocks.KlineService.get_kline", return_value=payload) as get_kline:
                ok = client.get("/api/v1/stocks/600519/kline", params={"period": "weekly", "days": 400})
            assert ok.status_code == 200, ok.text
            body = ok.json()
            assert body["period"] == "daily"
            assert set(body["moving_averages"]) == {"5", "20", "60"}
            assert body["chan"]["bi"]
            assert get_kline.call_args.kwargs == {"period": "weekly", "days": 400}

            bad_period = client.get("/api/v1/stocks/600519/kline", params={"period": "5m"})
            assert bad_period.status_code == 422

            with patch(
                "api.v1.endpoints.stocks.KlineService.get_kline",
                side_effect=KlineUnsupportedError("分钟级别 K 线目前仅支持 A 股"),
            ):
                unsupported = client.get("/api/v1/stocks/HK00700/kline", params={"period": "60m"})
            assert unsupported.status_code == 422
            assert "A 股" in json.dumps(unsupported.json(), ensure_ascii=False)

            with patch("api.v1.endpoints.stocks.KlineService.get_kline", side_effect=RuntimeError("boom")):
                failed = client.get("/api/v1/stocks/600519/kline")
            assert failed.status_code == 502
        finally:
            DatabaseManager.reset_instance()
            Config.reset_instance()
            os.environ.pop("DATABASE_PATH", None)
            os.environ.pop("ADMIN_AUTH_ENABLED", None)
            _reset_auth_globals()


def test_static_openapi_matches_kline_runtime_contract():
    static_spec = json.loads(
        (Path(__file__).resolve().parents[1] / "docs" / "architecture" / "api_spec.json").read_text(encoding="utf-8")
    )
    runtime_spec = create_app().openapi()
    api_path = "/api/v1/stocks/{stock_code}/kline"
    assert static_spec["paths"][api_path] == runtime_spec["paths"][api_path]
    for name in ("StockKlineResponse", "ChartBar", "ChanPointItem", "ChanStructure", "ChanPivotItem", "ChanBuyPointItem"):
        assert static_spec["components"]["schemas"][name] == runtime_spec["components"]["schemas"][name]
