import time
import uuid
import random
from typing import List, Dict, Tuple
from core.models import Order, PlayerState, Factory
import config

class GameEngine:
    def __init__(self):
        self.orders: List[Order] = []
        self.market_prices: Dict[str, int] = {k: v["base_price"] for k, v in config.ITEMS.items()}
        self.current_event = config.EVENTS_DB[0] 
        self.active_gov_event = None 
        self.gov_orders: List[Order] = []        
        
    # --- Phase 1: News & Event Generation ---
    def generate_daily_event(self, turn: int):
        # 1. 一般新聞事件
        self.current_event = config.get_random_event()
        
        # 2. 政府收購案檢定
        self.active_gov_event = None # 重置
        
        # 判定階段
        stage = "Early"
        chance = 0.25
        if turn >= 4: 
            stage = "Mid"
            chance = 0.50
        if turn >= 7: 
            stage = "Late"
            chance = 0.75
            
        # 骰子檢定
        if random.random() < chance:
            # 篩選符合當前階段的收購案
            candidates = [e for e in config.GOV_ACQUISITIONS if e["phase_req"] == stage]
            if candidates:
                self.active_gov_event = random.choice(candidates)
                print(f"[事件] 政府收購觸發：{self.active_gov_event['title']}")

        return self.current_event

    # --- Phase 2: Production ---
    def process_production(self, player: PlayerState, factory_id: str, target_item: str, quantity: int) -> Tuple[bool, str]:
        factory = next((f for f in player.factories if f.id == factory_id), None)
        if not factory: return False, "找不到工廠。"
        
        item_info = config.ITEMS.get(target_item)
        if not item_info: return False, "無效的物品。"

        if "Miner" in factory.name:
            if factory.has_produced: return False, "本回合已使用過採集器。"
            if item_info["tier"] != 0: return False, "採集器只能開採原料。"
            base_output = config.MINER_OUTPUTS.get(factory.tier, 3)
            player.inventory[target_item] = player.inventory.get(target_item, 0) + base_output
            factory.has_produced = True
            return True, f"成功開採 {base_output} 個 {target_item}。"
        else:
            if quantity <= 0: return False, "數量必須大於 0。"
            if factory.tier < item_info["tier"]: return False, "工廠等級不足。"
            recipe = item_info.get("recipe", {})
            for ing, qty_needed in recipe.items():
                if player.inventory.get(ing, 0) < (qty_needed * quantity): return False, f"原料 {ing} 不足。"
            for ing, qty_needed in recipe.items():
                player.inventory[ing] -= (qty_needed * quantity)
            player.inventory[target_item] = player.inventory.get(target_item, 0) + quantity
            return True, f"成功生產 {quantity} 個 {target_item}。"

    # --- Phase 2: Construction ---
    def process_build_new(self, player: PlayerState, target_tier: int, materials: List[str]) -> Tuple[bool, str]:
        if len(player.factories) >= player.land_limit: return False, "土地不足。"

        if target_tier == 0:
            cost = 500
            if player.money < cost: return False, "現金不足 (需要 $500)。"
            player.money -= cost
            player.factories.append(Factory(id=str(uuid.uuid4())[:8], tier=0, name="Miner"))
            return True, "成功建造採集器。"

        if target_tier == 1:
            rule = config.BUILD_T1_COST
            needed_count = rule["unique_types"]
            if len(materials) < needed_count: return False, f"請選擇 {needed_count} 種材料。"
            used_materials = materials[:needed_count]
            if len(set(used_materials)) != needed_count: return False, "材料必須不同。"
            for mat in used_materials:
                if config.ITEMS[mat]["tier"] != rule["material_tier"]: return False, f"{mat} 等級錯誤。"
                if player.inventory.get(mat, 0) < rule["qty_per_type"]: return False, f"需要 {rule['qty_per_type']} 個 {mat}。"
            for mat in used_materials:
                player.inventory[mat] -= rule["qty_per_type"]
            player.factories.append(Factory(id=str(uuid.uuid4())[:8], tier=1, name="Factory"))
            return True, "成功建造 T1 加工廠。"
        return False, "未知的建造類型。"

    # --- Phase 2: Upgrade ---
    def process_upgrade(self, player: PlayerState, factory_id: str, materials: List[str]) -> Tuple[bool, str]:
        factory = next((f for f in player.factories if f.id == factory_id), None)
        if not factory: return False, "找不到工廠。"
        
        if "Miner" in factory.name:
            rule = config.MINER_UPGRADE_RULES.get(factory.tier)
            if not rule: return False, "採集器已達最高等級。"
            if not rule["complex"]:
                if len(materials) < 1: return False, "請選擇 1 種材料。"
                mat = materials[0]
                if config.ITEMS[mat]["tier"] != rule["req_tier"]: return False, "材料等級錯誤。"
                if player.inventory.get(mat, 0) < rule["qty"]: return False, "材料數量不足。"
                player.inventory[mat] -= rule["qty"]
            else:
                if len(materials) < 2: return False, "請選擇 2 種材料。"
                mat_A, mat_B = materials[0], materials[1]
                if config.ITEMS[mat_A]["tier"] != 2 or player.inventory.get(mat_A, 0) < 3: return False, "需要 3 個 T2 材料。"
                if config.ITEMS[mat_B]["tier"] != 1 or player.inventory.get(mat_B, 0) < 3: return False, "需要 3 個 T1 材料。"
                player.inventory[mat_A] -= 3; player.inventory[mat_B] -= 3
            factory.tier += 1
            return True, f"採集器升級至 T{factory.tier}！"

        if factory.tier == 1:
            rule = config.UPGRADE_TO_T2
            if player.money < rule["money"]: return False, f"現金不足 (需要 ${rule['money']})。"
            if len(materials) < rule["unique_types"]: return False, "請選擇材料。"
            used_materials = materials[:rule["unique_types"]]
            if len(set(used_materials)) != rule["unique_types"]: return False, "材料必須不同。"
            for mat in used_materials:
                if config.ITEMS[mat]["tier"] != rule["material_tier"]: return False, "材料等級錯誤。"
                if player.inventory.get(mat, 0) < rule["qty_per_type"]: return False, "材料數量不足。"
            player.money -= rule["money"]
            for mat in used_materials: player.inventory[mat] -= rule["qty_per_type"]
            factory.tier = 2
            return True, "成功升級至 T2 工廠！"

        if factory.tier == 2:
            cost = config.UPGRADE_TO_T3_MONEY
            if player.money < cost: return False, f"現金不足 (需要 ${cost})。"
            if len(materials) < 3: return False, "請選擇 3 種材料。"
            used_materials = materials[:3]
            t2 = [m for m in used_materials if config.ITEMS[m]["tier"] == 2]
            t1 = [m for m in used_materials if config.ITEMS[m]["tier"] == 1]
            if len(set(t2)) != 2 or len(t1) != 1: return False, "需要 2 種不同的 T2 和 1 種 T1。"
            for m in t2:
                if player.inventory.get(m, 0) < 3: return False, "需要 3 個 T2 材料。"
            for m in t1:
                if player.inventory.get(m, 0) < 10: return False, "需要 10 個 T1 材料。"
            player.money -= cost
            for m in t2: player.inventory[m] -= 3
            for m in t1: player.inventory[m] -= 10
            factory.tier = 3
            return True, "成功升級至 T3 工廠！"
        return False, "已達最高等級。"

    # --- Phase 2: Demolish (NEW) ---
    def process_demolish(self, player: PlayerState, factory_id: str) -> Tuple[bool, str]:
        factory = next((f for f in player.factories if f.id == factory_id), None)
        if not factory: return False, "找不到該設施。"

        # 計算拆除費用 (Updated: T2=1000, T3=4000)
        demolish_fee = 0
        
        if "Miner" in factory.name:
            demolish_fee = 250 
        else:
            if factory.tier == 1:
                demolish_fee = 500
            elif factory.tier == 2:
                demolish_fee = 1000  # <--- 新費率
            elif factory.tier == 3:
                demolish_fee = 4000  # <--- 新費率
        
        if player.money < demolish_fee:
            return False, f"現金不足！拆除需支付清潔費 ${demolish_fee}。"

        player.money -= demolish_fee
        player.factories.remove(factory)
        
        return True, f"已拆除 {factory.name} (Lv.{factory.tier})，支付清潔費 ${demolish_fee}。"

    # --- Phase 2: Bank System ---
    def process_bank_sell(self, player: PlayerState, item_id: str, qty: int) -> Tuple[bool, str]:
        if qty <= 0: return False, "數量必須大於 0"
        if player.inventory.get(item_id, 0) < qty: return False, "庫存不足"
        
        # 價格計算：市價 * 0.85
        market_p = self.market_prices.get(item_id, config.ITEMS[item_id]["base_price"])
        bank_price = int(market_p * config.BANK_BUY_RATIO)
        
        total_gain = bank_price * qty
        
        # 執行交易
        player.inventory[item_id] -= qty
        player.money += total_gain
        
        return True, f"銀行回收成功：出售 {qty} 個 {item_id}，獲得 ${total_gain}"

    # --- Phase 3: Trading ---
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

    # --- Phase 4: Settlement (UPDATED) ---
    def execute_call_auction(self, players: Dict[str, PlayerState]):
        print("\n=== 結算開始 ===")
        
        # 1. 優先處理政府收購 (Gov Execution)
        if self.active_gov_event and self.gov_orders:
            self._execute_gov_auction(players)
            
        # 2. 處理一般市場撮合
        item_orders = {}
        for order in self.orders:
            if order.item_id not in item_orders: item_orders[order.item_id] = []
            item_orders[order.item_id].append(order)

        for item_id, orders in item_orders.items():
            bids = [o for o in orders if o.type == "BID"]
            asks = [o for o in orders if o.type == "ASK"]
            
            # Call Auction Logic
            clearing_price, volume = self._calc_price(bids, asks, item_id)
            print(f"{item_id}: 結算價 ${clearing_price}, 成交量 {volume}")
            
            if volume > 0:
                self.market_prices[item_id] = clearing_price # Update market price
                self._settle(players, bids, asks, clearing_price, volume, item_id)
            else:
                # No trade, just refund
                self._settle(players, bids, asks, clearing_price, 0, item_id)
        
        # 清空所有訂單
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

    def _execute_gov_auction(self, players):
        print(f"--- 政府收購: {self.active_gov_event['title']} ---")
        event = self.active_gov_event
        
        # Group gov orders by item
        orders_by_item = {}
        for order in self.gov_orders:
            if order.item_id not in orders_by_item: orders_by_item[order.item_id] = []
            orders_by_item[order.item_id].append(order)
            
        for item_id, orders in orders_by_item.items():
            # Sort: Lowest Price First (Reverse Auction), then Earliest Time
            sorted_orders = sorted(orders, key=lambda x: (x.price, x.timestamp))
            
            # Get Limits
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
            
            for order in sorted_orders:
                p_id = order.player_id
                player = players[p_id]
                current_p_filled = player_filled_counts.get(p_id, 0)
                
                # Calculate fillable amount
                can_fill = order.quantity
                if event["limit_type"] != "PLAYER": # Apply global limit check
                    can_fill = min(can_fill, global_limit - filled_global)
                can_fill = min(can_fill, player_limit - current_p_filled)
                
                if can_fill > 0:
                    revenue = can_fill * order.price
                    
                    # Execute Trade
                    player.locked_inventory[item_id] -= can_fill
                    player.money += revenue
                    print(f"政府收購: {player.name} 出售 {can_fill} 個 {item_id} @ ${order.price}")
                    
                    filled_global += can_fill
                    player_filled_counts[p_id] = current_p_filled + can_fill
                    
                    # Refund remaining (partially filled)
                    remain = order.quantity - can_fill
                    if remain > 0:
                        player.locked_inventory[item_id] -= remain
                        player.inventory[item_id] = player.inventory.get(item_id, 0) + remain
                else:
                    # Fully rejected (Limit reached)
                    player.locked_inventory[item_id] -= order.quantity
                    player.inventory[item_id] = player.inventory.get(item_id, 0) + order.quantity

    def _calc_price(self, bids: List[Order], asks: List[Order], item_id: str) -> Tuple[int, int]:
        if not bids or not asks: return self.market_prices[item_id], 0
        
        # 1. Collect all price nodes (from both bids and asks)
        prices = sorted(list(set([o.price for o in bids] + [o.price for o in asks])))
        
        max_vol = 0
        best_price = self.market_prices[item_id]
        candidates = []

        # 2. Cumulative Calculation
        for p in prices:
            # Demand: Buy at P or higher
            demand = sum(o.quantity for o in bids if o.price >= p)
            # Supply: Sell at P or lower
            supply = sum(o.quantity for o in asks if o.price <= p)
            
            # 3. Tradable Volume
            vol = min(demand, supply)
            
            if vol > max_vol:
                max_vol = vol
                candidates = [p]
            elif vol == max_vol and vol > 0:
                candidates.append(p)
        
        if max_vol == 0:
            return best_price, 0

        # 4. Boundary Condition: Closest to last price
        last_p = self.market_prices[item_id]
        candidates.sort(key=lambda x: abs(x - last_p))
        best_price = candidates[0]
        
        return best_price, max_vol

    def _settle(self, players, bids, asks, price, volume, item_id):
        valid_bids = sorted([b for b in bids if b.price >= price], key=lambda x: (-x.price, x.timestamp))
        valid_asks = sorted([a for a in asks if a.price <= price], key=lambda x: (x.price, x.timestamp))
        
        filled = 0
        b_idx = 0
        a_idx = 0
        
        while filled < volume and b_idx < len(valid_bids) and a_idx < len(valid_asks):
            bid = valid_bids[b_idx]
            ask = valid_asks[a_idx]
            
            trade_amt = min(bid.quantity, ask.quantity, volume - filled)
            
            # Buyer
            buyer = players[bid.player_id]
            actual_cost = trade_amt * price
            locked_funds = trade_amt * bid.price
            buyer.locked_money -= locked_funds
            buyer.money += (locked_funds - actual_cost)
            buyer.inventory[item_id] = buyer.inventory.get(item_id, 0) + trade_amt
            
            # Seller
            seller = players[ask.player_id]
            seller.locked_inventory[item_id] -= trade_amt
            seller.money += actual_cost
            
            bid.quantity -= trade_amt
            ask.quantity -= trade_amt
            filled += trade_amt
            
            if bid.quantity == 0: b_idx += 1
            if ask.quantity == 0: a_idx += 1

        # Refund remaining
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