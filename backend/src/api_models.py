"""
api_models.py – Pydantic response/request contracts for the FastAPI server.

These mirror EXACTLY the payloads already produced by server.py (no field
renames). Field names with capital letters (Date, Product, ISIN…) are the
canonical CSV schema and must not be changed to snake_case.
"""

from pydantic import BaseModel, Field


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
    # Currencies with no FX rate available: their "eur" value assumes rate 1.0
    # (i.e. is NOT converted). Empty when every currency has a rate.
    missing_fx: list[str] = []
    warning: str | None = None


class CashUpdate(BaseModel):
    # {"EUR": 1234.56, "USD": 500}
    balances: dict[str, float]


class ClassLimit(BaseModel):
    min: float | None = None
    max: float | None = None


class CashBuffer(BaseModel):
    pct: float = 0.0
    amount: float = 0.0


class TargetConfig(BaseModel):
    """Target ("cartera tipo") + diversification rules stored in sources.json."""
    targets: dict[str, float] = {}                 # {asset_class: pct}
    band_pct: float = 0.0                          # tolerance band ±%
    max_asset_pct: float | None = None             # single-asset max weight
    class_limits: dict[str, ClassLimit] = {}       # per-class min/max
    cash_buffer: CashBuffer = CashBuffer()


class RebalanceRow(BaseModel):
    asset_class: str
    has_target: bool           # False → class held but no target set (not an error)
    target_pct: float | None
    target_eur: float | None
    actual_pct: float
    actual_eur: float
    drift_pct: float | None
    band_pct: float
    within_band: bool
    action_eur: float | None   # +buy / -sell; None when no target
    status: str                # "ok" | "comprar" | "vender" | "sin_objetivo"


class RebalanceViolation(BaseModel):
    kind: str                  # max_asset | class_min | class_max | cash_buffer
    target: str
    message: str
    actual_pct: float
    limit_pct: float


class RebalanceResponse(BaseModel):
    configured: bool
    net_worth: float
    target_sum_pct: float
    band_pct: float
    rows: list[RebalanceRow]
    violations: list[RebalanceViolation]
    note: str = ""


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
    # Cash currencies with no FX rate (their EUR value assumes 1.0, not converted).
    cash_missing_fx: list[str] | None = None


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
    id: int | None = None
    # Stable content hash (Date+Coin+Quantity+ticker). Optional: clients may send
    # it back on PUT/DELETE (?fingerprint=...) to detect a stale positional id.
    fingerprint: str | None = None
    Date: str
    Product: str | None = None
    Coin: str | None = None
    Quantity: float | None = None
    ticker: str | None = None
    model_config = {"extra": "allow"}


class CryptoOperationCreate(BaseModel):
    Date: str = Field(max_length=40)
    Coin: str = Field(max_length=32)
    Quantity: float = Field(gt=0, allow_inf_nan=False)
    Product: str = Field(default="", max_length=120)
    ticker: str = Field(default="", max_length=40)
    # Optional optimistic-concurrency token for PUT (same as ?fingerprint=).
    fingerprint: str | None = Field(default=None, max_length=64)


class SourceDef(BaseModel):
    """One entry of stock_sources / crypto_sources in sources.json."""
    name: str = Field(min_length=1, max_length=120)
    file_pattern: str = Field(min_length=1, max_length=200)
    column_map: dict[str, str]
    model_config = {"extra": "allow"}


class SourcesPayload(BaseModel):
    """Body of POST /api/sources (whole sources.json document)."""
    stock_sources: list[SourceDef] = []
    crypto_sources: list[SourceDef] = []
    model_config = {"extra": "allow"}


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


class PreviewFile(BaseModel):
    file: str
    kind: str                       # "stock" | "crypto"
    source: str | None = None
    rows_read: int = 0
    new: int = 0
    duplicates: int = 0
    # Stock rows: {date, product, isin, quantity, price, value}
    # Crypto rows: {date, coin, quantity, ticker}
    entries: list[dict] = []
    error: str | None = None


class ProcessPreview(BaseModel):
    files: list[PreviewFile] = []
    total_new: int = 0
    total_duplicates: int = 0


class ProcessCommitFile(BaseModel):
    file: str
    kind: str                       # "stock" | "crypto"
    entries: list[dict] = []        # edited rows the user confirmed


class ProcessCommit(BaseModel):
    files: list[ProcessCommitFile] = []


class ReportResult(BaseModel):
    ok: bool
    file: str | None = None
    message: str = ""


class SourceFileInfo(BaseModel):
    file: str
    source: str
    enabled: bool


class SourceFileContent(BaseModel):
    file: str
    columns: list[str]
    rows: list[list[str]]         # raw cell values, one inner list per row


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
