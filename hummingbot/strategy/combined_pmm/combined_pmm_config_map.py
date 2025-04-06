
from hummingbot.client.config.config_var import ConfigVar
from hummingbot.client.config.config_validators import validate_decimal

combined_pmm_config_map = {
    "strategy": ConfigVar(
        key="strategy",
        prompt="",
        default="combined_pmm_strategy",  
        prompt_on_new=False
    ),
    "exchange": ConfigVar(
        key="exchange",
        prompt="Enter the name of the exchange >>> ",
        prompt_on_new=True,
        default=None,
     
    ),
    "trading_pair": ConfigVar(
        key="trading_pair",
        prompt="Enter the trading pair (e.g. ETH-USDT) >>> ",
        prompt_on_new=True,
        default=None,
    ),
    "order_amount": ConfigVar(
        key="order_amount",
        prompt="Enter order amount (in base asset) >>> ",
        prompt_on_new=True,
        default=0.0,
        type_str="decimal",
        validator=validate_decimal
    ),
    "order_refresh_time": ConfigVar(
        key="order_refresh_time",
        prompt="Enter order refresh time in seconds >>> ",
        prompt_on_new=True,
        default=15.0,
        type_str="float",
    ),
    "target_base_pct": ConfigVar(
        key="target_base_pct",
        prompt="Enter target base asset inventory percentage (0-100) >>> ",
        prompt_on_new=True,
        default=50.0,
        type_str="decimal",
        validator=validate_decimal
    ),
    "candles_interval": ConfigVar(
        key="candles_interval",
        prompt="Enter candle interval (e.g. 1m, 5m) >>> ",
        prompt_on_new=True,
        default="1m",
        type_str="str"
    ),
    "candles_length": ConfigVar(
        key="candles_length",
        prompt="Enter number of candles for indicators (e.g. 30) >>> ",
        prompt_on_new=True,
        default=30,
        type_str="int"
    ),
}
def strategy_config_map() -> Dict[str, ConfigVar]:
    return combined_pmm_config_map

