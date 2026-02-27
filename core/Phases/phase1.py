import random
import config
from typing import Tuple, List, Dict, Any

class Phase1News:
    def generate_daily_event(self, turn: int) -> Tuple[Dict[str, Any], List[str]]:
        # 0. 必須保留：清空上一回合的歷史訂單
        self.orders.clear()
        self.gov_orders.clear()
        
        event_logs = [] # 新增：用來收集這回合系統判定的日誌

        # 1. 統一判斷當前階段與政府收購機率
        stage = "Early"
        gov_chance = 0.50  
        
        if turn >= 4: 
            stage = "Mid"
            gov_chance = 0.70  
            
        if turn >= 7: 
            stage = "Late"
            gov_chance = 0.90  

        # 2. 一般新聞事件
        valid_events = [e for e in config.EVENTS_DB if e.get("phase_req", "All") in [stage, "All"]]
        if valid_events:
            self.current_event = random.choice(valid_events)
        else:
            self.current_event = config.EVENTS_DB[0] 
        
        # 3. 政府收購案檢定
        self.active_gov_event = None 
        
        # --- 特殊事件：第 16 回合強制觸發「全面戰爭總動員」 ---
        if turn == 16:
            target_event = next((e for e in config.GOV_ACQUISITIONS if e.get("id") == "L-05"), None)
            if target_event:
                self.active_gov_event = target_event
                event_logs.append(f"[事件] 第 {turn} 回合 - 強制觸發政府收購：{self.active_gov_event['title']}")
        else:
            # --- 一般政府收購案 ---
            if turn % 2 == 0:
                if random.random() < gov_chance:
                    candidates = [e for e in config.GOV_ACQUISITIONS if e.get("phase_req") == stage and e.get("id") != "L-05"]
                    
                    if candidates:
                        self.active_gov_event = random.choice(candidates)
                        event_logs.append(f"[事件] 第 {turn} 回合 ({stage}) - 政府收購觸發：{self.active_gov_event['title']}")
                else:
                    event_logs.append(f"[事件] 第 {turn} 回合 ({stage}) - 檢定未通過，本回合無政府收購案。")
            else:
                event_logs.append(f"[事件] 第 {turn} 回合 - 休息回合 (每兩回合進行一次政府收購檢定)。")

        # 4. 價格崩跌事件立即生效
        if self.current_event and self.current_event.get("type") == "PRICE_MOD":
            target = self.current_event["target"]
            mult = self.current_event["price_mult"]
            if target in self.market_prices:
                self.market_prices[target] = int(self.market_prices[target] * mult)

        # 修改回傳值，將事件與日誌一起拋出
        return self.current_event, event_logs