# start.py
from typing import Optional

from hummingbot.strategy.strategy_base import StrategyBase
from hummingbot.client.config.config_helpers import parse_cvar_value
from hummingbot.strategy.combined_pmm import combined_pmm_config_map as c_map
from hummingbot.strategy.combined_pmm.combined_pmm_strategy import CombinedPMMStrategy

def start(self) -> Optional[StrategyBase]:
    # Retrieve all required config variables
    exchange = c_map["exchange"].value.lower()
    trading_pair = c_map["trading_pair"].value
    order_amount = parse_cvar_value(c_map["order_amount"])
    order_refresh_time = float(c_map["order_refresh_time"].value)
    target_base_pct = Decimal(str(c_map["target_base_pct"].value)) / Decimal("100")  # convert % to fraction
    candles_interval = c_map["candles_interval"].value
    candles_length = int(c_map["candles_length"].value)
    
    # Set up market connector
    connector = self.connectors[exchange]  
    market_names = [(exchange, trading_pair)]
    
    # Initialize the strategy class with connectors (markets)
    strategy = CombinedPMMStrategy(connectors={exchange: connector})
    # Override strategy parameters with user config values
    strategy.exchange = exchange
    strategy.trading_pair = trading_pair
    strategy.order_amount = order_amount
    strategy.order_refresh_time = order_refresh_time
    strategy.target_base_pct = target_base_pct
    strategy.candles_interval = candles_interval
    strategy.candles_length = candles_length
    
    return strategy
