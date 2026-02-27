import time
from typing import Tuple, List, Dict
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
        
        # 檢查與鎖定資產
        if order.type == "BID":
            cost = order.price * order.quantity
            if player.money < cost: return False, "現金不足。"
            player.money -= cost
            player.locked_money += cost
        else: # ASK or GOV_ASK
            if player.inventory.get(order.item_id, 0) < order.quantity: return False, "庫存不足。"
            player.inventory[order.item_id] -= order.quantity
            player.locked_inventory[order.item_id] = player.locked_inventory.get(order.item_id, 0) + order.quantity
            
        order.timestamp = time.time()
        
        # 移除 print，改由回傳成功訊息，讓外層的 main.py 負責寫入 Log
        success_msg = f"[掛單成功] {player.name} 掛出 {order.type}：{order.quantity} 個 {order.item_id} (單價 ${order.price})"
        return True, success_msg

    def match_market_orders(self, players: Dict[str, PlayerState]) -> List[str]:
        trade_logs = []
        # 加入訂單數量追蹤，確認系統到底有沒有收到單
        trade_logs.append(f"=== 一般市場交易撮合開始 (共收到 {len(self.orders)} 筆訂單) ===")
        
        items_traded = set(o.item_id for o in self.orders)
        
        for item in items_traded:
            # 將訂單分為買單與賣單
            bids = [o for o in self.orders if o.item_id == item and o.type == "BID"]
            asks = [o for o in self.orders if o.item_id == item and o.type == "ASK"]
            
            # 🌟 新增：如果某物品只有買或只有賣，明確印出缺乏對手盤
            if not bids or not asks:
                trade_logs.append(f"[{item} 撮合略過] 缺乏對手盤 (買單: {len(bids)} 筆, 賣單: {len(asks)} 筆)，無法進行交易。")
                continue
            
            # 買單從高價排到低價，賣單從低價排到高價 (時間優先排序)
            bids.sort(key=lambda x: (-x.price, x.timestamp))
            asks.sort(key=lambda x: (x.price, x.timestamp))
            
            while bids and asks:
                bid = bids[0]
                ask = asks[0]
                
                # 最高買價 >= 最低賣價，則有機會成交
                if bid.price >= ask.price:
                    trade_price = ask.price # 依賣方開價成交
                    trade_qty = min(bid.quantity, ask.quantity)
                    
                    buyer = players.get(bid.player_id)
                    seller = players.get(ask.player_id)
                    
                    if not buyer or not seller:
                        break
                        
                    cost = trade_price * trade_qty
                    
                    # 嚴格檢查鎖定資產
                    buyer_can_afford = buyer.locked_money >= cost
                    seller_has_item = seller.locked_inventory.get(item, 0) >= trade_qty
                    
                    if buyer_can_afford and seller_has_item:
                        buyer.locked_money -= cost
                        buyer.inventory[item] = buyer.inventory.get(item, 0) + trade_qty
                        
                        seller.locked_inventory[item] -= trade_qty
                        seller.money += cost
                        
                        trade_logs.append(f"[撮合成交] {buyer.name} 向 {seller.name} 買入 {trade_qty} 個 {item} (單價: ${trade_price})")
                        
                        bid.quantity -= trade_qty
                        ask.quantity -= trade_qty
                        if bid.quantity <= 0: bids.pop(0)
                        if ask.quantity <= 0: asks.pop(0)
                        
                    else:
                        if not buyer_can_afford:
                            trade_logs.append(f"[撮合失敗] {buyer.name} 向 {seller.name} 購買 {item} 失敗。原因：{buyer.name} 鎖定資金異常")
                            bids.pop(0)
                        if not seller_has_item:
                            trade_logs.append(f"[撮合失敗] {buyer.name} 向 {seller.name} 購買 {item} 失敗。原因：{seller.name} 鎖定庫存異常")
                            asks.pop(0)
                else:
                    trade_logs.append(f"[{item} 撮合結束] 最高買價 (${bid.price}) 低於 最低賣價 (${ask.price})，無法達成交易共識。")
                    break
                    
        trade_logs.append("=== 一般市場交易撮合結束 ===")
        return trade_logs