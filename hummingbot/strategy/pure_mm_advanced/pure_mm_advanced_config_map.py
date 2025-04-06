from hummingbot.client.config.config_data_types import (
    ConfigVar,
    Dec,
)
from hummingbot.client.settings import required_exchanges

def pure_mm_advanced_config_map():
    return {
        "strategy": ConfigVar(
            key="strategy",
            prompt="",
            default="pure_mm_advanced",
        ),
        "exchange": ConfigVar(
            key="exchange",
            prompt="Enter the name of the exchange (e.g. binance_paper_trade)",
            validator=lambda v: v in required_exchanges,
        ),
        "trading_pair": ConfigVar(
            key="trading_pair",
            prompt="Enter the trading pair you would like to trade (e.g. ETH-USDT)",
        ),
        "order_amount": ConfigVar(
            key="order_amount",
            prompt="What is the order amount?",
            type_str="decimal",
            validator=lambda v: v > 0,
        ),
        "spread": ConfigVar(
            key="spread",
            prompt="What is the spread?",
            default=0.002,
            type_str="decimal",
        ),
    }
