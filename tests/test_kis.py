from scalping.kis import DOMAINS, RateLimiter


def test_domains_are_official():
    assert DOMAINS["real"] == "https://openapi.koreainvestment.com:9443"
    assert DOMAINS["paper"] == "https://openapivts.koreainvestment.com:29443"


def test_rate_limiter_schedules_fixed_spacing():
    # 벽시계로 재면 운영체제 타이머 오차로 흔들리므로, 다음 호출 예정 시각의 간격을 확인한다
    limiter = RateLimiter(per_sec=20)
    first = limiter.next_at
    for _ in range(5):
        limiter.wait()
    assert abs((limiter.next_at - first) - 5 * 0.05) < 0.02
