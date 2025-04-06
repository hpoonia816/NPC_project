from hummingbot.client.config.config_var import ConfigVar
from hummingbot.client.config.config_validators import validate_decimal, validate_bool
from decimal import Decimal

pure_mm_custom_config_map = {
    "strategy": ConfigVar(
        key="strategy",
        prompt="",
        default="pure_mm_custom",
    ),
    "exchange": ConfigVar(
        key="exchange",
        prompt="Enter the name of the exchange (e.g., binance_paper_trade): ",
        type_str="str",
    ),
    "market": ConfigVar(
        key="market",
        prompt="Enter the trading pair you would like to trade (e.g., ETH-USDT): ",
        type_str="str",
    ),
    "order_amount": ConfigVar(
        key="order_amount",
        prompt="Enter the order amount: ",
        type_str="decimal",
        validator=validate_decimal,
        default=Decimal("0.01"),
    ),
    "bid_spread": ConfigVar(
        key="bid_spread",
        prompt="Enter the bid spread (percentage): ",
        type_str="decimal",
        validator=validate_decimal,
        default=Decimal("0.01"),
    ),
    "ask_spread": ConfigVar(
        key="ask_spread",
        prompt="Enter the ask spread (percentage): ",
        type_str="decimal",
        validator=validate_decimal,
        default=Decimal("0.01"),
    ),
    "inventory_skew_enabled": ConfigVar(
        key="inventory_skew_enabled",
        prompt="Enable inventory skew? (True/False): ",
        type_str="bool",
        validator=validate_bool,
        default=False,
    ),
    # Add additional configuration parameters as needed
}
