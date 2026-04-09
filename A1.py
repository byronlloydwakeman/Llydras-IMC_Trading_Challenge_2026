from datamodel import OrderDepth, UserId, TradingState, Order
from typing import List
import string
import jsonpickle

class Trader:
	
	def bid(self) -> int:
		return 15

	def run(self, state: TradingState):
		MAX_TOMATO_POSITION = 10

		TOMATO_MEAN = 4992.571951219512
		TOMATO_STD = 21.1304672973115

		thres_buy = 0.8 #0.067582
		thres_sell = 1 #0.05

		result = {}
		for product, order_depth in state.order_depths.items():
			orders: List[Order] = []

			current_position = state.position.get(product, 0)

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

			result[product] = orders

		return result, 0, ''