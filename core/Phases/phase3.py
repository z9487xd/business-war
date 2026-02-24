import time
from typing import Tuple
from core.models import Order, PlayerState
import config

class Phase3Trading:
    def validate_and_lock_assets(self, player: PlayerState, order: Order) -> Tuple[bool, str]:
        if order.quantity <= 0: return False, "數量必須大於 0。"
        
        current_price = self.market_prices.get(order.item_id, 500)
        
        # 一般市場的波幅檢查
        if order.type != "GOV_ASK":
            max_p = int(current_price * (1 + config.PRICE_FLUCTUATION_LIMIT))
            min_p = int(current_price * (1 - config.PRICE_FLUCTUATION_LIMIT))
            if order.price > max_p or order.price < min_p: return False, f"價格超出限制 (${min_p} ~ ${max_p})"
        
        # 政府訂單的檢查已在 main.py 中進行
        
        if order.type == "BID":
            cost = order.price * order.quantity
            if player.money < cost: return False, "現金不足。"
            player.money -= cost; player.locked_money += cost
        else: # ASK or GOV_ASK
            if player.inventory.get(order.item_id, 0) < order.quantity: return False, "庫存不足。"
            player.inventory[order.item_id] -= order.quantity
            player.locked_inventory[order.item_id] = player.locked_inventory.get(order.item_id, 0) + order.quantity
            
        order.timestamp = time.time()
        print(f"[訂單] {player.name} {order.type} {order.quantity}個 {order.item_id} @ ${order.price}")
        return True, "成功"