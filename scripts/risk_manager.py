from decimal import Decimal

class InventoryManager:
    def __init__(self, max_inventory: Decimal, trading_pair: str):
        self.max_inventory = max_inventory
        self.base, self.quote = trading_pair.split('-')
        self.current_position = Decimal('0')
        
    def update_position(self, fill_event):
        if fill_event.trade_type == "BUY":
            self.current_position += Decimal(str(fill_event.amount))
        else:
            self.current_position -= Decimal(str(fill_event.amount))
            
    def get_skew_factor(self) -> float:
        """Returns -1 (max sell bias) to 1 (max buy bias)"""
        return float((self.max_inventory - self.current_position) / self.max_inventory)
        
    def check_limits(self, proposed_amount: Decimal) -> bool:
        return abs(self.current_position + proposed_amount) <= self.max_inventory