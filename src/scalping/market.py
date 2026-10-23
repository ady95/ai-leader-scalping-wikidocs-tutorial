"""KRX 호가가격단위와 가격제한폭 (2023-01-25 개편 단위표 기준)

이 책의 데이터는 2025-10 이후이므로 개편 후 단위표 하나만 쓴다.
"""

# (구간 상한, 호가단위) — 마지막 구간은 상한 없음
TICKS = [(2_000, 1), (5_000, 5), (20_000, 10), (50_000, 50),
         (200_000, 100), (500_000, 500), (None, 1_000)]


def tick_size(price):
    for bound, tick in TICKS:
        if bound is None or price < bound:
            return tick


def floor_tick(price):
    """가격을 그 가격대의 호가단위로 버린다."""
    tick = tick_size(price)
    return int(price // tick * tick)


def ceil_tick(price):
    """가격을 그 가격대의 호가단위로 올린다."""
    tick = tick_size(price)
    return int(-(-price // tick) * tick)


def add_ticks(price, n):
    """호가 n칸 위(음수면 아래) 가격. 구간 경계를 넘을 때도 한 칸씩 이동한다."""
    for _ in range(abs(n)):
        price = price + tick_size(price) if n > 0 else price - tick_size(price - 1)
    return int(price)


def upper_limit(base):
    """상한가 = 기준가격 + (기준가격 x 30%를 기준가격의 호가단위로 버린 금액)을 그 가격대 호가단위로 버림"""
    width = base * 3 // 10 // tick_size(base) * tick_size(base)
    return floor_tick(base + width)
