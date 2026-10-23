"""01-5 샘플 하루 재생 — 공개 전략 기준 전략(B0)의 간이판으로 시스템 전체 흐름을 본다.

    uv run python examples/ch01_replay.py

후보 → 햄버거 → 진입 → 청산 → 오버나이트 보유 → 로그까지 한 번에 흐른다.
각 단계의 정식 구현은 02장(후보)·04장(햄버거)·05~06장(진입)·07장(시간·재료)·08~09장(청산·보유)에서 만든다.
여기서는 1분봉이 끝난 시각(available_at)에만 판단한다는 규칙 하나만 엄격히 지킨다.
"""

import datetime as dt
import math

import pandas as pd

from scalping.config import load_config
from scalping.market import add_ticks, ceil_tick
from scalping.paths import REPORTS
from scalping.sample import load


class DayReplay:
    def __init__(self, data, cfg):
        self.cfg, self.b0, self.costs = cfg, cfg["b0"], cfg["costs"]
        self.stocks = data["stocks"].set_index("code")
        self.news = data["news"]
        self.next_open = data["next_open"].set_index("code")
        self.bars = data["bars"].sort_values(["time", "code"])
        self.state = {c: "WATCHLIST" for c in self.stocks.index}
        self.event, self.pos, self.log, self.trades = {}, {}, [], []

    def note(self, at, code, state, msg):
        self.state[code] = state
        self.log.append(dict(at=at, code=code, state=state, msg=msg))

    def has_news(self, code, at):
        """판단 시각 이전에 나온 뉴스만 본다."""
        n = self.news[(self.news.code == code) & (self.news.time < at)]
        return len(n) > 0

    # 1. 햄버거: 과거 급등 임계치를 넘는 1분봉 거래대금 (04장의 간이판)
    def on_bar_closed(self, bar, at):
        code, s = bar.code, self.stocks.loc[bar.code]
        st = self.state[code]
        if st == "WATCHLIST" and bar.value >= s.threshold:
            ratio = bar.value / s.threshold
            zone = bar.close / s.prev_close - 1
            head = f"기준봉 {bar.time:%H:%M} 대금 {bar.value / 1e8:.0f}억(임계치의 {ratio:.2f}배), 위치 {zone:+.1%}"
            if at.strftime("%H:%M") < self.b0["no_entry_before"]:
                self.note(at, code, "BLOCKED", f"{head} → {self.b0['no_entry_before']} 전이라 진입하지 않음")
            elif zone >= self.b0["high_zone_min"]:
                self.note(at, code, "BLOCKED", f"{head} → 높은 구간: 추격하지 않고 눌림을 기다림(06장)")
            elif zone < self.b0["low_zone_max"]:
                self.event[code] = dict(ref_high=bar.high, ref_low=bar.low, bars_left=self.b0["breakout_valid_bars"])
                self.note(at, code, "EVENT_LOCKED", f"{head} → 낮은 구간: 고점 {bar.high:,}원 돌파 대기")
            else:
                self.note(at, code, "BLOCKED", f"{head} → 중간 구간: 이 장에서는 건너뜀")
            if self.state[code] == "BLOCKED":
                self.state[code] = "WATCHLIST"            # 같은 날 다음 햄버거는 다시 본다
        elif st == "OPEN":
            self.manage(bar, at)

    # 2. 진입: 다음 봉에서 기준봉 고점을 넘으면 산다 (05장의 간이판)
    def on_bar(self, bar):
        code = bar.code
        if self.state[code] != "EVENT_LOCKED":
            return
        ev = self.event[code]
        trigger = add_ticks(ev["ref_high"], 1)
        if bar.high >= trigger:
            fill = add_ticks(max(bar.open, trigger), self.costs["slippage_ticks"])
            self.enter(bar, fill, ev)
        else:
            ev["bars_left"] -= 1
            if ev["bars_left"] == 0:
                self.note(bar.time + dt.timedelta(minutes=1), code, "WATCHLIST", "돌파 없이 유효 시간 만료")

    def enter(self, bar, fill, ev):
        acct = self.cfg["account"]
        stop = max(add_ticks(ev["ref_low"], -1), ceil_tick(fill * (1 - self.b0["max_loss"])))
        risk_qty = math.floor(acct["equity"] * acct["risk_per_trade"] / (fill - stop))
        cap_qty = math.floor(acct["equity"] * acct["max_position_ratio"] / fill)
        qty = min(risk_qty, cap_qty)
        news = self.has_news(bar.code, bar.time)
        target = None if news else ceil_tick(fill * (1 + self.b0["no_news_take_profit"]))
        self.pos[bar.code] = dict(entry=fill, qty=qty, stop=stop, target=target, news=news,
                                  entry_time=bar.time, bars=0)
        plan = f"손절 {stop:,}원" + (f", 익절 {target:,}원" if target else ", 재료 동반: 익절 목표 없음")
        self.note(bar.time, bar.code, "OPEN",
                  f"돌파 매수 {fill:,}원 x {qty}주 (신호 {add_ticks(ev['ref_high'], 1):,}원 + 슬리피지) · {plan}")

    # 3. 청산: 손실 상한 → 익절 → 1~2분 시간손절 순서로 본다 (08장의 간이판)
    def manage(self, bar, at):
        p = self.pos[bar.code]
        p["bars"] += 1
        if bar.time == p["entry_time"]:          # 매수한 봉 안의 움직임은 순서를 알 수 없으니 보지 않는다
            return
        slip = self.costs["slippage_ticks"]
        if bar.low <= p["stop"]:
            self.exit(bar.code, at, add_ticks(p["stop"], -slip), "손실 상한/구조적 손절")
        elif p["target"] and bar.high >= p["target"]:
            self.exit(bar.code, at, p["target"], "재료 없는 종목 3% 익절")
        elif p["bars"] == self.b0["fast_stop_bars"] and bar.close <= p["entry"]:
            self.exit(bar.code, at, add_ticks(bar.close, -slip), f"{p['bars']}분 안에 못 감: 초단기 시간손절")

    def exit(self, code, at, price, reason, day=None):
        p = self.pos.pop(code)
        c = self.costs
        buy = p["entry"] * p["qty"] * (1 + c["commission"])
        sell = price * p["qty"] * (1 - c["commission"] - c["sell_tax"])
        self.trades.append(dict(code=code, entry=p["entry"], exit=price, qty=p["qty"], reason=reason,
                                day=day or "당일", pnl=round(sell - buy), ret=sell / buy - 1))
        self.note(at, code, "CLOSED", f"{reason} {price:,}원 → 손익 {sell - buy:+,.0f}원")

    # 4. 장 마감: 재료 동반 상한가는 들고 가고, 나머지는 정리한다 (09장의 간이판)
    def close_session(self, last):
        at = last.time.max() + dt.timedelta(minutes=1)
        for code in list(self.pos):
            p, s = self.pos[code], self.stocks.loc[code]
            close = last.set_index("code").close[code]
            if p["news"] and close == s.upper_limit:
                self.note(at, code, "HOLD_OVERNIGHT", f"재료 동반 상한가 {close:,}원 마감 → 다음 날 시가에 청산")
            else:
                self.exit(code, at, close, "장 마감 정리")
        for code in [c for c, st in self.state.items() if st == "HOLD_OVERNIGHT"]:
            nxt = self.next_open.loc[code]
            self.exit(code, pd.Timestamp(f"{nxt.date} 09:00"), int(nxt.open),
                      "오버나이트 → 다음 날 시가 청산", day="다음 날")

    def run(self):
        times = sorted(self.bars.time.unique())
        for t in times:
            now = self.bars[self.bars.time == t]
            for bar in now.itertuples():
                self.on_bar(bar)                              # 봉이 진행 중일 때: 걸어 둔 돌파 주문
            at = t + pd.Timedelta(minutes=1)                  # 봉이 끝난 시각
            for bar in now.itertuples():
                self.on_bar_closed(bar, at)
        self.close_session(self.bars[self.bars.time == times[-1]])
        return pd.DataFrame(self.log), pd.DataFrame(self.trades)


def main():
    cfg = load_config()
    log, trades = DayReplay(load(), cfg).run()
    for r in log.itertuples():
        print(f"{r.at:%m-%d %H:%M}  {r.code}  {r.state:<14} {r.msg}")
    print()
    print(trades[["code", "entry", "exit", "qty", "day", "pnl", "ret", "reason"]]
          .to_string(index=False, formatters={"ret": "{:+.2%}".format}))
    print(f"\n합계 손익 {trades.pnl.sum():+,}원 (비용 포함, 가상 데이터)")
    REPORTS.mkdir(exist_ok=True)
    log.to_csv(REPORTS / "ch01_replay_log.csv", index=False, encoding="utf-8-sig")
    trades.to_csv(REPORTS / "ch01_trades.csv", index=False, encoding="utf-8-sig")


if __name__ == "__main__":
    main()
