from scalping.market import add_ticks, ceil_tick, floor_tick, tick_size, upper_limit


def test_upper_limit_matches_exchange():
    # 2026-10-22 한국투자증권 현재가 API의 기준가·상한가 (형제 도서 실측값)
    cases = {10_140: 13_180, 17_680: 22_950, 30_950: 40_200, 63_500: 82_500,
             179_500: 233_000, 223_500: 290_500, 430_000: 559_000, 1_294_000: 1_682_000}
    for base, expected in cases.items():
        assert upper_limit(base) == expected


def test_tick_rounding():
    assert tick_size(1_999) == 1 and tick_size(2_000) == 5
    assert floor_tick(10_456) == 10_450 and ceil_tick(10_451) == 10_460


def test_add_ticks_crosses_band():
    assert add_ticks(4_995, 1) == 5_000      # 5원 단위 → 다음 칸
    assert add_ticks(5_000, 1) == 5_010      # 10원 단위 구간
    assert add_ticks(5_000, -1) == 4_995     # 아래 칸은 아래 구간의 단위
