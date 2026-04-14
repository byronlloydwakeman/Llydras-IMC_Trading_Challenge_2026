from datamodel import OrderDepth, UserId, TradingState, Order
from typing import List
import string
import jsonpickle


class Trader:

    def bid(self) -> int:
        return 15

    def run(self, state: TradingState):
        MAX_EMERALD_POSITIONS = 20  # So we don't get burnt on one side
        EMERALD_FAIR_VAL = 10000
        EMERALD_TICK_RANGE = 3

        MAX_TOMATO_POSITION = 10

        EMERALD_MEAN = 9999.799499

        TOMATO_MEAN = 4992.571951219512
        TOMATO_STD = 21.1304672973115

        thres_buy = 0.067582
        thres_sell = 0.05

        buy_price_em = int(EMERALD_MEAN - 1)
        sell_price_em = int(EMERALD_MEAN + 1)

        buy_price = int(TOMATO_MEAN - 1)
        sell_price = int(TOMATO_MEAN + 1)

        result = {}
        for product, order_depth in state.order_depths.items():
            orders: List[Order] = []

            current_position = state.position.get(product, 0)

            if product == "EMERALDS":
                orders: List[Order] = []

                # Because emerald is so stable, we can become a market maker
                my_bid = EMERALD_FAIR_VAL - EMERALD_TICK_RANGE
                my_ask = EMERALD_FAIR_VAL + EMERALD_TICK_RANGE

                current_position = state.position.get(product, 0)

                # Don't buy if already at max long
                if current_position < MAX_EMERALD_POSITIONS:
                    orders.append(Order(product, my_bid, +10))

                # Don't sell if already at max short
                if current_position > -MAX_EMERALD_POSITIONS:
                    orders.append(Order(product, my_ask, -10))
                result[product] = orders

            if product == 'TOMATOES':
                for price, quantity in order_depth.sell_orders.items():
                    z = (price - TOMATO_MEAN) / TOMATO_STD

                    if z <= -thres_buy:
                        buy_qty = min(-quantity, MAX_TOMATO_POSITION + current_position)

                        if buy_qty > 0:
                            orders.append(Order(product, price, buy_qty))

                for price, quantity in order_depth.buy_orders.items():
                    z = (price - TOMATO_MEAN) / TOMATO_STD

                    if z >= thres_sell:
                        sell_qty = min(quantity, MAX_TOMATO_POSITION - current_position)

                        if sell_qty > 0:
                            orders.append(Order(product, price, -sell_qty))

                buy_qty = MAX_TOMATO_POSITION - current_position
                sell_qty = MAX_TOMATO_POSITION + current_position

                orders.append(Order(product, buy_price, buy_qty))
                orders.append(Order(product, sell_price, -sell_qty))

            result[product] = orders

        return result, 0, ''