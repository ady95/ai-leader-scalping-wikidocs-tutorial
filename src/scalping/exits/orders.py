"""08-5 매도 주문 장부 — 우선순위, 부분체결, 중복 주문

한국투자증권 Open API에는 "익절 지정가와 손절을 묶어 하나가 체결되면 나머지를 자동 취소"하는 OCO 주문이 없다.
그래서 애플리케이션이 보유 수량과 미체결 매도 주문을 함께 들고 다음을 지킨다.

    매도 가능 수량 = 보유 수량 - 미체결 매도 수량(취소 요청 중인 주문 포함)
    더 높은 우선순위의 청산이 오면 낮은 우선순위의 미체결 주문을 먼저 취소하고, 취소가 확인된 만큼만 새로 낸다
    취소 요청 중에 체결된 수량은 체결로 처리한다 (취소는 즉시 일어나지 않는다)

우선순위 (작을수록 먼저): 1 장애·위험 한도 > 2 손절·1~2분 시간손절 > 3 추적손절·표준 시간손절 > 4 익절
"""

from dataclasses import dataclass
from itertools import count

PRIORITY = {"risk": 1, "stop": 2, "fast": 2, "trail": 3, "time": 3, "take": 4}


@dataclass
class Order:
    oid: int
    kind: str
    qty: int
    price: int | None             # None = 시장가
    filled: int = 0
    state: str = "open"           # open / cancelling / done

    @property
    def rest(self):
        return self.qty - self.filled


class SellBook:
    def __init__(self, holding):
        self.holding = holding
        self.orders = {}
        self.want = None              # 취소 확인을 기다리는 상위 청산 (kind, price)
        self._ids = count(1)

    def pending(self):
        return sum(o.rest for o in self.orders.values() if o.state in ("open", "cancelling"))

    def available(self):
        return self.holding - self.pending()

    def request(self, kind, qty=None, price=None):
        """청산 요청 → 실행할 행동 목록 [("cancel", oid) | ("new", Order)]. qty=None 이면 남은 수량 전부."""
        acts, prio = [], PRIORITY[kind]
        if any(o.kind == kind and o.state == "open" for o in self.orders.values()):
            return acts                                                   # 같은 청산이 이미 나가 있다 (중복 방지)
        if qty is None:
            for o in self.orders.values():                                # 전량 청산: 낮은 순위 주문을 거둔다
                if o.state == "open" and PRIORITY[o.kind] > prio:
                    o.state = "cancelling"
                    acts.append(("cancel", o.oid))
            if acts:
                self.want = (kind, price)
        q = self.available() if qty is None else min(qty, self.available())
        if q > 0:
            o = Order(next(self._ids), kind, q, price)
            self.orders[o.oid] = o
            acts.append(("new", o))
        return acts

    def on_fill(self, oid, qty):
        o = self.orders[oid]
        o.filled += qty
        self.holding -= qty
        if o.rest == 0:
            o.state = "done"

    def on_cancelled(self, oid):
        """취소 확인 → 기다리던 상위 청산을 남은 가능 수량만큼 이어서 낸다"""
        self.orders[oid].state = "done"
        if self.want and not any(o.state == "cancelling" for o in self.orders.values()):
            kind, price = self.want
            self.want = None
            q = self.available()
            if q > 0:
                o = Order(next(self._ids), kind, q, price)
                self.orders[o.oid] = o
                return [("new", o)]
        return []
