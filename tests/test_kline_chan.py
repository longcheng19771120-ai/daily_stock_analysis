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
    compute_macd,
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


def _points_with_closes(spec):
    """spec 为 [(price, bars_to_next), ...]，返回笔端点（顶底交替）和逐根线性插值的收盘价。"""
    points, closes = [], []
    index = 0
    for k, (price, bars) in enumerate(spec):
        if k + 1 < len(spec):
            nxt = spec[k + 1][0]
            kind = "top" if nxt < price else "bottom"
        else:
            kind = "top" if price > spec[k - 1][0] else "bottom"
        points.append(ChanPoint(index, float(price), kind))
        if k + 1 < len(spec):
            nxt = spec[k + 1][0]
            for j in range(bars):
                closes.append(price + (nxt - price) * j / bars)
            index += bars
    closes.append(float(spec[-1][0]))
    return points, closes


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
    for name in (
        "StockKlineResponse",
        "ChartBar",
        "ChanPointItem",
        "ChanStructure",
        "ChanPivotItem",
        "ChanBuyPointItem",
        "MacdSeries",
    ):
        assert static_spec["components"]["schemas"][name] == runtime_spec["components"]["schemas"][name]


# ---------------------------------------------------------------- pivots / buy points


def test_find_pivots_overlap_and_third_buy():
    # 第 0 笔为进入笔；笔 1-3 重叠 [12, 18]；向上离开到 25，回抽 19 不回中枢 -> 三买
    points, closes = _points_with_closes([(5, 5), (20, 5), (10, 5), (18, 5), (12, 5), (25, 5), (19, 5), (28, 5)])
    pivots = find_pivots(points, last_bar_index=len(closes) - 1)
    assert len(pivots) == 1
    pivot = pivots[0]
    assert (pivot.zd, pivot.zg) == (12.0, 18.0)
    assert pivot.confirmed is True
    assert pivot.start_index == points[1].index
    assert pivot.end_index == points[4].index
    buys = find_buy_points(points, pivots, closes)
    assert [(b.kind, b.price) for b in buys] == [("buy3", 19.0)]


def test_find_pivots_extends_when_pullback_returns_and_stays_open_at_end():
    # 离开到 22 后回抽到 14 回到中枢 -> 延伸；数据末尾没有新的离开+回抽 -> 未结束，画到最后一根
    points, closes = _points_with_closes([(5, 5), (20, 5), (10, 5), (18, 5), (12, 5), (22, 5), (14, 5), (17, 5)])
    pivots = find_pivots(points, last_bar_index=len(closes) - 1)
    assert len(pivots) == 1
    assert pivots[0].confirmed is False
    assert pivots[0].end_index == len(closes) - 1
    assert pivots[0].gg == 22.0
    assert find_buy_points(points, pivots, closes) == []


def test_first_and_second_buy_on_down_divergence():
    # 进入笔 40->20 慢跌、面积大；离开笔 25->18 创新低但快速且幅度小 -> 一买；
    # 反弹到 21 不回中枢，随后低点 19 不破 18 -> 二买
    spec = [(40, 40), (20, 6), (26, 6), (22, 6), (25, 4), (18, 6), (21, 6), (19, 6), (21, 4)]
    points, closes = _points_with_closes(spec)
    pivots = find_pivots(points, last_bar_index=len(closes) - 1)
    assert pivots and (pivots[0].zd, pivots[0].zg) == (22.0, 25.0)
    buys = find_buy_points(points, pivots, closes)
    assert [(b.kind, b.price) for b in buys] == [("buy1", 18.0), ("buy2", 19.0)]


def test_no_first_buy_without_divergence():
    # 离开笔跌得比进入笔更猛更久：没有背驰，不出一买
    spec = [(30, 4), (20, 6), (26, 6), (22, 6), (25, 40), (5, 6), (9, 6)]
    points, closes = _points_with_closes(spec)
    pivots = find_pivots(points, last_bar_index=len(closes) - 1)
    assert pivots
    assert all(b.kind != "buy1" for b in find_buy_points(points, pivots, closes))


def test_analyze_chan_includes_pivots_and_buy_points():
    highs, lows = _zigzag([10, 30, 20, 26, 22, 25, 18, 23, 19, 24])
    result = analyze_chan(highs, lows)
    assert set(result) == {"bi", "segments", "pivots", "buy_points"}
    for pivot in result["pivots"]:
        assert pivot["zg"] > pivot["zd"]
        assert 0 <= pivot["start_index"] < pivot["end_index"] < len(highs)
    for buy in result["buy_points"]:
        assert buy["kind"] in {"buy1", "buy2", "buy3"}
        assert lows[buy["index"]] == pytest.approx(buy["price"])


def test_open_pivot_stops_at_departure_while_waiting_for_pullback():
    # 最后一笔跌出中枢、尚无回抽：中枢未确认，但箱体停在离开笔起点，不延伸到最后一根
    points, closes = _points_with_closes([(5, 5), (20, 5), (10, 5), (18, 5), (12, 5), (16, 5), (3, 5)])
    pivots = find_pivots(points, last_bar_index=len(closes) - 1)
    assert len(pivots) == 1
    assert pivots[0].confirmed is False
    assert pivots[0].end_index == points[5].index


def test_compute_macd_matches_reference_and_payload_alignment():
    closes = [10.0, 10.5, 11.0, 10.8, 11.2, 11.5]
    macd = compute_macd(closes)
    assert len(macd["dif"]) == len(macd["dea"]) == len(macd["hist"]) == len(closes)
    assert macd["dif"][0] == 0 and macd["hist"][0] == 0
    # 第二根：EMA12 = 10 + 0.5 * 2/13，EMA26 = 10 + 0.5 * 2/27，DEA = DIF * 0.2
    dif = 0.5 * 2 / 13 - 0.5 * 2 / 27
    assert macd["dif"][1] == pytest.approx(dif)
    assert macd["dea"][1] == pytest.approx(dif * 0.2)
    assert macd["hist"][1] == pytest.approx(2 * (dif - dif * 0.2))

    highs, lows = _zigzag([10, 20, 12, 25])
    payload = build_kline_payload(_bars_frame(highs, lows), period="daily")
    assert set(payload["macd"]) == {"dif", "dea", "hist"}
    assert all(len(values) == len(payload["bars"]) for values in payload["macd"].values())
