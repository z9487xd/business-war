import uuid
from datetime import datetime
from typing import Dict, List, Optional
from fastapi import FastAPI, Request, HTTPException, Body
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import JSONResponse
from pydantic import BaseModel

import config
from core.models import PlayerState, Order, Factory
from core.engine import GameEngine

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# --- 全域變數 ---
engine = GameEngine()
engine.generate_daily_event(1)
players: Dict[str, PlayerState] = {}
current_phase = 1
current_turn = 1
game_logs: List[str] = []  # 儲存遊戲日誌
final_ranking_data: List[dict] = []  # 新增：儲存最終結算成績

# --- 日誌輔助函式 ---
def log_event(message: str):
    time_str = datetime.now().strftime("%H:%M:%S")
    log_entry = f"[{time_str}] {message}"
    game_logs.insert(0, log_entry) # 最新訊息插在最前面
    if len(game_logs) > 100: # 只保留最近 100 筆
        game_logs.pop()

# --- API Models ---
class RegisterModel(BaseModel): name: str
class TradeModel(BaseModel): player_id: str; type: str; item_id: str; price: int; quantity: int
class ProduceModel(BaseModel): player_id: str; factory_id: str; target_item: str; quantity: int = 1
class BuildModel(BaseModel): player_id: str; target_tier: int = 1; payment_materials: List[str] = [] 
class UpgradeModel(BaseModel): player_id: str; factory_id: str; payment_materials: List[str] = []
class BankSellModel(BaseModel): player_id: str; item_id: str; quantity: int
class DemolishModel(BaseModel): player_id: str; factory_id: str
class BuildSpecialModel(BaseModel): player_id: str; building_type: str; payment_materials: List[str] = []

@app.get("/")
async def get_player_ui(request: Request):
    return templates.TemplateResponse("player_ui.html", {"request": request})

@app.get("/admin")
async def get_admin_dashboard(request: Request):
    return templates.TemplateResponse("admin_dashboard.html", {"request": request})

# --- Admin 專用資料接口 ---
@app.get("/admin/data")
async def get_admin_data():
    player_list = []
    for p in players.values():
        player_list.append({
            "name": p.name,
            "money": p.money,
            "land": f"{len(p.factories)}/{p.land_limit}",
            "inventory_count": sum(p.inventory.values())
        })
    # 根據金額排序 (有錢人排前面)
    player_list.sort(key=lambda x: x["money"], reverse=True)
    
    return {
        "phase": current_phase,
        "turn": current_turn,
        "players": player_list,
        "logs": game_logs,
        "items_meta": config.ITEMS,
        "market_prices": engine.market_prices
    }

@app.post("/api/register")
async def register_player(data: RegisterModel):
    # 🌟 攔截幽靈玩家：如果名字已經存在，直接讓他「登入」原帳號
    for pid, p in players.items():
        if p.name == data.name:
            log_event(f"玩家重連: {data.name} 回到了遊戲")
            return {"status": "success", "player_id": pid, "name": data.name}

    # 如果是全新的名字，才創建新帳號
    new_id = str(uuid.uuid4())
    init_factory = Factory(id=str(uuid.uuid4())[:8], tier=0, name="Miner")

    #測試用
    test_t2_factory = Factory(id=str(uuid.uuid4())[:8], tier=2, name="Factory")
    cheat_inventory = {k: 50 for k in config.ITEMS.keys()}
    new_player = PlayerState(
        id=new_id,
        name=data.name,
        money=1000000, # 🌟 測試用：直接給一百萬初始資金 (原本是 config.INITIAL_MONEY)
        inventory=cheat_inventory, # 🌟 測試用：載入作弊庫存
        factories=[init_factory, test_t2_factory], # 🌟 把 T2 工廠加進初始設施列表裡
        land_limit=config.INITIAL_LAND
    )

    # new_player = PlayerState(
    #     id=new_id,
    #     name=data.name,
    #     money=config.INITIAL_MONEY,
    #     inventory={k: 0 for k in config.ITEMS.keys()},
    #     factories=[init_factory],
    #     land_limit=config.INITIAL_LAND
    # )
    
    players[new_id] = new_player
    log_event(f"玩家註冊: {data.name} 加入了遊戲")
    return {"status": "success", "player_id": new_id, "name": data.name}

@app.get("/api/state")
async def get_state(player_id: Optional[str] = None):
    response = {
        "turn": current_turn,
        "phase": current_phase,
        "event": engine.current_event,
        "gov_event": engine.active_gov_event,
        "market_prices": engine.market_prices,
        "items_meta": config.ITEMS,
        "all_players": [
            {
                "name": p.name, 
                "money": p.money, 
                "factories": [f.dict() for f in p.factories],
                "land": f"{len(p.factories)}/{p.land_limit}"
            } for p in players.values()
        ]
    }
    if player_id and player_id in players:
        p = players[player_id]
        response["player"] = p.dict()
        
    # 新增：如果遊戲結束(Phase 5)，把最終排名傳給前端
    if current_phase == 5:
        response["final_ranking"] = final_ranking_data

    return response

@app.post("/api/produce")
async def produce_item(data: ProduceModel):
    if current_phase != 2: raise HTTPException(400, "非行動階段")
    if data.player_id not in players: raise HTTPException(404, "Player not found")
    
    p = players[data.player_id]
    success, msg = engine.process_production(p, data.factory_id, data.target_item, data.quantity)
    
    if not success: raise HTTPException(400, msg)
    log_event(f"{p.name} 生產: {msg}")
    return {"status": "success", "message": msg}

@app.post("/api/build")
async def build_factory(data: BuildModel):
    if current_phase != 2: raise HTTPException(400, "非行動階段")
    if data.player_id not in players: raise HTTPException(404, "Player not found")

    p = players[data.player_id]
    success, msg = engine.process_build_new(p, data.target_tier, data.payment_materials)
    
    if not success: raise HTTPException(400, msg)
    log_event(f"{p.name} 建造: {msg}")
    return {"status": "success", "message": msg}

@app.post("/api/build_special")
async def build_special(data: BuildSpecialModel):
    if current_phase != 2: raise HTTPException(400, "非行動階段")
    if data.player_id not in players: raise HTTPException(404, "Player not found")

    p = players[data.player_id]
    success, msg = engine.process_build_special(p, data.building_type, data.payment_materials)
    
    if not success: raise HTTPException(400, msg)
    log_event(f"{p.name} 執行特殊建設: {msg}")
    return {"status": "success", "message": msg}

@app.post("/api/upgrade")
async def upgrade_factory(data: UpgradeModel):
    if current_phase != 2: raise HTTPException(400, "非行動階段")
    if data.player_id not in players: raise HTTPException(404, "Player not found")

    p = players[data.player_id]
    success, msg = engine.process_upgrade(p, data.factory_id, data.payment_materials)
    
    if not success: raise HTTPException(400, msg)
    log_event(f"{p.name} 升級: {msg}")
    return {"status": "success", "message": msg}

@app.post("/api/demolish")
async def demolish_factory(data: DemolishModel):
    if current_phase != 2: raise HTTPException(400, "只有在行動階段才能拆除")
    if data.player_id not in players: raise HTTPException(404, "Player not found")
    
    p = players[data.player_id]
    success, msg = engine.process_demolish(p, data.factory_id)
    
    if not success: raise HTTPException(400, msg)
    log_event(f"{p.name} 拆除: {msg}")
    return {"status": "success", "message": msg}

@app.post("/api/bank_sell")
async def sell_to_bank(data: BankSellModel):
    if current_phase != 2: raise HTTPException(400, "非行動階段")
    if data.player_id not in players: raise HTTPException(404, "Player not found")
    
    p = players[data.player_id]
    success, msg = engine.process_bank_sell(p, data.item_id, data.quantity)
    
    if not success: raise HTTPException(400, msg)
    log_event(f"{p.name} 銀行交易: {msg}")
    return {"status": "success", "message": msg}

@app.post("/api/trade")
async def place_order(data: TradeModel):
    if current_phase != 3: raise HTTPException(400, "非交易階段")
    if data.player_id not in players: raise HTTPException(404, "Player not found")

    if engine.current_event and engine.current_event.get("type") == "TRADE_BAN":
        if data.item_id == engine.current_event["target"]:
            raise HTTPException(400, f" 核災恐慌：本回合禁止交易 {config.ITEMS[data.item_id]['label']}！")
    
    p = players[data.player_id]
    order_type = data.type
    
    if order_type == "GOV_ASK":
        if not engine.active_gov_event: raise HTTPException(400, "無政府收購")
        if data.item_id not in engine.active_gov_event["targets"]: raise HTTPException(400, "非收購目標")
        
        market_p = engine.market_prices.get(data.item_id, config.ITEMS[data.item_id]["base_price"])
        max_price = int(market_p * config.GOV_BUY_RATIO)
        if data.price > max_price: raise HTTPException(400, "出價過高")
            
    order = Order(
        player_id=data.player_id, 
        type=order_type, 
        item_id=data.item_id, 
        price=data.price, 
        quantity=data.quantity
    )
    
    success, msg = engine.validate_and_lock_assets(p, order)
    if not success: raise HTTPException(400, msg)
    
    if order_type == "GOV_ASK":
        engine.gov_orders.append(order)
        log_event(f"{p.name} 投標政府合約: {data.quantity}個 {data.item_id} @ ${data.price}")
    else:
        engine.orders.append(order)
        type_str = "買入" if data.type == "BID" else "賣出"
        log_event(f"{p.name} 掛單{type_str}: {data.quantity}個 {data.item_id} @ ${data.price}")
        
    return {"status": "accepted", "message": msg}

@app.post("/admin/next_phase")
async def next_phase():
    global current_phase, current_turn
    
    log_event(f"--- 管理員切換階段: 從 {current_phase} 結束 ---")

    if current_phase == 3:
        # 🌟 核心修改：接收撮合引擎回傳的交易日誌 (List[str])
        auction_logs = engine.match_market_orders(players)
        
        # 如果有日誌，就把每一筆交易結果與失敗原因印到 Admin 廣播日誌上
        if auction_logs:
            for alog in auction_logs:
                log_event(alog)
                
        current_phase = 4
        log_event("=== 市場撮合完成，進入第 4 階段：結算階段 ===")
        
        # 呼叫結算機制 (扣稅、事件懲罰、複利)
        end_turn_logs = engine.process_end_of_turn(players)
        if end_turn_logs:
            for l in end_turn_logs:
                log_event(l)
            
    elif current_phase == 4:
        for p in players.values():
            for f in p.factories: 
                # 🌟 新增：如果中了停擺懲罰，這回合就不能生產
                if getattr(f, "is_shutdown", False):
                    f.has_produced = True  # 設為 True 代表本回合已耗盡
                    f.is_shutdown = False  # 解除標記
                else:
                    f.has_produced = False
                f.current_product = None
        current_turn += 1
        engine.generate_daily_event(current_turn)
        current_phase = 1
        log_event(f"=== 第 {current_turn} 回合 開始 ===")

        new_event, phase1_logs = engine.generate_daily_event(current_turn)
        for log_msg in phase1_logs:
            log_event(log_msg)
        
    else:
        current_phase += 1

    return {"status": "success", "new_phase": current_phase, "turn": current_turn}

@app.post("/admin/reset")
async def reset_game():
    # 新增 final_ranking_data，確保重置時清空成績
    global players, current_phase, engine, current_turn, game_logs, final_ranking_data
    players = {}
    current_phase = 1
    current_turn = 1
    game_logs = [] 
    final_ranking_data = [] # 清空成績
    engine = GameEngine()
    engine.generate_daily_event(current_turn)
    log_event("=== 遊戲已重置 ===")
    return {"status": "reset complete"}

@app.post("/admin/end_game")
async def end_game():
    global current_phase, final_ranking_data # 加入 global 變數
    
    if not players:
        return {"status": "error", "message": "目前沒有玩家，無法結算。"}

    # 呼叫 GameEngine 的結算函式
    ranked_players = engine.game_set(players)
    
    # 將遊戲階段設為 5，代表「遊戲結束」
    current_phase = 5
    
    # 把格式整理好，存到全域變數裡讓玩家的 API 可以讀取
    final_ranking_data = [
        {"name": name, "scores": data} for name, data in ranked_players
    ]
    
    # 把結算結果寫入遊戲日誌，讓大家都能看到
    log_event("=== 🛑 遊戲已由管理員強制結束，進行最終結算 ===")
    for rank, p_data in enumerate(final_ranking_data, 1):
        log_event(f"🏆 第 {rank} 名: {p_data['name']} | 總資產: ${p_data['scores']['total_score']}")
        
    return {
        "status": "success", 
        "message": "遊戲已結算", 
        "ranking": final_ranking_data
    }