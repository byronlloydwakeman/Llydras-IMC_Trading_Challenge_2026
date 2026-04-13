import json
import math

from datamodel import OrderDepth, UserId, TradingState, Order
from typing import List
import string
import jsonpickle

class Trader:
    MAX_EMERALD_POSITIONS = 20  # So we don't get burnt on one side
    EMERALD_FAIR_VAL = 10000
    EMERALD_TICK_RANGE = 3

    MAX_TOMATO_POSITION = 10
    TOMATO_ROLLING_WINDOW = 50
    TOMATO_DEFAULT_MEAN = 4992.571951219512
    TOMATO_DEFAULT_STD = 21.1304672973115
    TOMATO_MIN_STD = 5.0

    TOMATO_Z_BUY = 0.8 # frmo 0.5
    TOMATO_Z_SELL = 0.8# from 0.5
    TOMATO_SPREAD = 1

    INVENTORY_SKEW = 0.5

    def bid(self) -> int:
        return 15

    def get_mid_price(self, order_depth: OrderDepth) -> float | None:
        if not order_depth.buy_orders or not order_depth.sell_orders:
            return None
        return (max(order_depth.buy_orders.keys()) + max(order_depth.sell_orders.keys())) / 2.0

    def calc_rolling_mean(self, prices: list) -> float:
        return sum(prices) / len(prices)

    def calc_rolling_std(self, prices: list, mean: float, default: float) -> float:
        if len(prices) < 2:
            return 0.0
        variance = sum((p - mean) * 2 for p in prices) / (len(prices) - 1)
        if variance > 0:
            return math.sqrt(variance)
        else:
            return default

    def run(self, state: TradingState):

        trader_data = jsonpickle.decode(state.traderData) if state.traderData else {}

        # Rolling mid price of tomatoes
        tomato_prices: list = trader_data.get("tomato_prices", [])

        result = {}
        for product, order_depth in state.order_depths.items():
            orders: List[Order] = []

            current_position = state.position.get(product, 0)

            if product == "EMERALDS":
                orders: List[Order] = []

                # Because emerald is so stable, we can become a market maker
                my_bid = self.EMERALD_FAIR_VAL - self.EMERALD_TICK_RANGE
                my_ask = self.EMERALD_FAIR_VAL + self.EMERALD_TICK_RANGE

                current_position = state.position.get(product, 0)

                # Don't buy if already at max long
                if current_position < self.MAX_EMERALD_POSITIONS:
                    orders.append(Order(product, my_bid, +10))

                # Don't sell if already at max short
                if current_position > -self.MAX_EMERALD_POSITIONS:
                    orders.append(Order(product, my_ask, -10))
                result[product] = orders

            if product == 'TOMATOES':
                mid = self.get_mid_price(order_depth)
                if mid is not None:
                    tomato_prices.append(mid)
                    if len(tomato_prices) > self.TOMATO_ROLLING_WINDOW:
                        # Baso saying get the last 50 elements of the tomato's mid point price
                        tomato_prices = tomato_prices[-self.TOMATO_ROLLING_WINDOW:]

                if len(tomato_prices) >= 5:
                    t_mean = self.calc_rolling_mean(tomato_prices)
                    t_std = self.calc_rolling_std(tomato_prices, t_mean, self.TOMATO_DEFAULT_STD)
                    t_std = max(t_std, self.TOMATO_MIN_STD)
                else:
                    t_mean = self.TOMATO_DEFAULT_MEAN
                    t_std = self.TOMATO_DEFAULT_STD

                # So we buy less when we have more of it, and buy more when we have less
                inv_weighting = -current_position * self.INVENTORY_SKEW
                adjusted_mean = t_mean + inv_weighting

                buy_cap = self.MAX_TOMATO_POSITION - current_position
                sell_cap = self.MAX_TOMATO_POSITION + current_position

                # Sort so that we're buying cheapest
                for price in sorted(order_depth.sell_orders.keys()):
                    if buy_cap <= 0:
                        break
                    # Does this make sense?
                    z = (price - adjusted_mean) / t_std
                    if z <= -self.TOMATO_Z_BUY:
                        # Negative so it becomes positive
                        available = -order_depth.sell_orders[price]
                        qty = min(available, buy_cap)
                        if qty > 0:
                            orders.append( Order(product, price, qty) )
                            buy_cap -= qty

                # Sort so we're selling to the most expensive
                for price in sorted(order_depth.buy_orders.keys(), reverse=True):
                    if sell_cap <= 0:
                        break
                    z = (price - adjusted_mean) / t_std
                    if z >= self.TOMATO_Z_SELL:
                        available = order_depth.buy_orders[price]
                        qty = min(available, sell_cap)
                        if qty > 0:
                            orders.append(Order(product, price, -qty))
                            sell_cap -= qty

                # Also do fair bids as a side hustle
                # side_bid = int(round(adjusted_mean - self.TOMATO_SPREAD))
                # side_ask = int(round(adjusted_mean + self.TOMATO_SPREAD))
                #
                # if buy_cap > 0:
                #     orders.append(Order(product, side_bid, buy_cap))
                # if sell_cap > 0:
                #     orders.append(Order(product, side_ask, sell_cap))


            result[product] = orders

        trader_data["tomato_prices"] = tomato_prices
        trader_data_str = jsonpickle.encode(trader_data)

        return result, 0, trader_data_str