from typing import List, Dict
from core.models import Order
import config

# Correct the path to include 'Phases' subfolder
from core.Phases.phase1 import Phase1News
from core.Phases.phase2 import Phase2Action
from core.Phases.phase3 import Phase3Trading
from core.Phases.phase4 import Phase4Settlement
# from core.Phases.phase5 import Phase5Result 

class GameEngine(Phase1News, Phase2Action, Phase3Trading, Phase4Settlement):
    """
    Game Engine combining all phases via Multiple Inheritance.
    """
    def __init__(self):    
        self.orders: List[Order] = []
        self.market_prices: Dict[str, int] = {
            k: v["base_price"] for k, v in config.ITEMS.items()
        }
        self.current_event = config.EVENTS_DB[0] 
        self.active_gov_event = None 
        self.gov_orders: List[Order] = []