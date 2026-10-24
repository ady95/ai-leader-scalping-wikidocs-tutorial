"""05-3 진입가·손절가·손익비·수량

    risk_per_share = entry - stop                     (롱)
    qty_risk       = floor(equity × risk_per_trade ÷ risk_per_share)
    qty_cash       = floor(equity × max_position_ratio ÷ entry)
    qty_liquidity  = floor(liquidity_ratio × 기준봉 거래대금 ÷ entry)
    qty            = min(세 수량)
수량은 **계획**이다. 갭·체결 부족으로 실제 손실이 위험예산을 넘을 수 있다(08장).
"""

import math

from scalping.market import add_ticks, ceil_tick


def stop_price(entry, ref_low, max_loss):
    """구조적 손절(기준봉 저가 아래 1호가)과 손실 상한(-max_loss) 중 진입가에 더 가까운 쪽"""
    return max(add_ticks(int(ref_low), -1), ceil_tick(entry * (1 - max_loss)))


def size(entry, stop, ref_value, account):
    """수량과 어느 한도가 수량을 정했는지(binding)를 돌려준다. risk_per_share <= 0 이면 0주."""
    rps = entry - stop
    if rps <= 0:
        return dict(qty=0, binding="invalid_stop", risk_per_share=rps)
    caps = {
        "risk": math.floor(account["equity"] * account["risk_per_trade"] / rps),
        "cash": math.floor(account["equity"] * account["max_position_ratio"] / entry),
        "liquidity": math.floor(account.get("liquidity_ratio", 0.01) * ref_value / entry),
    }
    binding = min(caps, key=caps.get)
    return dict(qty=max(caps[binding], 0), binding=binding, risk_per_share=rps,
                risk_pct=rps / entry, **{f"qty_{k}": v for k, v in caps.items()})
