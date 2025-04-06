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

# Replace with your actual config or pass through environment variables
BINANCE_API_KEY = global_config_map["binance_api_key"].value
BINANCE_API_SECRET = global_config_map["binance_api_secret"].value
TRADING_PAIR = "RLC-USDT"
ORDER_AMOUNT = 1.0
SPREAD_PERCENT = 0.002  # 0.2%

class EnhancedMarketMaker(ScriptStrategyBase):
    """
    Enhanced Binance Market Making Strategy with:
    - Secure API key handling
    - Dynamic spread
    - Candlestick indicator-based logic (RSI + NATR)
    - Status panel like Hummingbot CLI output
    """
    def __init__(self):
        super().__init__()
        self.binance = self.init_binance()
        self.rsi = 50.0
        self.natr = 0.0
        self.price_shift = 0.0
        self.mid_price = 0.0
        self.status_text = ""

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
        mid_price = self.get_mid_price()
        self.mid_price = mid_price

        bid_price, ask_price = self.calculate_prices(mid_price)
        self.cancel_all_orders()
        self.place_orders(bid_price, ask_price)
        self.display_status()

    def get_mid_price(self) -> float:
        return float(self.binance.get_price_by_type(TRADING_PAIR, PriceType.MidPrice))

    def fetch_indicators(self):
        try:
            candles = self.fetch_candles()
            if len(candles) < 15:
                return

            df = pd.DataFrame(candles)
            df.columns = ["timestamp", "open", "high", "low", "close", "volume"]
            self.rsi = ta.rsi(df["close"], length=14).iloc[-1]
            self.natr = ta.natr(df["high"], df["low"], df["close"], length=14).iloc[-1]
            self.price_shift = 0.002 * (1 if self.rsi > 60 else -1 if self.rsi < 40 else 0)
        except Exception as e:
            self.logger().error(f"Indicator calculation error: {e}")

    def fetch_candles(self):
        return MarketDataProvider().get_candles_df(
            connector_name="binance",
            trading_pair=TRADING_PAIR,
            interval="3m",
            max_records=30
        ).tail(15).values.tolist()

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

    def display_status(self):
        self.logger().info("\n" + "=" * 80)
        self.logger().info(f"Exchange Asset        | Price       | Spread Multiplier: {self.natr:.4f}")
        self.logger().info(f"Mid Price: {self.mid_price:.4f} | Shifted: {self.mid_price * (1 + self.price_shift):.4f} | RSI: {self.rsi:.2f} | NATR: {self.natr:.4f}")
        self.logger().info("=" * 80)
