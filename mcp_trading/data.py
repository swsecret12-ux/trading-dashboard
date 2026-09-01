"""Small, read-only Supabase REST client used by the MCP server."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Any

import requests


ALLOWED_COLUMNS = {
    "trade_history": {
        "id",
        "date",
        "ticker",
        "timeframe",
        "setup_pattern",
        "position",
        "result",
        "rr_ratio",
        "profit",
        "entry_basis",
        "exit_basis",
        "chart_image_paths",
        "created_at",
    },
    "analysis_archive": {
        "id",
        "date",
        "ticker",
        "category",
        "source_view",
        "chart_image_paths",
        "detail_image_paths",
        "memo",
        "ai_advice_mapping",
        "ocr_text_mapping",
        "created_at",
    },
    "sector_analysis": {
        "id",
        "ticker",
        "sector",
        "market_cap",
        "vol_1d",
        "vol_1w",
        "vol_1m",
        "vol_1q",
        "vol_1y",
        "issue",
        "detail_data",
        "ai_analysis",
        "created_at",
    },
    "theory_db": {"id", "category", "title", "content", "image_paths"},
}
ALLOWED_TABLES = frozenset(ALLOWED_COLUMNS)
IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9_-]{1,80}$")
TICKER_RE = re.compile(r"^[A-Za-z0-9.^=_:/-]{1,32}$")


def clamp_limit(limit: int, maximum: int = 50) -> int:
    try:
        value = int(limit)
    except (TypeError, ValueError):
        value = 10
    return max(1, min(value, maximum))


def validate_ticker(ticker: str | None) -> str | None:
    if ticker is None or not ticker.strip():
        return None
    value = ticker.strip().upper()
    if not TICKER_RE.fullmatch(value):
        raise ValueError("종목 기호 형식이 올바르지 않습니다.")
    return value


def normalize_filter(value: str | None, maximum: int = 100) -> str | None:
    """Normalize optional human-entered filters and bound local scan work."""
    if value is None:
        return None
    normalized = " ".join(str(value).split())
    return normalized[:maximum] or None


def _contains(value: Any, query: str) -> bool:
    return query.casefold() in str(value or "").casefold()


@dataclass(frozen=True)
class SupabaseConfig:
    url: str
    key: str
    data_token: str

    @classmethod
    def from_env(cls) -> "SupabaseConfig":
        url = os.getenv("SUPABASE_URL", "").rstrip("/")
        key = os.getenv("SUPABASE_PUBLISHABLE_KEY") or os.getenv("SUPABASE_KEY", "")
        data_token = os.getenv("SUPABASE_DATA_TOKEN") or key
        if not url.startswith("https://") or not key:
            raise RuntimeError(
                "SUPABASE_URL과 SUPABASE_PUBLISHABLE_KEY 환경변수가 필요합니다."
            )
        return cls(url=url, key=key, data_token=data_token)


class SupabaseReadClient:
    """Only exposes fixed GET operations; it cannot insert, update, or delete."""

    def __init__(
        self,
        url: str,
        key: str,
        data_token: str | None = None,
        timeout: int = 15,
        session: requests.Session | None = None,
    ) -> None:
        self.url = url.rstrip("/")
        self.timeout = timeout
        self.session = session or requests.Session()
        self.headers = {
            "apikey": key,
            "Authorization": f"Bearer {data_token or key}",
            "Accept": "application/json",
        }

    @classmethod
    def from_env(cls) -> "SupabaseReadClient":
        config = SupabaseConfig.from_env()
        return cls(config.url, config.key, config.data_token)

    def _get(self, table: str, params: dict[str, str]) -> list[dict[str, Any]]:
        if table not in ALLOWED_TABLES:
            raise ValueError("허용되지 않은 데이터 테이블입니다.")
        selected = params.get("select", "")
        selected_columns = {column.strip() for column in selected.split(",")}
        if (
            not selected
            or "*" in selected_columns
            or not selected_columns.issubset(ALLOWED_COLUMNS[table])
        ):
            raise ValueError("허용되지 않은 데이터 컬럼입니다.")
        try:
            response = self.session.get(
                f"{self.url}/rest/v1/{table}",
                headers=self.headers,
                params=params,
                timeout=self.timeout,
            )
            response.raise_for_status()
            payload = response.json()
        except requests.RequestException as exc:
            raise RuntimeError(
                "저장 데이터 조회에 실패했습니다. Supabase 상태와 환경변수를 확인해 주세요."
            ) from exc
        except ValueError as exc:
            raise RuntimeError("저장 데이터 응답 형식이 올바르지 않습니다.") from exc
        if not isinstance(payload, list) or not all(
            isinstance(row, dict) for row in payload
        ):
            raise RuntimeError("저장 데이터 응답 형식이 올바르지 않습니다.")
        return payload

    def dashboard_status(self) -> dict[str, Any]:
        tables: dict[str, dict[str, Any]] = {}
        for table in sorted(ALLOWED_TABLES):
            try:
                rows = self._get(
                    table,
                    {"select": "id", "limit": "1"},
                )
                tables[table] = {
                    "available": True,
                    "has_records": bool(rows),
                }
            except RuntimeError:
                tables[table] = {"available": False, "has_records": False}
        return {"mode": "read_only", "tables": tables}

    def list_recent_trades(
        self,
        limit: int = 10,
        ticker: str | None = None,
        result: str | None = None,
    ) -> list[dict[str, Any]]:
        requested = clamp_limit(limit)
        ticker = validate_ticker(ticker)
        result = normalize_filter(result)
        params = {
            "select": (
                "id,date,ticker,timeframe,setup_pattern,position,result,rr_ratio,"
                "profit,entry_basis,exit_basis,chart_image_paths,created_at"
            ),
            "order": "created_at.desc",
            "limit": str(50 if ticker or result else requested),
        }
        if ticker:
            params["ticker"] = f"eq.{ticker}"
        rows = self._get("trade_history", params)
        if result:
            rows = [row for row in rows if _contains(row.get("result"), result)]
        return rows[:requested]

    def get_trade_detail(self, trade_id: str | int) -> dict[str, Any] | None:
        value = str(trade_id).strip()
        if not IDENTIFIER_RE.fullmatch(value):
            raise ValueError("매매 기록 ID 형식이 올바르지 않습니다.")
        rows = self._get(
            "trade_history",
            {
                "select": (
                    "id,date,ticker,timeframe,setup_pattern,position,result,rr_ratio,"
                    "profit,entry_basis,exit_basis,chart_image_paths,created_at"
                ),
                "id": f"eq.{value}",
                "limit": "1",
            },
        )
        return rows[0] if rows else None

    def search_analysis_archive(
        self,
        query: str | None = None,
        ticker: str | None = None,
        category: str | None = None,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        requested = clamp_limit(limit)
        ticker = validate_ticker(ticker)
        query = normalize_filter(query)
        category = normalize_filter(category)
        params = {
            "select": (
                "id,date,ticker,category,source_view,chart_image_paths,"
                "detail_image_paths,memo,ai_advice_mapping,ocr_text_mapping,created_at"
            ),
            "order": "created_at.desc",
            "limit": str(50 if query or category else requested),
        }
        if ticker:
            params["ticker"] = f"eq.{ticker}"
        rows = self._get("analysis_archive", params)
        if category:
            rows = [row for row in rows if _contains(row.get("category"), category)]
        if query:
            searchable = ("ticker", "category", "source_view", "memo", "ocr_text_mapping")
            rows = [
                row
                for row in rows
                if any(_contains(row.get(key), query) for key in searchable)
            ]
        return rows[:requested]

    def list_watchlist(
        self, ticker: str | None = None, limit: int = 20
    ) -> list[dict[str, Any]]:
        requested = clamp_limit(limit)
        ticker = validate_ticker(ticker)
        params = {
            "select": (
                "id,date,ticker,category,source_view,memo,ai_advice_mapping,created_at"
            ),
            "order": "created_at.desc",
            "category": "eq.나의관점",
            "limit": str(requested),
        }
        if ticker:
            params["ticker"] = f"eq.{ticker}"
        return self._get("analysis_archive", params)[:requested]

    def list_sector_research(
        self,
        sector: str | None = None,
        ticker: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        requested = clamp_limit(limit)
        ticker = validate_ticker(ticker)
        sector = normalize_filter(sector)
        params = {
            "select": (
                "id,ticker,sector,market_cap,vol_1d,vol_1w,vol_1m,vol_1q,vol_1y,"
                "issue,detail_data,ai_analysis,created_at"
            ),
            "order": "created_at.desc",
            "limit": str(50 if sector else requested),
        }
        if ticker:
            params["ticker"] = f"eq.{ticker}"
        rows = self._get("sector_analysis", params)
        if sector:
            rows = [row for row in rows if _contains(row.get("sector"), sector)]
        return rows[:requested]

    def list_custom_theories(self, limit: int = 50) -> list[dict[str, Any]]:
        return self._get(
            "theory_db",
            {
                "select": "id,category,title,content,image_paths",
                "order": "category.asc,title.asc",
                "limit": str(clamp_limit(limit)),
            },
        )
