import json
import random
import os

# 取得目前檔案所在的目錄位置，確保能正確讀取 json
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
JSON_PATH = os.path.join(BASE_DIR, "data.json")

with open(JSON_PATH, "r", encoding="utf-8") as f:
    data = json.load(f)

# --- 讀取基礎設定 ---
settings = data["game_settings"]
INITIAL_MONEY = settings["initial_money"]
INITIAL_LAND = settings["initial_land"]
PRICE_FLUCTUATION_LIMIT = settings["price_fluctuation_limit"]
BANK_BUY_RATIO = settings["bank_buy_ratio"]
GOV_BUY_RATIO = settings["gov_buy_ratio"]

# --- 讀取倉儲規則 ---
storage = data["storage_rules"]
BASE_STORAGE_LIMIT = storage["base_storage_limit"]
PENALTY_LOW = storage["penalty_low"]
PENALTY_MID = storage["penalty_mid"]
PENALTY_HIGH = storage["penalty_high"]

# JSON 的鍵必定為字串，需在此轉為整數供遊戲邏輯使用
CP_VALUES = {int(k): v for k, v in storage["cp_values"].items()}

# --- 讀取工廠與採集器設定 ---
costs = data["factory_costs"]
BUILD_T1_COST = costs["build_t1"]
UPGRADE_TO_T2 = costs["upgrade_to_t2"]
UPGRADE_TO_T3_MONEY = costs["upgrade_to_t3_money"]

miners = data["miner_rules"]
MINER_UPGRADE_RULES = {int(k): v for k, v in miners["upgrade_rules"].items()}
MINER_OUTPUTS = {int(k): v for k, v in miners["outputs"].items()}

# --- 讀取物品與事件 ---
ITEMS = data["items"]
EVENTS_DB = data["events"]
GOV_ACQUISITIONS = data["gov_acquisitions"]

# --- 輔助函式 ---
def get_random_event():
    return random.choice(EVENTS_DB)