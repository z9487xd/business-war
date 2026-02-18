from typing import Dict, List, Optional
from pydantic import BaseModel
import time

class Factory(BaseModel):
    id: str
    tier: int           # 0=Miner, 1=Factory T1, etc.
    name: str           # e.g., "T0 Miner", "T1 Factory"
    has_produced: bool = False # Reset this every round

class PlayerState(BaseModel):
    id: str
    name: str
    money: int
    inventory: Dict[str, int] = {}
    
    # Building System
    land_limit: int = 5
    factories: List[Factory] = []
    
    # Locked assets during trading phase
    locked_money: int = 0
    locked_inventory: Dict[str, int] = {}

class Order(BaseModel):
    player_id: str
    type: str           # "BID", "ASK", "GOV_ASK"
    item_id: str
    price: int
    quantity: int
    timestamp: float = 0.0