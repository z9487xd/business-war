import uuid
from typing import List, Tuple
from core.models import PlayerState, Factory
import config

class Phase2Action:
    def process_production(self, player: PlayerState, factory_id: str, target_item: str, quantity: int) -> Tuple[bool, str]:
        factory = next((f for f in player.factories if f.id == factory_id), None)
        if not factory: return False, "找不到該設施"
            
        if getattr(factory, "is_shutdown", False):
            return False, "該設施因天災停擺中，本回合無法運作！"
            
        event = getattr(self, "current_event", {}) or {}
        item_data = config.ITEMS.get(target_item)

        if "Miner" in factory.name:
            if getattr(factory, "has_produced", False):
                return False, "該採集器本回合已經開採過了！"
            if not item_data or item_data.get("tier") != 0:
                return False, "採集器只能開採 T0 原料"
            
            base_output = config.MINER_OUTPUTS.get(factory.tier, 3)
            qty_produced = base_output * quantity
            if event.get("special_effect") == "MINER_BOOST_1":
                qty_produced += (1 * quantity)
                
            player.inventory[target_item] = player.inventory.get(target_item, 0) + qty_produced
            factory.has_produced = True 
            return True, f"開採了 {qty_produced} 個 {item_data['label']}"
            
        else:
            if not item_data or "recipe" not in item_data: return False, "無效的配方"

            # 針對鑽石場的特殊防呆
            if target_item == "diamond":
                if factory.name != "Diamond Mine":
                    return False, "只有鑽石場可以生產鑽石！"
            else:
                if factory.tier < item_data["tier"]:
                    return False, f"工廠等級不足 (需要 T{item_data['tier']})"
                
            if getattr(factory, "has_produced", False):
                locked_item = getattr(factory, "current_product", None)
                if locked_item and locked_item != target_item:
                    locked_name = config.ITEMS.get(locked_item, {}).get("label", locked_item)
                    return False, f"產線已鎖定！此工廠本回合只能生產【{locked_name}】。"
            is_omni = (factory.name == "Omni Factory")
            is_accelerator = (factory.name == "Accelerator")

            # 1. 檢查原料是否充足 (萬能工廠可支援同階級替代)
            for ing_id, req_qty in item_data["recipe"].items():
                total_needed = req_qty * quantity
                if player.inventory.get(ing_id, 0) >= total_needed:
                    continue
                
                if is_omni:
                    req_tier = config.ITEMS[ing_id]["tier"]
                    shortage = total_needed - player.inventory.get(ing_id, 0)
                    # 尋找所有同階級的替代品數量
                    subs_found = sum(qty for sub_id, qty in player.inventory.items() 
                                     if sub_id != ing_id and config.ITEMS.get(sub_id, {}).get("tier") == req_tier)
                    if subs_found < shortage:
                        return False, f"原料或同等級替代品不足: 缺少 {config.ITEMS[ing_id]['label']} (需 {total_needed} 個)"
                else:
                    return False, f"原料不足: 缺少 {config.ITEMS[ing_id]['label']} (需 {total_needed} 個)"
        
            # 2. 扣除原料 (含萬能工廠的代扣邏輯)
            for ing_id, req_qty in item_data["recipe"].items():
                total_needed = req_qty * quantity
                exact_have = player.inventory.get(ing_id, 0)
                
                if exact_have >= total_needed:
                    player.inventory[ing_id] -= total_needed
                elif is_omni:
                    player.inventory[ing_id] = 0
                    shortage = total_needed - exact_have
                    req_tier = config.ITEMS[ing_id]["tier"]
                    # 依序扣除其他同階級物品直到補足 shortage
                    for sub_id in list(player.inventory.keys()):
                        if shortage <= 0: break
                        if sub_id != ing_id and config.ITEMS.get(sub_id, {}).get("tier") == req_tier:
                            take = min(player.inventory[sub_id], shortage)
                            player.inventory[sub_id] -= take
                            shortage -= take

            # 3. 計算產量與增益
            qty_produced = quantity
            if is_accelerator:
                qty_produced *= 2 # 加速器產量翻倍
                
            if factory.name == "Diamond Mine" and event.get("logic_key") == "DIAMOND_BOOST":
                qty_produced *= 2 # 疊加鑽石爆發事件
                
            player.inventory[target_item] = player.inventory.get(target_item, 0) + qty_produced 
            factory.has_produced = True           
            factory.current_product = target_item     
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
        # 1. 取得設定檔中的規則
        fac_config = config.SPECIAL_FACILITIES.get(b_type)
        if not fac_config:
            return False, "未知的特殊建築類型"

        # 2. 土地空間檢查 (擴充土地除外)
        if b_type != "special_land" and len(player.factories) >= player.land_limit:
            return False, "土地空間不足，請先擴充土地！"

        mats = [m for m in materials if m] # 過濾空值
        
        # 3. 處理「UNIQUE_TIER」邏輯 (例如：擴充土地)
        if fac_config["cost_rule"] == "UNIQUE_TIER":
            req_tier = fac_config["costs"]["tier"]
            req_unique = fac_config["costs"]["unique_qty"]
            req_qty = fac_config["costs"]["qty_per_item"]
            
            unique_mats = list(set(mats))
            # 先過濾出符合等級的材料
            valid_tier_mats = [m for m in unique_mats if config.ITEMS.get(m, {}).get("tier") == req_tier]
            
            if len(valid_tier_mats) < req_unique: 
                return False, f"選擇的材料必須包含 {req_unique} 種不同的 T{req_tier} 物品！"
            
            valid_mats = valid_tier_mats[:req_unique]
            for m in valid_mats:
                if player.inventory.get(m, 0) < req_qty: 
                    return False, f"缺乏 {config.ITEMS[m]['label']} (需要 {req_qty} 個)"
            
            # 扣除庫存並生效
            for m in valid_mats: 
                player.inventory[m] -= req_qty
            player.land_limit += 1
            return True, "成功擴充 1 單位的土地！"

        # 4. 處理「SERIES_AND_TIER」邏輯 (其他實體設施)
        elif fac_config["cost_rule"] == "SERIES_AND_TIER":
            reqs = fac_config["costs"] # e.g. {"silicon_2": 4, "iron_2": 4}
            matched_items = {}
            available_mats = list(mats) 
            
            for req_key, req_qty in reqs.items():
                req_series, req_tier_str = req_key.split("_")
                req_tier = int(req_tier_str)
                
                # 尋找玩家選擇中，符合該系別與等級的物品
                found_item = None
                for m in available_mats:
                    item_data = config.ITEMS.get(m)
                    if item_data and item_data.get("series") == req_series and item_data.get("tier") == req_tier:
                        found_item = m
                        break
                        
                if not found_item:
                    fam_name = {"silicon": "矽晶", "iron": "鐵", "energy": "能源"}.get(req_series, req_series)
                    return False, f"付款材料缺少對應的【{fam_name}系 T{req_tier}】物品！"
                
                if player.inventory.get(found_item, 0) < req_qty:
                    return False, f"{config.ITEMS[found_item]['label']} 數量不足 (需 {req_qty} 個)！"
                    
                matched_items[req_key] = {"item": found_item, "qty": req_qty}
                available_mats.remove(found_item) # 避免重複判定

            # 扣除庫存
            for req_key, match in matched_items.items():
                player.inventory[match["item"]] -= match["qty"]
                
            # 決定設施內部的識別名稱與階級
            name_mapping = {
                "special_diamond": ("Diamond Mine", 4), # 設為 T4 讓它可以讀到鑽石配方
                "special_defense": ("Defense", 3),
                "special_omni": ("Omni Factory", 3),
                "special_accelerator": ("Accelerator", 3)
            }
            name, tier = name_mapping.get(b_type, (fac_config["label"], 3))
            
            # 建立特殊設施
            new_special = Factory(id=str(uuid.uuid4())[:8], tier=tier, name=name)
            new_special.has_produced = False 
            player.factories.append(new_special)
            
            return True, f"成功建造特殊建築：{fac_config['label']}！"
            
        return False, "設定檔規則解析錯誤"
    
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