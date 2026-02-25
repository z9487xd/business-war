from typing import Dict, List, Optional
from pydantic import BaseModel

class Order(BaseModel):
    player_id: str
    type: str  
    item_id: str
    price: int
    quantity: int
    timestamp: float = 0.0

class Factory(BaseModel):
    id: str
    tier: int
    name: str
    has_produced: bool = False
    is_shutdown: bool = False
    current_product: Optional[str] = None  

class PlayerState(BaseModel):
    id: str
    name: str
    money: int
    inventory: Dict[str, int]
    locked_inventory: Dict[str, int] = {}
    locked_money: int = 0
    factories: List[Factory]
    land_limit: int = 5