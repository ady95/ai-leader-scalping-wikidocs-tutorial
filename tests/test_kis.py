from scalping.kis import DOMAINS, RateLimiter


def test_domains_are_official():
    assert DOMAINS["real"] == "https://openapi.koreainvestment.com:9443"
    assert DOMAINS["paper"] == "https://openapivts.koreainvestment.com:29443"


def test_rate_limiter_spacing():
    import time

    limiter = RateLimiter(per_sec=20)
    start = time.monotonic()
    for _ in range(5):
        limiter.wait()
    assert time.monotonic() - start >= 0.19
