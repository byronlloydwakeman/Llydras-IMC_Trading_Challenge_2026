from datamodel import OrderDepth, UserId, TradingState, Order
from typing import List
import string
import jsonpickle


class Trader:

    def bid(self):
        return 15

    def run(self, state: TradingState):
        """Only method required. It takes all buy and sell orders for all
        symbols as an input, and outputs a list of orders to be sent."""

        # Data setup
        trader_data = jsonpickle.decode(state.traderData) if state.traderData else {}

        # CONSTS
        ## Emerald
        MAX_EMERALD_POSITIONS = 20  # So we don't get burnt on one side
        EMERALD_FAIR_VAL = 10000
        EMERALD_TICK_RANGE = 3

        ## Tomato
        MAX_TOMATO_WINDOW_LENGTH = 10
        TOMATO_STRONG_BUY_THRES = 0.4
        TOMATO_WEAK_BUY_THRES = 0.1
        TOMATO_STRONG_SELL_THRES = -0.4


        # Orders to be placed on exchange matching engine
        result = {}
        for product in state.order_depths:
            # Trading data setup
            order_depth: OrderDepth = state.order_depths[product]

            if product == "EMERALDS":
                orders: List[Order] = []

                # Because emerald is so stable, we can become a market maker
                my_bid = EMERALD_FAIR_VAL - EMERALD_TICK_RANGE  # 9997 — you offer to buy here
                my_ask = EMERALD_FAIR_VAL + EMERALD_TICK_RANGE  # 10003 — you offer to sell here

                current_position = state.position.get(product, 0)

                # Don't buy if already at max long
                if current_position < MAX_EMERALD_POSITIONS:
                    orders.append(Order(product, my_bid, +10))

                # Don't sell if already at max short
                if current_position > -MAX_EMERALD_POSITIONS:
                    orders.append(Order(product, my_ask, -10))
                result[product] = orders

            elif product == "TOMATOES":
                orders: List[Order] = []
                # Strategy
                # Mean reversion with Order Book Inbalance

                if "raw_imbalance" not in trader_data.keys():
                    trader_data["raw_imbalance"] = {product: []}


                bid_vol = sum(order_depth.buy_orders.values())
                ask_vol = sum(order_depth.sell_orders.values())  # these are negative in IMC, so abs()
                raw_imbalance = (bid_vol - abs(ask_vol)) / (bid_vol + abs(ask_vol))

                # Smoothed imbalance — store history in traderData
                trader_data["raw_imbalance"][product].append(raw_imbalance)
                if len(trader_data["raw_imbalance"][product]) >= MAX_TOMATO_WINDOW_LENGTH:
                    trader_data["raw_imbalance"][product].pop(0)

                smoothed_imbalance = sum(trader_data["raw_imbalance"][product]) / len(trader_data["raw_imbalance"][product])

                best_bid, best_bid_amount = list(order_depth.buy_orders.items())[0]
                best_ask, best_ask_amount = list(order_depth.sell_orders.items())[0]

                if smoothed_imbalance > TOMATO_STRONG_BUY_THRES:  # strong buy pressure
                    orders.append(Order(product, best_ask, 10))
                elif smoothed_imbalance < TOMATO_STRONG_SELL_THRES:
                    orders.append(Order(product, best_bid, -10))

                result[product] = orders

        traderData = ""  # No state needed - we check position directly
        conversions = 0
        return result, conversions, traderData
