
#!/usr/bin/env python
import logging
import pandas as pd
import pandas_ta as ta
from decimal import Decimal
from typing import Tuple
from hummingbot.strategy.script_strategy_base import ScriptStrategyBase
from hummingbot.core.data_type.common import OrderType, PriceType
from hummingbot.connector.exchange.binance.binance_exchange import BinanceExchange
from hummingbot.client.config.global_config_map import global_config_map
from hummingbot.data_feed.market_data_provider import MarketDataProvider

# Replace with actual config values or from env
BINANCE_API_KEY = global_config_map["binance_api_key"].value
BINANCE_API_SECRET = global_config_map["binance_api_secret"].value
TRADING_PAIR = "RLC-USDT"
ORDER_AMOUNT = 1.0
SPREAD_PERCENT = 0.002  # 0.2%

class EnhancedMarketMaker(ScriptStrategyBase):
    def __init__(self):
        super().__init__()
        self.binance = self.init_binance()
        self.rsi = 50.0
        self.natr = 0.0
        self.price_shift = 0.0
        self.mid_price = 0.0
        self._initialize_status_display()

    def init_binance(self):
        if not BINANCE_API_KEY or not BINANCE_API_SECRET:
            raise ValueError("Binance API keys not configured!")
        return BinanceExchange(
            binance_api_key=BINANCE_API_KEY,
            binance_api_secret=BINANCE_API_SECRET,
            trading_pairs=[TRADING_PAIR]
        )

    def on_tick(self):
        self.fetch_indicators()
        self.mid_price = self.get_mid_price()

        bid_price, ask_price = self.calculate_prices(self.mid_price)
        self.cancel_all_orders()
        self.place_orders(bid_price, ask_price)
        self._update_status()

    def get_mid_price(self) -> float:
        return float(self.binance.get_price_by_type(TRADING_PAIR, PriceType.MidPrice))

    def fetch_indicators(self):
        try:
            candles_df = MarketDataProvider().get_candles_df(
                connector_name="binance",
                trading_pair=TRADING_PAIR,
                interval="3m",
                max_records=30
            ).tail(15)

            self.rsi = ta.rsi(candles_df["close"], length=14).iloc[-1]
            self.natr = ta.natr(candles_df["high"], candles_df["low"], candles_df["close"], length=14).iloc[-1]
            self.price_shift = 0.002 * (1 if self.rsi > 60 else -1 if self.rsi < 40 else 0)
        except Exception as e:
            self.logger().error(f"Indicator calculation error: {e}")

    def calculate_prices(self, mid_price: float) -> Tuple[float, float]:
        spread_multiplier = 1 + self.natr * 0.01
        spread = SPREAD_PERCENT * spread_multiplier
        shifted_mid = mid_price * (1 + self.price_shift)
        bid = round(shifted_mid * (1 - spread), 4)
        ask = round(shifted_mid * (1 + spread), 4)
        return bid, ask

    def cancel_all_orders(self):
        for order in self.get_active_orders("binance"):
            self.cancel("binance", order.trading_pair, order.client_order_id)

    def place_orders(self, bid: float, ask: float):
        self.buy("binance", TRADING_PAIR, Decimal(str(ORDER_AMOUNT)), Decimal(str(bid)), OrderType.LIMIT)
        self.sell("binance", TRADING_PAIR, Decimal(str(ORDER_AMOUNT)), Decimal(str(ask)), OrderType.LIMIT)

    def _initialize_status_display(self):
        self._live_data = {
            "Mid Price": lambda: f"{self.mid_price:.4f}",
            "Shifted Price": lambda: f"{self.mid_price * (1 + self.price_shift):.4f}",
            "RSI_14": lambda: f"{self.rsi:.2f}",
            "NATR_14": lambda: f"{self.natr:.4f}",
            "Spread Multiplier": lambda: f"{(1 + self.natr * 0.01):.4f}",
            "Price Multiplier": lambda: f"{self.price_shift:.4f}"
        }

    def format_status(self) -> str:
        lines = []
        lines.append("Enhanced MM | Binance Spot | Pair: " + TRADING_PAIR)
        lines.append("-" * 60)
        for key, value_fn in self._live_data.items():
            lines.append(f"{key:20}: {value_fn()}")
        lines.append("-" * 60)
        return "\n".join(lines)
