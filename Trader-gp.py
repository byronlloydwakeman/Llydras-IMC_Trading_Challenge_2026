import math
from datamodel import OrderDepth, TradingState, Order
from typing import List
import jsonpickle


class Trader:
    # ── EMERALD parameters ────────────────────────────────────────────────────
    EMERALD_FAIR_VAL = 10000
    EMERALD_BID_OFFSET = 3
    EMERALD_ASK_OFFSET = 3
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

    # ── ASH_COATED_OSMIUM parameters ──────────────────────────────────────────
    ASH_COATED_OSMIUM_FAIR_VAL = 10000
    ASH_COATED_OSMIUM_BID_OFFSET = 3
    ASH_COATED_OSMIUM_ASK_OFFSET = 3
    ASH_COATED_OSMIUM_LOT = 10
    MAX_ASH_COATED_OSMIUM_POS = 20

    # ── INTARIAN_PEPPER_ROOT parameters ───────────────────────────────────────
    MAX_INTARIAN_PEPPER_ROOT_POS = 20
    INTARIAN_PEPPER_ROOT_LOT = 10
    INTARIAN_TAKE_THRESHOLD = 6

    # ✅ NEW: configurable alpha knobs
    INTARIAN_OBI_WEIGHT = 3.0
    INTARIAN_INVENTORY_WEIGHT = 0.5
    INTARIAN_SPREAD_BASE = 2
    INTARIAN_SPREAD_POS_FACTOR = 10  # widen spread every N inventory

    # ─────────────────────────────────────────────────────────────────────────

    def _mid(self, order_depth: OrderDepth):
        if not order_depth.buy_orders or not order_depth.sell_orders:
            return None
        return (max(order_depth.buy_orders) + min(order_depth.sell_orders)) / 2.0

    def _obi(self, order_depth: OrderDepth, level: int = 1):
        bid_prices = sorted(order_depth.buy_orders.keys(), reverse=True)
        ask_prices = sorted(order_depth.sell_orders.keys())

        if len(bid_prices) < level or len(ask_prices) < level:
            return 0.0

        bv = order_depth.buy_orders[bid_prices[level - 1]]
        av = -order_depth.sell_orders[ask_prices[level - 1]]

        total = bv + av
        return (bv - av) / total if total > 0 else 0.0

    def _rolling_stats(self, prices: list):
        n = len(prices)
        if n == 0:
            return self.TOMATO_DEFAULT_MEAN, self.TOMATO_DEFAULT_STD

        mean = sum(prices) / n
        if n < 2:
            return mean, self.TOMATO_DEFAULT_STD

        variance = sum((p - mean) ** 2 for p in prices) / (n - 1)
        std = math.sqrt(variance) if variance > 0 else self.TOMATO_DEFAULT_STD
        std = max(std, self.TOMATO_MIN_STD)

        return mean, std

    def run(self, state: TradingState):
        trader_data = jsonpickle.decode(state.traderData) if state.traderData else {}

        tomato_prices = trader_data.get("tomato_prices", [])
        result = {}

        for product, order_depth in state.order_depths.items():
            orders: List[Order] = []
            pos = state.position.get(product, 0)

            # ── EMERALDS (UNCHANGED, GOOD) ───────────────────────────────────
            if product == "EMERALDS":
                fair = self.EMERALD_FAIR_VAL

                my_bid = fair - self.EMERALD_BID_OFFSET
                my_ask = fair + self.EMERALD_ASK_OFFSET

                buy_qty = min(self.EMERALD_LOT, self.MAX_EMERALD_POS - pos)
                sell_qty = min(self.EMERALD_LOT, self.MAX_EMERALD_POS + pos)

                if buy_qty > 0:
                    orders.append(Order(product, my_bid, buy_qty))
                if sell_qty > 0:
                    orders.append(Order(product, my_ask, -sell_qty))

            # ── TOMATOES (UNCHANGED) ─────────────────────────────────────────
            if product == "TOMATOES":
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

            # ── ASH_COATED_OSMIUM (IMPROVED WITH OBI + COMPETITIVE QUOTES) ───
            if product == "ASH_COATED_OSMIUM":
                mid = self._mid(order_depth)
                if mid is None:
                    continue

                best_bid = max(order_depth.buy_orders)
                best_ask = min(order_depth.sell_orders)

                obi = self._obi(order_depth)

                # ✅ NEW: OBI + inventory skew
                fair = self.ASH_COATED_OSMIUM_FAIR_VAL
                fair += obi * 2
                fair -= pos * 0.3
                fair = int(round(fair))

                bid_price = min(fair - 2, best_bid + 1)
                ask_price = max(fair + 2, best_ask - 1)

                buy_qty = min(self.ASH_COATED_OSMIUM_LOT, self.MAX_ASH_COATED_OSMIUM_POS - pos)
                sell_qty = min(self.ASH_COATED_OSMIUM_LOT, self.MAX_ASH_COATED_OSMIUM_POS + pos)

                if buy_qty > 0:
                    orders.append(Order(product, int(bid_price), buy_qty))
                if sell_qty > 0:
                    orders.append(Order(product, int(ask_price), -sell_qty))

            # ── INTARIAN_PEPPER_ROOT (FULL HYBRID MODEL) ──────────────────────
            if product == "INTARIAN_PEPPER_ROOT":
                mid = self._mid(order_depth)
                if mid is None:
                    continue

                # ✅ NEW: correct trend base
                if "ipr_base" not in trader_data:
                    trader_data["ipr_base"] = mid - state.timestamp * 0.001

                base = trader_data["ipr_base"]
                trend_fair = base + state.timestamp * 0.001

                obi = self._obi(order_depth)

                # ✅ NEW: combined fair value
                fair_val = 0.7 * mid + 0.3 * trend_fair

                # ✅ NEW: OBI alpha
                fair_val += obi * self.INTARIAN_OBI_WEIGHT

                # ✅ NEW: inventory control
                fair_val -= pos * self.INTARIAN_INVENTORY_WEIGHT

                fair_val = int(round(fair_val))

                best_bid = max(order_depth.buy_orders)
                best_ask = min(order_depth.sell_orders)

                # ✅ NEW: adaptive spread
                spread = self.INTARIAN_SPREAD_BASE + int(abs(pos) / self.INTARIAN_SPREAD_POS_FACTOR)

                bid_price = min(fair_val - spread, best_bid + 1)
                ask_price = max(fair_val + spread, best_ask - 1)

                buy_qty = min(self.INTARIAN_PEPPER_ROOT_LOT, self.MAX_INTARIAN_PEPPER_ROOT_POS - pos)
                sell_qty = min(self.INTARIAN_PEPPER_ROOT_LOT, self.MAX_INTARIAN_PEPPER_ROOT_POS + pos)

                # ── PASSIVE ────────────────────────────────────────────────
                if buy_qty > 0:
                    orders.append(Order(product, int(bid_price), buy_qty))
                if sell_qty > 0:
                    orders.append(Order(product, int(ask_price), -sell_qty))

                # ── MEAN REVERSION (SMART) ────────────────────────────────
                for price, quantity in order_depth.sell_orders.items():
                    if price < fair_val - self.INTARIAN_TAKE_THRESHOLD and obi > -0.2:
                        buy_qty = min(-quantity, self.MAX_INTARIAN_PEPPER_ROOT_POS - pos)
                        if buy_qty > 0:
                            orders.append(Order(product, int(price), buy_qty))

                for price, quantity in order_depth.buy_orders.items():
                    if price > fair_val + self.INTARIAN_TAKE_THRESHOLD and obi < 0.2:
                        sell_qty = min(quantity, self.MAX_INTARIAN_PEPPER_ROOT_POS + pos)
                        if sell_qty > 0:
                            orders.append(Order(product, int(price), -sell_qty))

            result[product] = orders

        trader_data["tomato_prices"] = tomato_prices
        return result, 0, jsonpickle.encode(trader_data)