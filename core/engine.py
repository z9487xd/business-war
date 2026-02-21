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
        # 1. 統一判斷當前階段與政府收購機率
        stage = "Early"
        gov_chance = 0.50  # 前期機率：50%
        
        if turn >= 4: 
            stage = "Mid"
            gov_chance = 0.70  # 中期機率：70%
            
        if turn >= 7: 
            stage = "Late"
            gov_chance = 0.90  # 後期機率：90%

        # 2. 一般新聞事件 (加入階段過濾)
        # 篩選出 phase_req 符合當前 stage，或者是 "All" (通用) 的事件
        valid_events = [e for e in config.EVENTS_DB if e.get("phase_req", "All") in [stage, "All"]]
        if valid_events:
            self.current_event = random.choice(valid_events)
        else:
            self.current_event = config.EVENTS_DB[0] # 防呆機制
        
        # 3. 政府收購案檢定
        self.active_gov_event = None # 預設清空
        
        # --- 特殊事件：第 16 回合強制觸發「全面戰爭總動員」 ---
        if turn == 16:
            target_event = next((e for e in config.GOV_ACQUISITIONS if e["id"] == "L-05"), None)
            if target_event:
                self.active_gov_event = target_event
                print(f"[事件] 第 {turn} 回合 - 🚨 強制觸發：{self.active_gov_event['title']}")
            return self.current_event

        # --- 一般政府收購案 (每兩回合檢定一次，即偶數回合) ---
        if turn % 2 == 0:
            if random.random() < gov_chance:
                # 篩選符合當前階段的收購案，並排除 L-05 (確保它只在第16回合出沒)
                candidates = [e for e in config.GOV_ACQUISITIONS if e["phase_req"] == stage and e["id"] != "L-05"]
                
                if candidates:
                    self.active_gov_event = random.choice(candidates)
                    print(f"[事件] 第 {turn} 回合 ({stage}) - 政府收購觸發：{self.active_gov_event['title']}")
            else:
                print(f"[事件] 第 {turn} 回合 ({stage}) - 檢定未通過，本回合無政府收購案")
        else:
            print(f"[事件] 第 {turn} 回合 - 休息回合 (每兩回合才進行政府收購檢定)")

        if self.current_event and self.current_event.get("type") == "PRICE_MOD":
                target = self.current_event["target"]
                mult = self.current_event["price_mult"]
                if target in self.market_prices:
                    self.market_prices[target] = int(self.market_prices[target] * mult)

        return self.current_event
    
# --- Phase 2: Production ---
    def process_production(self, player: PlayerState, factory_id: str, target_item: str, quantity: int) -> Tuple[bool, str]:
        # 1. 尋找對應的設施
        factory = next((f for f in player.factories if f.id == factory_id), None)
        if not factory: 
            return False, "找不到該設施"
            
        # 2. 檢查停擺狀態 
        if getattr(factory, "is_shutdown", False):
            return False, "該設施因天災停擺中，本回合無法運作！"
            
        event = getattr(self, "current_event", {}) or {}

        if "Miner" in factory.name:
            if getattr(factory, "has_produced", False):
                return False, "該採集器本回合已經開採過了！"

            if target_item not in config.ITEMS or config.ITEMS[target_item].get("tier") != 0:
                return False, "採集器只能開採 T0 原料"
            
            base_output = config.MINER_OUTPUTS.get(factory.tier, 3)
            qty_produced = base_output * quantity
        
            if event.get("special_effect") == "MINER_BOOST_1":
                qty_produced += (1 * quantity)
                
            player.inventory[target_item] += qty_produced
            factory.has_produced = True 
            return True, f"開採了 {qty_produced} 個 {config.ITEMS[target_item]['label']}"
            
        else:
            item_data = config.ITEMS.get(target_item)
            if not item_data or "recipe" not in item_data:
                return False, "無效的配方"
            
            if factory.tier < item_data["tier"]:
                return False, f"工廠等級不足 (需要 T{item_data['tier']})"
            
      
            for ing_id, req_qty in item_data["recipe"].items():
                if player.inventory.get(ing_id, 0) < req_qty * quantity:
                    return False, f"原料不足: 缺少 {config.ITEMS[ing_id]['label']} (需要 {req_qty * quantity} 個)"
        
            for ing_id, req_qty in item_data["recipe"].items():
                player.inventory[ing_id] -= req_qty * quantity
            
            qty_produced = quantity
     
            if factory.name == "Diamond Mine" and event.get("logic_key") == "DIAMOND_BOOST":
                qty_produced *= 2
                
            player.inventory[target_item] += qty_produced            
            return True, f"生產了 {qty_produced} 個 {item_data['label']}"
    
    def process_build_new(self, player: PlayerState, target_tier: int, materials: List[str]) -> Tuple[bool, str]:
        if len(player.factories) >= player.land_limit: return False, "土地不足。"

        if target_tier == 0:
            cost = 500
            if player.money < cost: return False, "現金不足 (需要 $500)。"
            player.money -= cost
            
            # 🌟 採集器：建好當下不可使用 (冷卻中)
            new_miner = Factory(id=str(uuid.uuid4())[:8], tier=0, name="Miner")
            new_miner.has_produced = True  
            player.factories.append(new_miner)
            
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
                
            # 🌟 一般加工廠：建好當下可立刻使用
            new_factory = Factory(id=str(uuid.uuid4())[:8], tier=1, name="Factory T1")
            new_factory.has_produced = False 
            player.factories.append(new_factory)
            
            return True, "成功建造 T1 加工廠。"
            
        return False, "未知的建造類型。"

    def process_build_special(self, player: PlayerState, b_type: str, materials: List[str]) -> Tuple[bool, str]:
        # 1. 土地空間檢查 (擴充土地除外)
        if b_type != "land" and len(player.factories) >= player.land_limit:
            return False, "土地空間不足，請先擴充土地！"

        mats = [m for m in materials if m] # 過濾空值
        
        # 2. 定義物品系別 (對應 T2 與 T3)
        ITEM_FAMILIES = {
            "silicon_t2": ["processor", "projector", "scanner"],
            "iron_t2": ["chassis", "drone", "thruster"],
            "energy_t2": ["reactor", "laser", "shield"],
            "silicon_t3": ["quantum", "upload"],
            "iron_t3": ["elevator", "terraform"],
            "energy_t3": ["warp_core", "star_conv"]
        }

        # 3. 處理「擴充土地」邏輯
        if b_type == "land":
            unique_mats = list(set(mats))
            if len(unique_mats) < 3: return False, "擴充土地需要「3 種不同」的 T3 物品，請在選單分別選擇！"
            
            t3_mats = [m for m in unique_mats[:3] if config.ITEMS.get(m, {}).get("tier") == 3]
            if len(t3_mats) < 3: return False, "選擇的材料必須都是 T3 等級！"
            
            for m in t3_mats:
                if player.inventory.get(m, 0) < 1: return False, f"缺乏 {config.ITEMS[m]['label']}"
                
            for m in t3_mats: player.inventory[m] -= 1
            player.land_limit += 1
            return True, "成功擴充 1 單位的土地！"

        # 4. 定義特殊建築需求
        reqs = {}
        name = ""
        tier = 3
        if b_type == "diamond": reqs = {"silicon_t2": 4, "iron_t2": 4}; name = "Diamond Mine"; tier = 2
        elif b_type == "prophet": reqs = {"silicon_t3": 3}; name = "Prophet"
        elif b_type == "defense": reqs = {"iron_t3": 1, "energy_t3": 2}; name = "Defense"
        elif b_type == "omni": reqs = {"energy_t3": 3}; name = "Omni Factory"
        elif b_type == "accelerator": reqs = {"iron_t3": 2, "energy_t3": 1}; name = "Accelerator"
        else: return False, "未知的建築類型"

        # 5. 驗證玩家提供的材料是否符合系別與數量
        matched_items = {}
        available_mats = list(mats) 
        
        for family, qty in reqs.items():
            # 尋找下拉選單中符合該系別的物品
            found_item = next((m for m in available_mats if m in ITEM_FAMILIES[family]), None)
            if not found_item:
                fam_name = family.replace("silicon", "矽晶").replace("iron", "鐵").replace("energy", "能源").upper()
                return False, f"付款材料缺少對應的【{fam_name}】物品！"
            
            if player.inventory.get(found_item, 0) < qty:
                return False, f"{config.ITEMS[found_item]['label']} 數量不足 (需 {qty} 個)！"
                
            matched_items[family] = found_item
            available_mats.remove(found_item) # 避免重複判定

        # 6. 扣除庫存並建立建築
        for family, qty in reqs.items():
            item = matched_items[family]
            player.inventory[item] -= qty
            
        # 🌟 特殊建築：建好當下可立刻啟動被動效果
        new_special = Factory(id=str(uuid.uuid4())[:8], tier=tier, name=name)
        new_special.has_produced = False 
        player.factories.append(new_special)
        
        name_zh = {"Diamond Mine": "鑽石場", "Prophet": "預言家", "Defense": "防災中心", "Omni Factory": "萬能工廠", "Accelerator": "加速器"}[name]
        return True, f"成功建造特殊建築：{name_zh}！"
    
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
    
        item_info = config.ITEMS.get(item_id)
        if not item_info or item_info["tier"] != 0:
            return False, "銀行只收購 T0 原料！"

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
    def execute_call_auction(self, players: Dict[str, PlayerState]) -> List[str]:
        print("\n=== 結算開始 ===")
        match_logs = []  # 🌟 新增：用來收集交易日誌的列表
        
        # 1. 優先處理政府收購 (Gov Execution)
        if self.active_gov_event and self.gov_orders:
            gov_logs = self._execute_gov_auction(players)
            match_logs.extend(gov_logs)
            
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
            
            item_name = config.ITEMS[item_id]['label']
            
            if volume > 0:
                self.market_prices[item_id] = clearing_price # Update market price
                match_logs.append(f"📈 市場撮合：【{item_name}】結算價 ${clearing_price}，共成交 {volume} 個！")
                
                # 🌟 修改：接收 _settle 回傳的詳細日誌並加入總列表
                detailed_logs = self._settle(players, bids, asks, clearing_price, volume, item_id)
                match_logs.extend(detailed_logs)
            else:
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
        
        return match_logs # 🌟 回傳收集到的日誌給 main.py

    def _execute_gov_auction(self, players) -> List[str]:
        print(f"--- 政府收購: {self.active_gov_event['title']} ---")
        event = self.active_gov_event
        gov_logs = [] # 🌟 收集政府收購的日誌
        
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
            item_name = config.ITEMS[item_id]['label']
            
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
                    
                    # 🌟 記錄政府得標日誌
                    gov_logs.append(f"🏛️ 政府得標：【{player.name}】成功向政府出售 {can_fill} 個 {item_name}，進帳 ${revenue}！")
                    
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
                    
        return gov_logs # 回傳給主函式

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

    def _settle(self, players, bids, asks, price, volume, item_id) -> List[str]:
        settle_logs = [] # 🌟 新增：收集這項物品的所有詳細撮合日誌
        item_name = config.ITEMS[item_id]['label'] # 取得物品名稱以便顯示

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
                
                # 🌟 新增：記錄玩家間的交易
                settle_logs.append(f"🤝 玩家交易：【{buyer.name}】向【{seller.name}】購買了 {trade_amt} 個 {item_name} (總價 ${actual_cost})")

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
                
        return settle_logs # 🌟 回傳詳細日誌
    
    def game_set(self, players: Dict[str, PlayerState]) -> List[Tuple[str, dict]]:
        print("\n=== 遊戲結束，開始最終計分 ===")
        
        # 定義設施價值查表
        facility_values = {
            "Miner": {0: 200, 1: 500, 2: 2000, 3: 5000},
            "Factory": {0: 0, 1: 500, 2: 8000, 3: 18000}
        }
        
        final_scores = {}
        
        for p_id, player in players.items():
            # 1. 計算庫存總價值 (所有物品數量 * 當前市價)
            inventory_value = 0
            for item_id, qty in player.inventory.items():
                if qty > 0:
                    market_price = self.market_prices.get(item_id, 0)
                    inventory_value += qty * market_price
                    
            # 2. 計算設施總價值
            facility_value = 0
            for factory in player.factories:
                # 判定是採集器還是工廠
                f_type = "Miner" if "Miner" in factory.name else "Factory"
                # 根據 tier 取出對應價值，若防呆防錯預設為 0
                facility_value += facility_values[f_type].get(factory.tier, 0)
                
            # 3. 總分計算 = 庫存價值 + 設施價值 + 現金
            total_score = inventory_value + facility_value + player.money
            
            final_scores[player.name] = {
                "inventory_value": inventory_value,
                "facility_value": facility_value,
                "cash": player.money,
                "total_score": total_score
            }
            
        # 依照總分進行降冪排序
        ranked_players = sorted(final_scores.items(), key=lambda x: x[1]["total_score"], reverse=True)
        
        # 印出結算結果清單
        for rank, (name, data) in enumerate(ranked_players, 1):
            print(f"第 {rank} 名: {name} | 總分: {data['total_score']} "
                  f"(現金: {data['cash']}, 庫存價值: {data['inventory_value']}, 設施價值: {data['facility_value']})")
            
        return ranked_players
    
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
            
            # --- A. 倉儲稅機制 ---
            # 免稅額 = 基礎(5) + sum(工廠點數)
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
                player_logs.append(f"📦 倉儲超載稅：扣除 ${tax_total}")

            # --- B. 事件檢定與懲罰 ---
            has_defense = any(f.name == "Defense" for f in p.factories) # 檢查是否有防災中心
            
            if event.get("type") == "DEFENSE_CHECK":
                req_item = event["req_item"]
                req_qty = event["req_qty"]
                
                if p.inventory.get(req_item, 0) >= req_qty:
                    p.inventory[req_item] -= req_qty
                    player_logs.append(f"🛡️ 成功上繳 {req_qty} 個 {config.ITEMS[req_item]['label']} 抵禦災害！")
                elif has_defense:
                    player_logs.append(f"🛡️ 防災中心啟動！完美抵禦了災害！")
                else:
                    penalty = event["penalty"]
                    if penalty == "SHUTDOWN_FACILITIES":
                        for f in p.factories: setattr(f, "is_shutdown", True) # 標記停擺
                        player_logs.append("💥 災害命中：所有設施下回合停擺！")
                    elif penalty == "HALVE_CASH":
                        lost = p.money - int(p.money * 0.5)
                        p.money = int(p.money * 0.5)
                        player_logs.append(f"💥 災害命中：現金減半 (損失 ${lost})！")
                    elif penalty == "DESTROY_FACTORY":
                        if p.factories:
                            import random
                            f_to_destroy = random.choice(p.factories)
                            p.factories.remove(f_to_destroy)
                            player_logs.append(f"💥 災害命中：{f_to_destroy.name} 被摧毀了！")

            elif event.get("type") == "SPECIAL" and event.get("logic_key") == "LAND_TAX_BEAM":
                if p.land_limit > 5:
                    if p.inventory.get("beam", 0) >= 7:
                        p.inventory["beam"] -= 7
                        player_logs.append("🏗️ 扣除 7 個工業鋼樑維護擴充的土地。")
                    else:
                        if p.factories:
                            import random
                            f_to_destroy = random.choice(p.factories)
                            p.factories.remove(f_to_destroy)
                            player_logs.append(f"⚠️ 鋼樑不足！擴充土地上的 {f_to_destroy.name} 崩塌了！")
                            
            if player_logs:
                logs.append(f"【{p.name}】 " + " | ".join(player_logs))
                
        return logs