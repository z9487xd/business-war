import random
import config

class Phase1News:
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