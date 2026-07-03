"""
api_models.py – Pydantic response/request contracts for the FastAPI server.

These mirror EXACTLY the payloads already produced by server.py (no field
renames). Field names with capital letters (Date, Product, ISIN…) are the
canonical CSV schema and must not be changed to snake_case.
"""

from pydantic import BaseModel


class XY(BaseModel):
    x: str            # "YYYY-MM-DD"
    y: float


class Metrics(BaseModel):
    # Totales
    fecha_actual: str | None = None
    dias_totales: int | None = None
    anhos_totales: float | None = None
    capital_total: float | None = None
    valor_total: float | None = None
    plusvalia_total: float | None = None
    rentabilidad_total: float | None = None
    cagr_total: float | None = None
    twr_total_total: float | None = None
    twr_total_anual: float | None = None
    # Acciones
    capital_aportado_acciones: float | None = None
    valor_actual_acciones: float | None = None
    plusvalia_acciones: float | None = None
    rentabilidad_acciones: float | None = None
    cagr_acciones: float | None = None
    twr_acciones_total: float | None = None
    twr_acciones_anual: float | None = None
    peso_acciones: float | None = None
    # Crypto
    capital_aportado_crypto: float | None = None
    valor_actual_crypto: float | None = None
    plusvalia_crypto: float | None = None
    rentabilidad_crypto: float | None = None
    cagr_crypto: float | None = None
    twr_cripto_total: float | None = None
    twr_cripto_anual: float | None = None
    peso_crypto: float | None = None
    # Benchmark
    benchmark_ticker: str | None = None
    benchmark_name: str | None = None
    benchmark_total: float | None = None
    benchmark_annual: float | None = None

    model_config = {"extra": "allow"}   # compute_metrics may add keys


class AssetSlice(BaseModel):
    name: str
    symbol: str
    value: float


class CryptoSlice(BaseModel):
    name: str
    symbol: str
    value: float
    pct: float


class ClassSlice(BaseModel):
    name: str
    value: float
    pct: float
    members: list[AssetSlice] = []


class AssetClassItem(BaseModel):
    symbol: str
    name: str
    auto: str                 # class from the heuristic
    override: str | None = None   # explicit override from sources.json, if any
    effective: str            # override or auto
    kind: str                 # "stock" | "crypto"


class AssetClassesResponse(BaseModel):
    known_classes: list[str]
    items: list[AssetClassItem]


class CashEntry(BaseModel):
    currency: str
    amount: float
    eur: float


class CashResponse(BaseModel):
    balances: list[CashEntry]
    total_eur: float


class CashUpdate(BaseModel):
    # {"EUR": 1234.56, "USD": 500}
    balances: dict[str, float]


class CorrelationAsset(BaseModel):
    name: str
    symbol: str
    weight: float


class CorrelationPair(BaseModel):
    asset_1: str
    asset_2: str
    corr: float


class CorrelationMatrix(BaseModel):
    labels: list[str]
    values: list[list[float | None]]


class Correlation(BaseModel):
    threshold_pct: float
    assets: list[CorrelationAsset]
    matrix: CorrelationMatrix
    top_positive: list[CorrelationPair]
    top_negative: list[CorrelationPair]
    history_days: int
    note: str


class PortfolioChart(BaseModel):
    value: list[XY]
    invested: list[XY]
    benchmark: list[XY] | None = None


class CryptoChart(BaseModel):
    value: list[XY]
    invested: list[XY]


class DashboardResponse(BaseModel):
    # `error` present only when there are no operations (behaviour preserved).
    error: str | None = None
    metrics: Metrics | None = None
    has_crypto: bool | None = None
    portfolio_chart: PortfolioChart | None = None
    composition: list[AssetSlice] | None = None
    composition_full: list[AssetSlice] | None = None
    portfolio_total_value: float | None = None
    cash_total: float | None = None
    net_worth: float | None = None
    top_assets: list[AssetSlice] | None = None
    class_breakdown: list[ClassSlice] | None = None
    correlation: Correlation | None = None
    crypto_chart: CryptoChart | None = None
    crypto_breakdown: list[CryptoSlice] | None = None
    crypto_total_value: float | None = None
    failed_tickers: list[str] | None = None


class Operation(BaseModel):
    Date: str
    Product: str | None = None
    ticker: str | None = None
    ISIN: str | None = None
    Quantity: float | None = None
    Price: float | None = None
    Coin: str | None = None
    Value: float | None = None


class OperationCreate(BaseModel):
    Date: str
    Product: str
    ISIN: str
    Quantity: float
    Price: float
    Coin: str = "EUR"
    ticker: str = ""
    Value: float | None = None    # if missing: ±|Quantity×Price| (negative on buy)


class CryptoOperation(BaseModel):
    Date: str
    Product: str | None = None
    Coin: str | None = None
    Quantity: float | None = None
    ticker: str | None = None
    model_config = {"extra": "allow"}


class CryptoOperationCreate(BaseModel):
    Date: str
    Coin: str
    Quantity: float               # > 0
    Product: str = ""
    ticker: str = ""


class TaxResponse(BaseModel):
    gains: list[dict]
    annual: list[dict]
    by_ticker: list[dict]


class OkResponse(BaseModel):
    ok: bool


class MutationResult(BaseModel):
    ok: bool
    row: dict


class UploadResponse(BaseModel):
    saved: list[str]


class ProcessResult(BaseModel):
    ok: bool
    stock_added: int = 0
    crypto_added: int = 0
    files: list[str] = []
    message: str = ""


class ReportResult(BaseModel):
    ok: bool
    file: str | None = None
    message: str = ""


class SourceFileInfo(BaseModel):
    file: str
    source: str
    enabled: bool


class SourceDataEntry(BaseModel):
    date: str
    quantity: float
    price: float
    value: float


class SourceData(BaseModel):
    source: str
    file: str
    ticker: str | None = None
    product: str | None = None
    coin: str | None = None
    total_qty: float | None = None
    total_value: float | None = None
    entries: list[SourceDataEntry] = []
    error: str | None = None
