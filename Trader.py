"""
🌶️ INTARIAN_PEPPER_ROOT — "The Escalator"
The dominant pattern is a perfect linear trend: +1000 pts per day, every day, like clockwork. Day -2 starts at 10,000 and ends at 11,000. Day -1: 11,000 → 12,000. Day 0: 12,000 → 13,000. The slope is almost exactly 0.001 pts per timestamp unit. This is not noise — it's a deterministic drift.
But layered on top is strong mean reversion. Once you subtract the trend, the residual has a std of only ±2.2 pts and bounces back hard — IR of 2.84 when residual exceeds ±6 pts. The OBI signal is also 0.65 correlated with the next tick, identical to what you saw with Tomatoes.
Suggested algo: A trend-following market maker. Your fair value at any tick is base_for_day + timestamp * 0.001. Quote around that fair value. When the residual stretches beyond ±6, aggressively take the mean-reverting side. This gives you two income streams simultaneously.

🪨 ASH_COATED_OSMIUM — "The Emerald Clone"
This looks almost identical to Emeralds from the tutorial: mean ≈ 10,000, std of only 5.3 pts, tight range of 9,977–10,023 across all three days. It barely moves. The z-score mean reversion is real (IR of 2.36 at z > 2) but the spread at median 16 is wide, suggesting the same market-making approach as Emeralds will work well here.
The key difference from Emeralds: OBI level 1 is a much stronger signal here — 0.65 correlation with the next tick versus Emerald's weaker signal. Use OBI to time your passive quotes rather than posting symmetrically.
Suggested algo: Near-identical to your Emerald v2 code. Fair value = 10,000, quote inside the 16-wide spread, use OBI_1 to skew — only post the bid when OBI > 0, only post the ask when OBI < 0.

Position Limits to Infer
Both products have bid/ask volumes of 10–15 units at best price. The tutorial products had limits of 10–20. Assume similar — play it safe with ±15 until you know for sure.
"""

import math
from datamodel import OrderDepth, TradingState, Order
from typing import List
import jsonpickle


class Trader:
    # ── EMERALD parameters ────────────────────────────────────────────────────
    EMERALD_FAIR_VAL = 10000
    EMERALD_BID_OFFSET = 3  # FIX: tightened from 3 → 9998 (more fills, same safety)
    EMERALD_ASK_OFFSET = 3  # FIX: tightened from 3 → 10002
    EMERALD_LOT = 10
    MAX_EMERALD_POS = 20

    # ── TOMATO parameters ─────────────────────────────────────────────────────
    MAX_TOMATO_POS = 10
    TOMATO_WINDOW = 50
    TOMATO_MIN_STD = 5.0
    TOMATO_DEFAULT_MEAN = 4992.6
    TOMATO_DEFAULT_STD = 21.13
    TOMATO_THRES_BUY = 0.067582
    TOMATO_THRES_SELL = 0.05
    TOMATO_CHEEKY_SCORE = 5

    # ── ASH_COATED_OSMIUM parameters ────────────────────────────────────────────────────
    ASH_COATED_OSMIUM_FAIR_VAL = 10000
    ASH_COATED_OSMIUM_BID_OFFSET = 6
    ASH_COATED_OSMIUM_ASK_OFFSET = 6
    ASH_COATED_OSMIUM_LOT = 10
    MAX_ASH_COATED_OSMIUM_POS = 20

    Z_ENTRY = 0.8  # take liquidity when |z| > this
    Z_STRONG = 1.5  # double lot size when |z| > this

    OBI_GATE = 0.0  # OBI must agree with direction (0 = any positive alignment)

    INVENTORY_SKEW = 0.5  # pts per unit of position to shift fair value

    # ─────────────────────────────────────────────────────────────────────────

    def _obi(self, order_depth: OrderDepth, level: int) -> float:
        bid_prices = sorted(order_depth.buy_orders.keys(), reverse=True)
        ask_prices = sorted(order_depth.sell_orders.keys())
        if len(bid_prices) < level or len(ask_prices) < level:
            return 0.0
        bv = order_depth.buy_orders[bid_prices[level - 1]]
        av = -order_depth.sell_orders[ask_prices[level - 1]]
        total = bv + av
        return (bv - av) / total if total > 0 else 0.0

    def _mid(self, order_depth: OrderDepth):
        if not order_depth.buy_orders or not order_depth.sell_orders:
            return None
        return (max(order_depth.buy_orders) + min(order_depth.sell_orders)) / 2.0

    def _rolling_stats(self, prices: list):
        n = len(prices)
        if n == 0:
            return self.self.TOMATO_DEFAULT_MEAN, self.self.TOMATO_DEFAULT_STD
        mean = sum(prices) / n
        if n < 2:
            return mean, self.self.TOMATO_DEFAULT_STD
        variance = sum((p - mean) ** 2 for p in prices) / (n - 1)
        std = math.sqrt(variance) if variance > 0 else self.self.TOMATO_DEFAULT_STD
        return max(std, self.TOMATO_MIN_STD), mean  # intentional: returns (std, mean)

    def _rolling_stats(self, prices: list):
        n = len(prices)
        if n == 0:
            return self.self.TOMATO_DEFAULT_MEAN, self.self.TOMATO_DEFAULT_STD
        mean = sum(prices) / n
        if n < 2:
            return mean, self.self.TOMATO_DEFAULT_STD
        variance = sum((p - mean) ** 2 for p in prices) / (n - 1)
        std = math.sqrt(variance) if variance > 0 else self.self.TOMATO_DEFAULT_STD
        std = max(std, self.TOMATO_MIN_STD)
        return mean, std

    def run(self, state: TradingState):
        trader_data: dict = jsonpickle.decode(state.traderData) if state.traderData else {}
        tomato_prices: list = trader_data.get("tomato_prices", [])

        result = {}

        for product, order_depth in state.order_depths.items():
            orders: List[Order] = []
            pos = state.position.get(product, 0)

            # ── EMERALDS ──────────────────────────────────────────────────────
            if product == "EMERALDS":
                mid = self._mid(order_depth)
                fair = self.EMERALD_FAIR_VAL

                if mid is not None and mid != fair:
                    # Dislocation: market at 9996 or 10004
                    # Skew quotes back toward fair but keep minimum edge
                    skew = int(round(fair - mid))
                    my_bid = fair - self.EMERALD_BID_OFFSET + skew
                    my_ask = fair + self.EMERALD_ASK_OFFSET + skew
                    # BUG 2 FIX: hard-floor so we always have at least 1pt edge
                    my_bid = min(my_bid, fair - 1)
                    my_ask = max(my_ask, fair + 1)
                else:
                    my_bid = fair - self.EMERALD_BID_OFFSET  # 9998
                    my_ask = fair + self.EMERALD_ASK_OFFSET  # 10002

                # Inventory skew: nudge quotes to reduce position risk
                inv_skew = -int(round(pos * 0.1))
                my_bid += inv_skew
                my_ask += inv_skew

                # BUG 1 FIX: size each quote so it cannot breach the position limit
                buy_headroom = self.MAX_EMERALD_POS - pos  # how much long room left
                sell_headroom = self.MAX_EMERALD_POS + pos  # how much short room left

                bid_qty = min(self.EMERALD_LOT, max(buy_headroom, 0))
                ask_qty = min(self.EMERALD_LOT, max(sell_headroom, 0))

                # Sanity check, never buy above the average and sell below
                if bid_qty > 0 and my_bid > fair:
                    orders.append(Order(product, my_bid, bid_qty))
                if ask_qty > 0 and my_ask < fair:
                    orders.append(Order(product, my_ask, -ask_qty))

            # ── TOMATOES ──────────────────────────────────────────────────────
            if product == 'TOMATOES':
                mid = self._mid(order_depth)
                if mid is not None:
                    tomato_prices.append(mid)
                    tomato_prices = tomato_prices[-self.TOMATO_WINDOW:]

                if len(tomato_prices) >= 5:
                    t_mean, t_std = self._rolling_stats(tomato_prices)
                else:
                    t_mean, t_std = self.TOMATO_DEFAULT_MEAN, self.TOMATO_DEFAULT_STD

                for price, quantity in order_depth.sell_orders.items():
                    z = (price - t_mean) / t_std

                    if z <= -self.TOMATO_THRES_BUY:
                        buy_qty = min(-quantity, self.MAX_TOMATO_POS + pos)

                        if buy_qty > 0:
                            orders.append(Order(product, price, buy_qty))

                for price, quantity in order_depth.buy_orders.items():
                    z = (price - t_mean) / t_std

                    if z >= self.TOMATO_THRES_SELL:
                        sell_qty = min(quantity, self.MAX_TOMATO_POS - pos)

                        if sell_qty > 0:
                            orders.append(Order(product, price, -sell_qty))

                buy_qty = self.MAX_TOMATO_POS - pos
                sell_qty = self.MAX_TOMATO_POS + pos

                orders.append(Order(product, self.TOMATO_CHEEKY_SCORE - 5, buy_qty))
                orders.append(Order(product, self.TOMATO_CHEEKY_SCORE + 5, -sell_qty))

            if product == 'INTARIAN_PEPPER_ROOT':
                continue

            if product == 'ASH_COATED_OSMIUM':
                mid = self._mid(order_depth)
                fair = self.ASH_COATED_OSMIUM_FAIR_VAL

                # if mid is not None and mid != fair:
                #     # Dislocation: market at 9996 or 10004
                #     # Skew quotes back toward fair but keep minimum edge
                #     skew = int(round(fair - mid))
                #     my_bid = fair - self.ASH_COATED_OSMIUM_BID_OFFSET + skew
                #     my_ask = fair + self.ASH_COATED_OSMIUM_ASK_OFFSET + skew
                #     # BUG 2 FIX: hard-floor so we always have at least 1pt edge
                #     my_bid = min(my_bid, fair - 1)
                #     my_ask = max(my_ask, fair + 1)
                # else:
                #     my_bid = fair - self.ASH_COATED_OSMIUM_BID_OFFSET  # 9998
                #     my_ask = fair + self.ASH_COATED_OSMIUM_ASK_OFFSET  # 10002
                #
                # # Inventory skew: nudge quotes to reduce position risk
                # inv_skew = -int(round(pos * 0.1))
                # my_bid += inv_skew
                # my_ask += inv_skew

                # BUG 1 FIX: size each quote so it cannot breach the position limit
                buy_headroom = self.MAX_ASH_COATED_OSMIUM_POS - pos  # how much long room left
                sell_headroom = self.MAX_ASH_COATED_OSMIUM_POS + pos  # how much short room left

                bid_qty = min(self.ASH_COATED_OSMIUM_LOT, max(buy_headroom, 0))
                ask_qty = min(self.ASH_COATED_OSMIUM_LOT, max(sell_headroom, 0))

                # Sanity check, never buy above the average and sell below
                if bid_qty > 0:
                    orders.append(Order(product, fair + self.ASH_COATED_OSMIUM_BID_OFFSET, bid_qty))
                if ask_qty > 0:
                    orders.append(Order(product, fair - self.ASH_COATED_OSMIUM_ASK_OFFSET, -ask_qty))

            result[product] = orders

        trader_data["tomato_prices"] = tomato_prices
        return result, 0, jsonpickle.encode(trader_data)
