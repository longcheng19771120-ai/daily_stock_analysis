# -*- coding: utf-8 -*-
"""
K 线图数据服务：多周期 K 线 + 均线 + 缠论笔/线段。

- daily / weekly：复用 DataFetcherManager 的日线多数据源回退，周线由日线聚合。
- 60m / 30m：A 股分钟线，来自 AkShare 新浪接口（stock_zh_a_minute，前复权）；
  港股、美股等暂不支持分钟级别。
"""

from __future__ import annotations

import logging
import math
import re
from typing import Any, Callable, Dict, List, Optional, Sequence

import pandas as pd

from src.services.chan_analysis import analyze_chan

logger = logging.getLogger(__name__)

DAILY_PERIODS = ("daily", "weekly")
MINUTE_PERIODS = {"60m": "60", "30m": "30"}
SUPPORTED_PERIODS = DAILY_PERIODS + tuple(MINUTE_PERIODS)
DEFAULT_MA_WINDOWS = (5, 20, 60)
MAX_BARS = 2000

_A_SHARE_PATTERN = re.compile(r"^(?:(sh|sz|bj)\.?)?(\d{6})(?:\.(sh|sz|bj|ss))?$", re.IGNORECASE)


class KlineUnsupportedError(ValueError):
    """请求的代码/周期组合不受支持。"""


def to_sina_minute_symbol(stock_code: str) -> Optional[str]:
    """把 A 股代码转换成新浪分钟线 symbol；非 A 股返回 None。"""
    match = _A_SHARE_PATTERN.match((stock_code or "").strip())
    if not match:
        return None
    from data_provider.akshare_fetcher import _to_sina_tx_symbol

    prefix = (match.group(1) or "").lower()
    if prefix:
        return f"{prefix}{match.group(2)}"
    return _to_sina_tx_symbol(match.group(2))


def _fetch_sina_minute(symbol: str, period: str) -> pd.DataFrame:
    import akshare as ak

    return ak.stock_zh_a_minute(symbol=symbol, period=period, adjust="qfq")


def aggregate_weekly(df: pd.DataFrame) -> pd.DataFrame:
    """把日线聚合为周线，周线日期取该周最后一个交易日。"""
    if df.empty:
        return df
    work = df.copy()
    work["date"] = pd.to_datetime(work["date"])
    work = work.sort_values("date")
    iso = work["date"].dt.isocalendar()
    work["_week"] = iso["year"].astype(int) * 100 + iso["week"].astype(int)
    agg: Dict[str, Any] = {
        "date": "last",
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
    }
    if "volume" in work:
        agg["volume"] = "sum"
    if "amount" in work:
        agg["amount"] = "sum"
    return work.groupby("_week", sort=True).agg(agg).reset_index(drop=True)


def _clean_bars(df: pd.DataFrame) -> pd.DataFrame:
    work = df.copy()
    for col in ("open", "high", "low", "close", "volume", "amount"):
        if col in work:
            work[col] = pd.to_numeric(work[col], errors="coerce")
    work["date"] = pd.to_datetime(work["date"], errors="coerce")
    work = work.dropna(subset=["date", "open", "high", "low", "close"])
    work = work.sort_values("date").drop_duplicates(subset=["date"], keep="last")
    return work.tail(MAX_BARS).reset_index(drop=True)


def _finite_or_none(value: Any) -> Optional[float]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def build_kline_payload(
    df: pd.DataFrame,
    *,
    period: str,
    ma_windows: Sequence[int] = DEFAULT_MA_WINDOWS,
) -> Dict[str, Any]:
    """把标准化 K 线 DataFrame 转成接口载荷（K 线、均线、缠论结构）。"""
    bars_df = _clean_bars(df)
    intraday = period in MINUTE_PERIODS
    time_format = "%Y-%m-%d %H:%M" if intraday else "%Y-%m-%d"

    bars: List[Dict[str, Any]] = []
    for row in bars_df.itertuples(index=False):
        bars.append(
            {
                "time": row.date.strftime(time_format),
                "open": float(row.open),
                "high": float(row.high),
                "low": float(row.low),
                "close": float(row.close),
                "volume": _finite_or_none(getattr(row, "volume", None)),
                "amount": _finite_or_none(getattr(row, "amount", None)),
            }
        )

    moving_averages: Dict[str, List[Optional[float]]] = {}
    for window in ma_windows:
        series = bars_df["close"].rolling(window=window, min_periods=window).mean()
        moving_averages[str(window)] = [
            round(v, 4) if v is not None else None for v in (_finite_or_none(x) for x in series)
        ]

    chan = (
        analyze_chan(bars_df["high"].tolist(), bars_df["low"].tolist(), bars_df["close"].tolist())
        if bars
        else {"bi": [], "segments": [], "pivots": [], "buy_points": []}
    )
    return {"bars": bars, "moving_averages": moving_averages, "chan": chan}


class KlineService:
    """取数并生成 K 线图载荷。取数函数可注入，便于测试。"""

    def __init__(
        self,
        manager_factory: Optional[Callable[[], Any]] = None,
        minute_fetcher: Optional[Callable[[str, str], pd.DataFrame]] = None,
    ) -> None:
        self._manager_factory = manager_factory
        self._minute_fetcher = minute_fetcher or _fetch_sina_minute

    def _manager(self) -> Any:
        if self._manager_factory is not None:
            return self._manager_factory()
        from data_provider.base import DataFetcherManager

        return DataFetcherManager()

    def get_kline(
        self,
        stock_code: str,
        *,
        period: str = "daily",
        days: int = 365,
        ma_windows: Sequence[int] = DEFAULT_MA_WINDOWS,
    ) -> Dict[str, Any]:
        if period not in SUPPORTED_PERIODS:
            raise KlineUnsupportedError(f"不支持的周期 {period}，可选：{', '.join(SUPPORTED_PERIODS)}")

        source: Optional[str] = None
        stock_name: Optional[str] = None
        manager = self._manager()

        if period in MINUTE_PERIODS:
            symbol = to_sina_minute_symbol(stock_code)
            if symbol is None:
                raise KlineUnsupportedError("分钟级别 K 线目前仅支持 A 股")
            raw = self._minute_fetcher(symbol, MINUTE_PERIODS[period])
            if raw is None or raw.empty:
                df = pd.DataFrame(columns=["date", "open", "high", "low", "close", "volume"])
            else:
                df = raw.rename(columns={"day": "date"})
            source = "AkshareSinaMinute"
        else:
            fetch_days = days * 5 if period == "weekly" else days
            df, source = manager.get_daily_data(stock_code, days=fetch_days)
            if df is None:
                df = pd.DataFrame(columns=["date", "open", "high", "low", "close", "volume"])
            if period == "weekly":
                df = aggregate_weekly(df)

        try:
            stock_name = manager.get_stock_name(stock_code)
        except Exception as exc:  # 名称只用于展示，失败不影响 K 线
            logger.debug("获取 %s 名称失败: %s", stock_code, exc)

        payload = build_kline_payload(df, period=period, ma_windows=ma_windows)
        payload.update(
            {
                "stock_code": stock_code,
                "stock_name": stock_name,
                "period": period,
                "source": source,
            }
        )
        return payload
