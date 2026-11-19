"""Async CoinMarketCap API client.

Keyless-first: when no API key is configured the client talks to the
public keyless base (``/public-api``) with no auth header. When the
``CMC_API_KEY`` environment variable is set it uses the keyed base and
sends ``X-CMC_PRO_API_KEY``.

The shared-IP anonymous pool behind the keyless endpoint is heavily
used, so most calls from a shared host return CMC error_code 1022
("You've reached the limit for anonymous access"). The client retries
those (and HTTP 429s) with exponential backoff and, if the limit
persists, raises an error that tells the user a free API key removes
the limit.
"""

from __future__ import annotations

import asyncio
import os

import httpx

KEYLESS_BASE = "https://pro-api.coinmarketcap.com/public-api"
KEYED_BASE = "https://pro-api.coinmarketcap.com"

#: Delays (seconds) between attempts. 5 attempts total (initial + 4 retries).
RETRY_DELAYS = (1.0, 2.0, 4.0, 8.0)

#: CMC error code for "anonymous access limit reached".
ERROR_ANONYMOUS_LIMIT = 1022

KEY_HELP = (
    "CoinMarketCap anonymous-access limit reached (error 1022). "
    "A free API key removes this limit: create one at "
    "https://coinmarketcap.com/api/ and set the CMC_API_KEY environment "
    "variable (keyed mode also unlocks the full endpoint catalog)."
)


class CMCError(Exception):
    """Raised when a CoinMarketCap API call fails."""


class KeyRequiredError(CMCError):
    """Raised when a keyed-only endpoint is called without an API key."""


def _proxy_url() -> str | None:
    """Proxy URL from the environment, if one is configured.

    Read explicitly instead of relying on httpx's ``trust_env`` parsing:
    httpx chokes on bracketed IPv6 entries (e.g. ``[::1]``) in ``no_proxy``
    with ``InvalidURL: Invalid port``. Passing the proxy explicitly with
    ``trust_env=False`` avoids that while still routing through the
    sandbox egress proxy when one is set.
    """
    for var in (
        "HTTPS_PROXY",
        "https_proxy",
        "HTTP_PROXY",
        "http_proxy",
        "ALL_PROXY",
        "all_proxy",
    ):
        value = os.environ.get(var)
        if value:
            return value
    return None


def _ca_bundle() -> str | bool:
    """TLS CA bundle to verify the API host with.

    httpx only honours ``SSL_CERT_FILE`` when ``trust_env`` is on, and
    this client runs with ``trust_env=False`` (see :func:`_proxy_url`),
    so resolve the bundle explicitly. The sandbox egress proxy signs
    with its own CA (``/run/hatch/egress-tls/ca-bundle.pem``); the
    stock certifi bundle does not contain it, so without this every
    live call fails TLS verification.
    """
    for var in ("SSL_CERT_FILE", "CURL_CA_BUNDLE"):
        path = os.environ.get(var)
        if path and os.path.exists(path):
            return path
    return True


class CMCClient:
    """Minimal async client for the CoinMarketCap API.

    Parameters
    ----------
    api_key:
        CMC Pro API key. When ``None`` the ``CMC_API_KEY`` environment
        variable is consulted; when still unset the client runs keyless.
    transport:
        Optional httpx transport (used by tests to inject a mock).
    """

    def __init__(
        self,
        api_key: str | None = None,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.api_key = api_key if api_key is not None else os.environ.get("CMC_API_KEY") or None
        self.keyless = self.api_key is None
        self.base_url = KEYLESS_BASE if self.keyless else KEYED_BASE
        self._transport = transport
        self._client: httpx.AsyncClient | None = None

    @property
    def mode(self) -> str:
        return "keyless" if self.keyless else "keyed"

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            headers = {"Accept": "application/json"}
            if not self.keyless:
                # The key header is ONLY sent in keyed mode, never keyless.
                headers["X-CMC_PRO_API_KEY"] = self.api_key  # type: ignore[assignment]
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                headers=headers,
                timeout=httpx.Timeout(15.0),
                transport=self._transport,
                # A configured proxy takes precedence over a custom
                # transport in httpx, so only pass it for real traffic.
                proxy=_proxy_url() if self._transport is None else None,
                trust_env=False,
                verify=_ca_bundle(),
            )
        return self._client

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def __aenter__(self) -> "CMCClient":
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.close()

    async def get(self, path: str, params: dict | None = None) -> dict:
        """GET ``path`` and return the ``data`` payload.

        Retries HTTP 429, HTTP 5xx, transport errors and CMC error 1022
        with exponential backoff (1s / 2s / 4s / 8s).
        """
        client = self._get_client()
        last_error: Exception | None = None
        for attempt in range(len(RETRY_DELAYS) + 1):
            try:
                response = await client.get(path, params=params or {})
            except httpx.TransportError as exc:
                last_error = CMCError(f"Network error calling {path}: {exc}")
                if attempt < len(RETRY_DELAYS):
                    await asyncio.sleep(RETRY_DELAYS[attempt])
                    continue
                raise last_error from exc

            if response.status_code == 429 or response.status_code >= 500:
                last_error = CMCError(
                    f"CoinMarketCap returned HTTP {response.status_code} for {path}."
                    + (" " + KEY_HELP if response.status_code == 429 else "")
                )
                if attempt < len(RETRY_DELAYS):
                    await asyncio.sleep(RETRY_DELAYS[attempt])
                    continue
                raise last_error

            try:
                payload = response.json()
            except ValueError as exc:
                raise CMCError(f"CoinMarketCap returned non-JSON for {path}") from exc

            status = payload.get("status") or {}
            # CMC is inconsistent: some endpoints return error_code as an
            # int (0), others as a string ("0"). Normalise to int so a
            # successful "0" is not mistaken for an error.
            try:
                error_code = int(status.get("error_code", 0))
            except (TypeError, ValueError):
                error_code = status.get("error_code", 0)
            if error_code == ERROR_ANONYMOUS_LIMIT:
                last_error = CMCError(KEY_HELP)
                if attempt < len(RETRY_DELAYS):
                    await asyncio.sleep(RETRY_DELAYS[attempt])
                    continue
                raise last_error
            if error_code:
                raise CMCError(
                    f"CoinMarketCap error {error_code} for {path}: "
                    f"{status.get('error_message', 'unknown error')}"
                )
            if response.status_code >= 400:
                raise CMCError(
                    f"CoinMarketCap returned HTTP {response.status_code} for {path}: "
                    f"{status.get('error_message', response.text[:200])}"
                )
            return payload.get("data", payload)
        # Unreachable in practice; keeps type checkers happy.
        raise last_error or CMCError(f"CoinMarketCap call failed for {path}")

    # -- CEX / market-data endpoints (keyless) --------------------------------

    async def simple_price(self, symbols: str, convert: str = "USD") -> dict:
        """GET /v2/simple/price — simple price for one or more symbols."""
        return await self.get(
            "/v2/simple/price", {"symbol": symbols, "convert": convert}
        )

    async def quotes_latest(
        self, symbols: str | None = None, ids: str | None = None, convert: str = "USD"
    ) -> dict:
        """GET /v3/cryptocurrency/quotes/latest — full quotes for coins."""
        params: dict = {"convert": convert}
        if symbols:
            params["symbol"] = symbols
        if ids:
            params["id"] = ids
        return await self.get("/v3/cryptocurrency/quotes/latest", params)

    async def listings_latest(
        self, limit: int = 20, sort: str = "market_cap", convert: str = "USD",
        sort_dir: str = "desc",
    ) -> list:
        """GET /v3/cryptocurrency/listings/latest — ranked coin listings."""
        return await self.get(
            "/v3/cryptocurrency/listings/latest",
            {"limit": limit, "sort": sort, "convert": convert, "sort_dir": sort_dir},
        )  # type: ignore[return-value]

    async def coin_info(
        self, symbols: str | None = None, ids: str | None = None
    ) -> dict:
        """GET /v2/cryptocurrency/info — metadata for coins."""
        params: dict = {}
        if symbols:
            params["symbol"] = symbols
        if ids:
            params["id"] = ids
        return await self.get("/v2/cryptocurrency/info", params)

    async def global_metrics(self, convert: str = "USD") -> dict:
        """GET /v1/global-metrics/quotes/latest — total market cap, dominance."""
        return await self.get(
            "/v1/global-metrics/quotes/latest", {"convert": convert}
        )

    async def fear_greed(self, limit: int = 1) -> dict:
        """GET /v3/fear-and-greed/latest — latest Fear & Greed index."""
        return await self.get("/v3/fear-and-greed/latest", {"limit": limit})

    async def fear_greed_historical(self, limit: int = 7) -> dict:
        """GET /v3/fear-and-greed/historical — historical Fear & Greed index."""
        return await self.get("/v3/fear-and-greed/historical", {"limit": limit})

    async def cmc100(self) -> dict:
        """GET /v3/index/cmc100-latest — CMC100 index value."""
        return await self.get("/v3/index/cmc100-latest")

    async def altcoin_season(self) -> dict:
        """GET /v1/altcoin-season-index/latest — Altcoin Season Index."""
        return await self.get("/v1/altcoin-season-index/latest")

    async def price_conversion(
        self,
        amount: float,
        symbol: str = "BTC",
        convert: str = "USD",
        coin_id: str | None = None,
    ) -> dict:
        """GET /v2/tools/price-conversion — convert an amount between assets."""
        params: dict = {"amount": amount, "convert": convert}
        if coin_id:
            params["id"] = coin_id
        else:
            params["symbol"] = symbol
        return await self.get("/v2/tools/price-conversion", params)

    # -- DEX endpoints (keyless) ----------------------------------------------

    async def dex_search(self, query: str) -> dict:
        """GET /v1/dex/search — search DEX tokens/pairs by name or symbol."""
        return await self.get("/v1/dex/search", {"query": query})

    async def dex_token(self, platform: str, address: str) -> dict:
        """GET /v1/dex/token — DEX token detail for a contract address."""
        return await self.get("/v1/dex/token", {"platform": platform, "address": address})

    async def dex_security(self, platform: str, address: str) -> dict:
        """GET /v1/dex/security/detail — security audit detail for a DEX token."""
        return await self.get(
            "/v1/dex/security/detail", {"platform": platform, "address": address}
        )

    async def dex_pools(self, platform: str, address: str) -> dict:
        """GET /v1/dex/token/pools — liquidity pools for a DEX token."""
        return await self.get(
            "/v1/dex/token/pools", {"platform": platform, "address": address}
        )

    async def dex_pair_quotes(self, network_id: int, contract_address: str) -> dict:
        """GET /v4/dex/pairs/quotes/latest — quotes for DEX pairs."""
        return await self.get(
            "/v4/dex/pairs/quotes/latest",
            {"network_id": network_id, "contract_address": contract_address},
        )

    async def kline_candles(
        self, platform: str, address: str, interval: str = "1d"
    ) -> dict:
        """GET /v1/k-line/candles — OHLCV candles for a DEX token."""
        return await self.get(
            "/v1/k-line/candles",
            {"platform": platform, "address": address, "interval": interval},
        )

    # -- Keyed-only endpoints ---------------------------------------------------

    async def trending_gainers_losers(
        self, start: int = 1, limit: int = 10, convert: str = "USD", sort_dir: str = "desc"
    ) -> dict:
        """GET /v1/cryptocurrency/trending/gainers-losers — keyed only.

        Raises KeyRequiredError in keyless mode; the endpoint is not part
        of the anonymous catalog.
        """
        if self.keyless:
            raise KeyRequiredError(
                "get_trending_gainers_losers requires a CoinMarketCap API key "
                "(endpoint /v1/cryptocurrency/trending/gainers-losers is not "
                "available in keyless mode). Set CMC_API_KEY to a free key from "
                "https://coinmarketcap.com/api/ — or use find_movers, which "
                "derives gainers/losers from keyless listings instead."
            )
        return await self.get(
            "/v1/cryptocurrency/trending/gainers-losers",
            {"start": start, "limit": limit, "convert": convert, "sort_dir": sort_dir},
        )


def get_client(api_key: str | None = None) -> CMCClient:
    """Build a client from an explicit key or the CMC_API_KEY env var."""
    return CMCClient(api_key=api_key)
