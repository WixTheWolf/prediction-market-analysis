import httpx

from src.agent.kalshi_scanner import KalshiScanner, ScannerConfig


def test_public_scan_excludes_multivariate_markets() -> None:
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(dict(request.url.params))
        return httpx.Response(200, json={"markets": [], "cursor": ""})

    client = httpx.Client(
        base_url="https://example.test/trade-api/v2",
        transport=httpx.MockTransport(handler),
    )
    scanner = KalshiScanner(ScannerConfig(min_volume=0), client=client)
    scanner.scan(limit=1)
    client.close()

    assert seen["status"] == "open"
    assert seen["mve_filter"] == "exclude"
