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
    MAX_ASH_COATED_OSMIUM_POS = 80
    ASH_COATED_OSMIUM_ROLLING_WINDOW = 50

    # ── INTARIAN_PEPPER_ROOT parameters ────────────────────────────────────────────────────
    MAX_INTARIAN_PEPPER_ROOT_POS = 80 # Other 40 is buy and hold
    INTARIAN_PEPPER_ROOT_CHANNEL_WIDTH = 7
    INTARIAN_PEPPER_ROOT_HOLD_LOT = 40
    INTARIAN_PEPPER_ROOT_LOT = 10

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

    def _rolling_stats(self, prices: list, default_mean, default_std):
        n = len(prices)
        if n == 0:
            return default_mean, default_std
        mean = sum(prices) / n
        if n < 2:
            return mean, default_std
        variance = sum((p - mean) ** 2 for p in prices) / (n - 1)
        std = math.sqrt(variance) if variance > 0 else default_std
        return max(std, default_std), mean

    def calc_rolling_mean(self, prices: list) -> float:
        return sum(prices) / len(prices)

    def run(self, state: TradingState):
        trader_data: dict = jsonpickle.decode(state.traderData) if state.traderData else {}

        tomato_prices: list = trader_data.get("tomato_prices", [])
        intarian_prices: list = trader_data.get("intarian_prices", [])
        ash_prices: list = trader_data.get("ash_prices", [])

        result = {}

        for product, order_depth in state.order_depths.items():
            orders: List[Order] = []
            pos = state.position.get(product, 0)

            if product == 'INTARIAN_PEPPER_ROOT':

                if "ipr_base" not in trader_data:
                    mid = self._mid(order_depth)
                    if mid:
                        trader_data["ipr_base"] = mid
                    else:
                        trader_data["ipr_base"] = sorted(order_depth.buy_orders.items())[0]

                base = trader_data["ipr_base"]
                trend_fair = base + state.timestamp * 0.001

                # 2. THE START: BUY AND HOLD until 'hold vol' reached
                if pos < self.INTARIAN_PEPPER_ROOT_HOLD_LOT and state.timestamp < 1000:
                    remaining_to_hold = self.INTARIAN_PEPPER_ROOT_HOLD_LOT - pos
                    # Walk the sell orders from cheapest to most expensive
                    for price, quantity in sorted(order_depth.sell_orders.items()):
                        if remaining_to_hold <= 0: break
                        buy_qty = min(abs(quantity), remaining_to_hold)
                        orders.append(Order(product, price, buy_qty))
                        remaining_to_hold -= buy_qty
                        pos += buy_qty  # Update local pos tracker
                else:
                    # 3. THE END: LIQUIDATE EVERYTHING (at final timestamp)
                    # Give ourselves 9 ticks to sell everything
                    if state.timestamp >= 995000:
                        if pos > 0:
                            remaining_to_sell = pos
                            # Walk the buy orders from highest to lowest price
                            for price, quantity in sorted(order_depth.buy_orders.items(), reverse=True):
                                if remaining_to_sell <= 0: break
                                sell_qty = min(abs(quantity), remaining_to_sell)
                                orders.append(Order(product, price, -sell_qty))
                                remaining_to_sell -= sell_qty
                    else:
                        # 1. Take liquidity if the residual is extreme (> 6 pts)
                        for price, quantity in order_depth.sell_orders.items():
                            residual = price - trend_fair
                            if residual <= -6.0:  # Price is 6 points below trend
                                buy_qty = min(-quantity, self.MAX_INTARIAN_PEPPER_ROOT_POS + pos)
                                if buy_qty > 0:
                                    # Minus one to capture micro arb
                                    orders.append(Order(product, price - 1, buy_qty))

                        for price, quantity in order_depth.buy_orders.items():
                            residual = price - trend_fair
                            if residual >= 6.0:  # Price is 6 points above trend
                                sell_qty = min(quantity, self.MAX_INTARIAN_PEPPER_ROOT_POS - pos)
                                if sell_qty > 0:
                                    # Buy one to capture micro arb
                                    orders.append(Order(product, price + 1, -sell_qty))


                        # 2. Add Market Making quotes around trend_fair
                        buy_headroom = self.MAX_INTARIAN_PEPPER_ROOT_POS - pos
                        sell_headroom = self.MAX_INTARIAN_PEPPER_ROOT_POS + pos

                        if buy_headroom > 0:
                            orders.append(Order(product, int(trend_fair - 2), min(self.INTARIAN_PEPPER_ROOT_LOT, buy_headroom)))
                        if sell_headroom > 0:
                            orders.append(
                                Order(product, int(trend_fair + 2), -min(self.INTARIAN_PEPPER_ROOT_LOT, sell_headroom)))

            if product == 'ASH_COATED_OSMIUM':
                mid = self._mid(order_depth)
                if mid is not None:
                    ash_prices.append(mid)
                    if len(ash_prices) > self.ASH_COATED_OSMIUM_ROLLING_WINDOW:
                        ash_prices = ash_prices[-self.ASH_COATED_OSMIUM_ROLLING_WINDOW:]

                mean = self.calc_rolling_mean(ash_prices)

                obi_level = self._obi(order_depth, 1)

                # Wide spread as per instructions
                my_bid = mean - self.ASH_COATED_OSMIUM_BID_OFFSET
                my_ask = mean + self.ASH_COATED_OSMIUM_ASK_OFFSET

                buy_headroom = self.MAX_ASH_COATED_OSMIUM_POS - pos
                sell_headroom = self.MAX_ASH_COATED_OSMIUM_POS + pos

                bid_qty = min(self.ASH_COATED_OSMIUM_LOT, max(buy_headroom, 0))
                ask_qty = min(self.ASH_COATED_OSMIUM_LOT, max(sell_headroom, 0))

                # Only post quotes if OBI agrees with the direction
                if bid_qty > 0:# and obi_level > 0:
                    orders.append(Order(product, int(my_bid), bid_qty))
                if ask_qty > 0:# and obi_level < 0:
                    orders.append(Order(product, int(my_ask), -ask_qty))

                # mid = self._mid(order_depth)
                # fair = self.ASH_COATED_OSMIUM_FAIR_VAL
                #
                # if mid is not None:
                #
                #     my_bid = mid - self.ASH_COATED_OSMIUM_BID_OFFSET
                #     my_ask = mid + self.ASH_COATED_OSMIUM_ASK_OFFSET
                #
                #     # # Inventory skew: nudge quotes to reduce position risk
                #     # inv_skew = int(round(
                #     #     pos * 0.5))  # So at a pos of 16, will reduce/increase by 8, the closer to 1 the more aggressive
                #     # my_bid -= inv_skew
                #     # my_ask += inv_skew
                #     #
                #     # obi_level = self._obi(order_depth, 1)
                #
                #     buy_headroom = self.MAX_ASH_COATED_OSMIUM_POS - pos  # how much long room left
                #     sell_headroom = self.MAX_ASH_COATED_OSMIUM_POS + pos  # how much short room left
                #
                #     bid_qty = min(self.ASH_COATED_OSMIUM_LOT, max(buy_headroom, 0))
                #     ask_qty = min(self.ASH_COATED_OSMIUM_LOT, max(sell_headroom, 0))
                #
                #     # Sanity check, never buy above the average and sell below
                #     if bid_qty > 0: # and obi_level > 0:
                #         orders.append(Order(product, my_bid, bid_qty))
                #     if ask_qty > 0: # > obi_level:
                #         orders.append(Order(product, my_ask, -ask_qty))

            result[product] = orders

        trader_data["tomato_prices"] = tomato_prices
        trader_data["intarian_prices"] = intarian_prices
        return result, 0, jsonpickle.encode(trader_data)
