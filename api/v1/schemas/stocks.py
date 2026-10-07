# -*- coding: utf-8 -*-
"""
===================================
股票数据相关模型
===================================

职责：
1. 定义股票实时行情模型
2. 定义历史 K 线数据模型
"""

from typing import Dict, Literal, Optional, List

from pydantic import BaseModel, ConfigDict, Field

from api.v1.schemas.history import HistoryItem
from api.v1.schemas.intelligence import IntelligenceItem
from api.v1.schemas.research_artifact import ResearchArtifact

StockProfileStatus = Literal["fresh", "partial", "unavailable"]


class StockQuote(BaseModel):
    """股票实时行情"""
    
    stock_code: str = Field(..., description="股票代码")
    stock_name: Optional[str] = Field(None, description="股票名称")
    current_price: float = Field(..., description="当前价格")
    change: Optional[float] = Field(None, description="涨跌额")
    change_percent: Optional[float] = Field(None, description="涨跌幅 (%)")
    open: Optional[float] = Field(None, description="开盘价")
    high: Optional[float] = Field(None, description="最高价")
    low: Optional[float] = Field(None, description="最低价")
    prev_close: Optional[float] = Field(None, description="昨收价")
    volume: Optional[float] = Field(None, description="成交量（股）")
    amount: Optional[float] = Field(None, description="成交额（元）")
    update_time: Optional[str] = Field(None, description="更新时间")
    
    model_config = ConfigDict(json_schema_extra={
        "example": {
            "stock_code": "600519",
            "stock_name": "贵州茅台",
            "current_price": 1800.00,
            "change": 15.00,
            "change_percent": 0.84,
            "open": 1785.00,
            "high": 1810.00,
            "low": 1780.00,
            "prev_close": 1785.00,
            "volume": 10000000,
            "amount": 18000000000,
            "update_time": "2024-01-01T15:00:00"
        }
    })


class KLineData(BaseModel):
    """K 线数据点"""
    
    date: str = Field(..., description="日期")
    open: float = Field(..., description="开盘价")
    high: float = Field(..., description="最高价")
    low: float = Field(..., description="最低价")
    close: float = Field(..., description="收盘价")
    volume: Optional[float] = Field(None, description="成交量")
    amount: Optional[float] = Field(None, description="成交额")
    change_percent: Optional[float] = Field(None, description="涨跌幅 (%)")
    
    model_config = ConfigDict(json_schema_extra={
        "example": {
            "date": "2024-01-01",
            "open": 1785.00,
            "high": 1810.00,
            "low": 1780.00,
            "close": 1800.00,
            "volume": 10000000,
            "amount": 18000000000,
            "change_percent": 0.84
        }
    })


class ExtractItem(BaseModel):
    """单条提取结果（代码、名称、置信度）"""

    code: Optional[str] = Field(None, description="股票代码，None 表示解析失败")
    name: Optional[str] = Field(None, description="股票名称（如有）")
    confidence: str = Field("medium", description="置信度：high/medium/low")


class ExtractFromImageResponse(BaseModel):
    """图片股票代码提取响应"""

    codes: List[str] = Field(..., description="提取的股票代码（已去重，向后兼容）")
    items: List[ExtractItem] = Field(default_factory=list, description="提取结果明细（代码+名称+置信度）")
    raw_text: Optional[str] = Field(None, description="原始 LLM 响应（调试用）")


class StockHistoryResponse(BaseModel):
    """股票历史行情响应"""
    
    stock_code: str = Field(..., description="股票代码")
    stock_name: Optional[str] = Field(None, description="股票名称")
    period: str = Field(..., description="K 线周期")
    data: List[KLineData] = Field(default_factory=list, description="K 线数据列表")
    
    model_config = ConfigDict(json_schema_extra={
        "example": {
            "stock_code": "600519",
            "stock_name": "贵州茅台",
            "period": "daily",
            "data": []
        }
    })


class ChartBar(BaseModel):
    """K 线图数据点（time 为日线 YYYY-MM-DD 或分钟线 YYYY-MM-DD HH:MM，北京时间）"""

    time: str = Field(..., description="时间")
    open: float = Field(..., description="开盘价")
    high: float = Field(..., description="最高价")
    low: float = Field(..., description="最低价")
    close: float = Field(..., description="收盘价")
    volume: Optional[float] = Field(None, description="成交量")
    amount: Optional[float] = Field(None, description="成交额")


class ChanPointItem(BaseModel):
    """缠论笔/线段端点，index 指向 bars 中的序号"""

    index: int = Field(..., description="对应 bars 的序号")
    price: float = Field(..., description="端点价格")
    kind: Literal["top", "bottom"] = Field(..., description="顶/底")


class ChanPivotItem(BaseModel):
    """笔中枢（箱体），start_index/end_index 指向 bars 中的序号"""

    start_index: int = Field(..., description="中枢起点对应 bars 的序号")
    end_index: int = Field(..., description="中枢终点对应 bars 的序号（未结束且仍在区间内时为最后一根）")
    zg: float = Field(..., description="中枢上沿 ZG")
    zd: float = Field(..., description="中枢下沿 ZD")
    gg: float = Field(..., description="中枢区间最高点 GG")
    dd: float = Field(..., description="中枢区间最低点 DD")
    confirmed: bool = Field(..., description="中枢是否已结束（离开后回抽不回中枢）")


class ChanBuyPointItem(BaseModel):
    """缠论买点（简化判定），index 指向 bars 中的序号"""

    index: int = Field(..., description="对应 bars 的序号")
    price: float = Field(..., description="买点价格")
    kind: Literal["buy1", "buy2", "buy3"] = Field(..., description="一买/二买/三买")


class MacdSeries(BaseModel):
    """MACD(12, 26, 9)，各数组与 bars 一一对应"""

    dif: List[float] = Field(default_factory=list, description="DIF（快线）")
    dea: List[float] = Field(default_factory=list, description="DEA（慢线）")
    hist: List[float] = Field(default_factory=list, description="MACD 柱，2 * (DIF - DEA)")


class ChanStructure(BaseModel):
    bi: List[ChanPointItem] = Field(default_factory=list, description="笔端点")
    segments: List[ChanPointItem] = Field(default_factory=list, description="线段端点（仅已确认线段）")
    pivots: List[ChanPivotItem] = Field(default_factory=list, description="笔中枢（箱体）")
    buy_points: List[ChanBuyPointItem] = Field(default_factory=list, description="买点（简化判定）")


class StockKlineResponse(BaseModel):
    """K 线图数据：多周期 K 线 + 均线 + MACD + 缠论笔/线段/中枢/买点"""

    stock_code: str = Field(..., description="股票代码")
    stock_name: Optional[str] = Field(None, description="股票名称")
    period: Literal["daily", "weekly", "60m", "30m"] = Field(..., description="K 线周期")
    source: Optional[str] = Field(None, description="数据源")
    bars: List[ChartBar] = Field(default_factory=list, description="K 线")
    moving_averages: Dict[str, List[Optional[float]]] = Field(
        default_factory=dict, description="均线，键为周期，值与 bars 一一对应"
    )
    macd: MacdSeries = Field(default_factory=MacdSeries, description="MACD(12, 26, 9)")
    chan: ChanStructure = Field(default_factory=ChanStructure, description="缠论结构")


class StockProfileQuoteBlock(BaseModel):
    status: StockProfileStatus
    data: Optional[StockQuote] = None
    limitations: List[str] = Field(default_factory=list)


class StockProfileHistoryBlock(BaseModel):
    status: StockProfileStatus
    period: Literal["daily"] = "daily"
    data: List[KLineData] = Field(default_factory=list)
    limitations: List[str] = Field(default_factory=list)


class StockProfileResearchData(BaseModel):
    latest_report: Optional[HistoryItem] = None
    recent_reports: List[HistoryItem] = Field(default_factory=list)
    structured_report: Optional[ResearchArtifact] = None


class StockProfileResearchBlock(BaseModel):
    status: StockProfileStatus
    data: StockProfileResearchData = Field(default_factory=StockProfileResearchData)
    limitations: List[str] = Field(default_factory=list)


class StockProfileIntelligenceBlock(BaseModel):
    status: StockProfileStatus
    items: List[IntelligenceItem] = Field(default_factory=list)
    limitations: List[str] = Field(default_factory=list)


class StockProfilePortfolioRelation(BaseModel):
    held: bool = False
    matched_markets: List[str] = Field(default_factory=list)


class StockProfilePortfolioBlock(BaseModel):
    status: StockProfileStatus
    data: StockProfilePortfolioRelation = Field(default_factory=StockProfilePortfolioRelation)
    limitations: List[str] = Field(default_factory=list)


class StockProfileMonitorData(BaseModel):
    total_rule_count: int = 0
    enabled_rule_count: int = 0
    rule_ids: List[int] = Field(default_factory=list)


class StockProfileMonitorBlock(BaseModel):
    status: StockProfileStatus
    data: StockProfileMonitorData = Field(default_factory=StockProfileMonitorData)
    limitations: List[str] = Field(default_factory=list)


class StockProfileEvidenceQuality(BaseModel):
    status: StockProfileStatus
    blocks: Dict[str, StockProfileStatus] = Field(default_factory=dict)
    limitations: List[str] = Field(default_factory=list)


class StockProfileResponse(BaseModel):
    requested_code: str
    canonical_code: str
    market: Literal["cn", "hk", "us", "jp", "kr", "tw"]
    as_of: str
    quote: StockProfileQuoteBlock
    history: StockProfileHistoryBlock
    research: StockProfileResearchBlock
    intelligence: StockProfileIntelligenceBlock
    portfolio: StockProfilePortfolioBlock
    monitors: StockProfileMonitorBlock
    evidence_quality: StockProfileEvidenceQuality
