import random
from typing import List, Dict, Tuple
from core.models import Order, PlayerState
import config

class Phase4Settlement:
    def execute_call_auction(self, players: Dict[str, PlayerState]) -> List[str]:
        print("\n=== 結算開始 ===")
        match_logs = [] 
        
        # 1. 優先處理政府收購 (Gov Execution)
        if self.active_gov_event and self.gov_orders:
            gov_logs = self._execute_gov_auction(players)
            if gov_logs:
                match_logs.extend(gov_logs)
            
        # 2. 處理一般市場撮合
        item_orders = {}
        for order in self.orders:
            if order.item_id not in item_orders: item_orders[order.item_id] = []
            item_orders[order.item_id].append(order)

        for item_id, orders in item_orders.items():
            bids = [o for o in orders if o.type == "BID"]
            asks = [o for o in orders if o.type == "ASK"]
            
            clearing_price, volume = self._calc_price(bids, asks, item_id)
            print(f"{item_id}: 結算價 ${clearing_price}, 成交量 {volume}")
            
            item_name = config.ITEMS[item_id]['label']
            
            if volume > 0:
                self.market_prices[item_id] = clearing_price 
                match_logs.append(f"市場撮合：【{item_name}】結算價 ${clearing_price}，共成交 {volume} 個！")
                
                detailed_logs = self._settle(players, bids, asks, clearing_price, volume, item_id)
                if detailed_logs:
                    match_logs.extend(detailed_logs)
            else:
                self._settle(players, bids, asks, clearing_price, 0, item_id)
        
        self.orders = []
        self.gov_orders = []
        
        # Storage Penalty
        print("--- 庫存盤點 ---")
        for p in players.values():
            cp = sum(config.CP_VALUES.get(f.tier, 0) for f in p.factories)
            limit = config.BASE_STORAGE_LIMIT + cp
            for k, v in p.inventory.items():
                if v > limit:
                    excess = v - limit
                    penalty = 0
                    t1 = min(excess, 3); penalty += t1 * config.PENALTY_LOW
                    if excess > 3:
                        t2 = min(excess-3, 4); penalty += t2 * config.PENALTY_MID
                    if excess > 7:
                        t3 = excess - 7; penalty += t3 * config.PENALTY_HIGH
                    
                    if p.money < penalty:
                        print(f"罰款 {p.name}: {k} -${p.money} (觸發破產保護)")
                        p.money = 0
                    else:
                        p.money -= penalty
                        print(f"罰款 {p.name}: {k} -${penalty}")
        print("=== 結算完成 ===\n")
        
        return match_logs

    def _execute_gov_auction(self, players) -> List[str]:
        print(f"--- 政府收購: {self.active_gov_event['title']} ---")
        event = self.active_gov_event
        gov_logs = [] 
        
        orders_by_item = {}
        for order in self.gov_orders:
            if order.item_id not in orders_by_item: orders_by_item[order.item_id] = []
            orders_by_item[order.item_id].append(order)
            
        for item_id, orders in orders_by_item.items():
            sorted_orders = sorted(orders, key=lambda x: (x.price, x.timestamp))
            
            global_limit = 999999
            player_limit = 999999
            
            if event["limit_type"] == "GLOBAL":
                global_limit = event["limit"]
            elif event["limit_type"] == "PLAYER":
                player_limit = event["limit"]
            elif event["limit_type"] == "MIXED":
                global_limit = event["limits"].get(item_id, 999999)
            
            filled_global = 0
            player_filled_counts = {}
            item_name = config.ITEMS[item_id]['label']
            
            for order in sorted_orders:
                p_id = order.player_id
                player = players[p_id]
                current_p_filled = player_filled_counts.get(p_id, 0)
                
                can_fill = order.quantity
                if event["limit_type"] != "PLAYER": 
                    can_fill = min(can_fill, global_limit - filled_global)
                can_fill = min(can_fill, player_limit - current_p_filled)
                
                if can_fill > 0:
                    revenue = can_fill * order.price
                    
                    player.locked_inventory[item_id] -= can_fill
                    player.money += revenue
                    print(f"政府收購: {player.name} 出售 {can_fill} 個 {item_id} @ ${order.price}")
                    
                    gov_logs.append(f"🏛️ 政府得標：【{player.name}】成功向政府出售 {can_fill} 個 {item_name}，進帳 ${revenue}！")
                    
                    filled_global += can_fill
                    player_filled_counts[p_id] = current_p_filled + can_fill
                    
                    remain = order.quantity - can_fill
                    if remain > 0:
                        player.locked_inventory[item_id] -= remain
                        player.inventory[item_id] = player.inventory.get(item_id, 0) + remain
                else:
                    player.locked_inventory[item_id] -= order.quantity
                    player.inventory[item_id] = player.inventory.get(item_id, 0) + order.quantity
                    
        return gov_logs 

    def _calc_price(self, bids: List[Order], asks: List[Order], item_id: str) -> Tuple[int, int]:
        if not bids or not asks: return self.market_prices[item_id], 0
        
        prices = sorted(list(set([o.price for o in bids] + [o.price for o in asks])))
        
        max_vol = 0
        best_price = self.market_prices[item_id]
        candidates = []

        for p in prices:
            demand = sum(o.quantity for o in bids if o.price >= p)
            supply = sum(o.quantity for o in asks if o.price <= p)
            vol = min(demand, supply)
            
            if vol > max_vol:
                max_vol = vol
                candidates = [p]
            elif vol == max_vol and vol > 0:
                candidates.append(p)
        
        if max_vol == 0:
            return best_price, 0

        last_p = self.market_prices[item_id]
        candidates.sort(key=lambda x: abs(x - last_p))
        best_price = candidates[0]
        
        return best_price, max_vol

    def _settle(self, players, bids, asks, price, volume, item_id) -> List[str]:
        settle_logs = []
        item_name = config.ITEMS[item_id]['label'] 

        valid_bids = sorted([b for b in bids if b.price >= price], key=lambda x: (-x.price, x.timestamp))
        valid_asks = sorted([a for a in asks if a.price <= price], key=lambda x: (x.price, x.timestamp))
        
        filled = 0
        b_idx = 0
        a_idx = 0
        
        while filled < volume and b_idx < len(valid_bids) and a_idx < len(valid_asks):
            bid = valid_bids[b_idx]
            ask = valid_asks[a_idx]
            
            trade_amt = min(bid.quantity, ask.quantity, volume - filled)
            
            if trade_amt > 0:
                buyer = players[bid.player_id]
                actual_cost = trade_amt * price
                locked_funds = trade_amt * bid.price
                buyer.locked_money -= locked_funds
                buyer.money += (locked_funds - actual_cost)
                buyer.inventory[item_id] = buyer.inventory.get(item_id, 0) + trade_amt
                
                seller = players[ask.player_id]
                seller.locked_inventory[item_id] -= trade_amt
                seller.money += actual_cost
                
                settle_logs.append(f"【市場撮合】{buyer.name} 成功向 {seller.name} 購買 {trade_amt} 個 {item_name} (單價: ${price})")

                bid.quantity -= trade_amt
                ask.quantity -= trade_amt
                filled += trade_amt
            
            if bid.quantity == 0: b_idx += 1
            if ask.quantity == 0: a_idx += 1

        for b in bids:
            if b.quantity > 0:
                p = players[b.player_id]
                p.locked_money -= b.quantity * b.price
                p.money += b.quantity * b.price
        
        for a in asks:
            if a.quantity > 0:
                p = players[a.player_id]
                p.locked_inventory[item_id] -= a.quantity
                p.inventory[item_id] = p.inventory.get(item_id, 0) + a.quantity
                
        return settle_logs
    
    def process_end_of_turn(self, players: Dict[str, PlayerState]) -> List[str]:
        logs = []
        event = getattr(self, "current_event", {}) or {}
        
        # 1. 全域特殊事件 (例如：反壟斷法案)
        if event.get("type") == "SPECIAL" and event.get("logic_key") == "ROBIN_HOOD_TAX":
            sorted_players = sorted(players.values(), key=lambda x: x.money, reverse=True)
            top_3 = sorted_players[:3]
            others = sorted_players[3:]
            tax_pool = 0
            for tp in top_3:
                tax = int(tp.money * 0.3)
                tp.money -= tax
                tax_pool += tax
            if others and tax_pool > 0:
                share = tax_pool // len(others)
                for op in others: op.money += share
            logs.append(f"⚖️ 反壟斷法：前 3 名玩家扣除 30% 稅金共 ${tax_pool}，已平分給其餘玩家！")

        # 2. 結算每個玩家的【倉儲稅】與【事件懲罰】
        for p_id, p in players.items():
            player_logs = []
            
            capacity = 5
            for f in p.factories:
                if "Miner" in f.name: continue
                elif f.tier == 1: capacity += 3
                elif f.tier == 2: capacity += 6
                elif f.tier >= 3: capacity += 12
            
            tax_total = 0
            for item, qty in p.inventory.items():
                if qty > capacity:
                    excess = qty - capacity
                    if excess <= 3: tax_total += excess * 100
                    elif excess <= 7: tax_total += excess * 200
                    else: tax_total += excess * 500
                    
            if tax_total > 0:
                p.money -= tax_total
                player_logs.append(f"倉儲超載稅：扣除 ${tax_total}")

            has_defense = any(f.name == "Defense" for f in p.factories) 
            
            if event.get("type") == "DEFENSE_CHECK":
                req_item = event["req_item"]
                req_qty = event["req_qty"]
                
                if p.inventory.get(req_item, 0) >= req_qty:
                    p.inventory[req_item] -= req_qty
                    player_logs.append(f" 成功上繳 {req_qty} 個 {config.ITEMS[req_item]['label']} 抵禦災害！")
                elif has_defense:
                    player_logs.append(f" 防災中心啟動！完美抵禦了災害！")
                else:
                    penalty = event["penalty"]
                    if penalty == "SHUTDOWN_FACILITIES":
                        for f in p.factories: setattr(f, "is_shutdown", True) 
                        player_logs.append(" 災害命中：所有設施下回合停擺！")
                    elif penalty == "HALVE_CASH":
                        lost = p.money - int(p.money * 0.5)
                        p.money = int(p.money * 0.5)
                        player_logs.append(f" 災害命中：現金減半 (損失 ${lost})！")
                    elif penalty == "DESTROY_FACTORY":
                        if p.factories:
                            f_to_destroy = random.choice(p.factories)
                            p.factories.remove(f_to_destroy)
                            player_logs.append(f" 災害命中：{f_to_destroy.name} 被摧毀了！")

            elif event.get("type") == "SPECIAL" and event.get("logic_key") == "LAND_TAX_BEAM":
                if p.land_limit > 5:
                    if p.inventory.get("beam", 0) >= 7:
                        p.inventory["beam"] -= 7
                        player_logs.append(" 扣除 7 個工業鋼樑維護擴充的土地。")
                    else:
                        if p.factories:
                            f_to_destroy = random.choice(p.factories)
                            p.factories.remove(f_to_destroy)
                            player_logs.append(f" 鋼樑不足！擴充土地上的 {f_to_destroy.name} 崩塌了！")
            
            if p.money > 0:
                original_money = p.money
                p.money = int(p.money * 1.2)
                interest = p.money - original_money
                player_logs.append(f"資本複利：資產增長 20% (收益 +${interest:,})")

            if player_logs:
                logs.append(f"【{p.name}】 " + " | ".join(player_logs))                        
                
        return logs

    def game_set(self, players: Dict[str, PlayerState]) -> List[Tuple[str, dict]]:
        print("\n=== 遊戲結束，開始最終計分 ===")
        
        facility_values = {
            "Miner": {0: 200, 1: 500, 2: 2000, 3: 5000},
            "Factory": {0: 0, 1: 500, 2: 8000, 3: 18000}
        }
        
        final_scores = {}
        
        for p_id, player in players.items():
            inventory_value = 0
            for item_id, qty in player.inventory.items():
                if qty > 0:
                    market_price = self.market_prices.get(item_id, 0)
                    inventory_value += qty * market_price
                    
            facility_value = 0
            for factory in player.factories:
                f_type = "Miner" if "Miner" in factory.name else "Factory"
                facility_value += facility_values[f_type].get(factory.tier, 0)
                
            total_score = inventory_value + facility_value + player.money
            
            final_scores[player.name] = {
                "inventory_value": inventory_value,
                "facility_value": facility_value,
                "cash": player.money,
                "total_score": total_score
            }
            
        ranked_players = sorted(final_scores.items(), key=lambda x: x[1]["total_score"], reverse=True)
        
        for rank, (name, data) in enumerate(ranked_players, 1):
            print(f"第 {rank} 名: {name} | 總分: {data['total_score']} "
                  f"(現金: {data['cash']}, 庫存價值: {data['inventory_value']}, 設施價值: {data['facility_value']})")
            
        return ranked_players