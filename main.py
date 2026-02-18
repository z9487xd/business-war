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
game_logs: List[str] = []  # 新增：儲存遊戲日誌

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

@app.get("/")
async def get_player_ui(request: Request):
    return templates.TemplateResponse("player_ui.html", {"request": request})

@app.get("/admin")
async def get_admin_dashboard(request: Request):
    return templates.TemplateResponse("admin_dashboard.html", {"request": request})

# --- 新增：Admin 專用資料接口 ---
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
        "logs": game_logs
    }

@app.post("/api/register")
async def register_player(data: RegisterModel):
    new_id = str(uuid.uuid4())
    init_factory = Factory(id=str(uuid.uuid4())[:8], tier=0, name="Miner")
    
    new_player = PlayerState(
        id=new_id,
        name=data.name,
        money=config.INITIAL_MONEY,
        inventory={k: 0 for k in config.ITEMS.keys()},
        factories=[init_factory],
        land_limit=config.INITIAL_LAND
    )
    
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
        engine.execute_call_auction(players)
        current_phase = 4
        log_event("市場撮合與結算完成")
        
    elif current_phase == 4:
        for p in players.values():
            for f in p.factories: f.has_produced = False
        
        current_turn += 1
        engine.generate_daily_event(current_turn)
        current_phase = 1
        log_event(f"=== 第 {current_turn} 回合 開始 ===")
        
    else:
        current_phase += 1

    return {"status": "success", "new_phase": current_phase, "turn": current_turn}

@app.post("/admin/reset")
async def reset_game():
    global players, current_phase, engine, current_turn, game_logs
    players = {}
    current_phase = 1
    current_turn = 1
    game_logs = [] # 清空日誌
    engine = GameEngine()
    engine.generate_daily_event(current_turn)
    log_event("=== 遊戲已重置 ===")
    return {"status": "reset complete"}