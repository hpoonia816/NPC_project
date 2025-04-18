#!/usr/bin/env python
import logging
import pandas as pd
import pandas_ta as ta
from decimal import Decimal
from typing import Tuple, Dict
import os
import yaml

from hummingbot.strategy.script_strategy_base import ScriptStrategyBase
from hummingbot.core.data_type.common import OrderType, PriceType, TradeType
from hummingbot.connector.exchange_base import ExchangeBase
from hummingbot.core.data_type.order_candidate import OrderCandidate
from hummingbot.core.event.events import OrderFilledEvent
from hummingbot.client.config.config_data_types import BaseClientModel, ClientFieldData
from pydantic import Field

# Explanation: 
# It places dynamic bid and ask orders around the mid-price, adjusting spread width based on market volatility (NATR) and shifting price based on trend direction (RSI).It includes inventory-based spread skew to auto-balance asset holdings, and a circuit breaker that halts trading during extreme volatility.Order sizes are also adjusted dynamically based on portfolio value, making it a responsive, risk-aware market making solution.

# Config Class for User Inputs

class EnhancedConfig(BaseClientModel):
    script_file_name: str = Field(default_factory=lambda: os.path.basename(__file__))
    exchange: str = Field("binance", client_data=ClientFieldData(prompt_on_new=True))
    trading_pair: str = Field("RLC-USDT", client_data=ClientFieldData(prompt_on_new=True))
    order_amount: Decimal = Field(1, client_data=ClientFieldData(prompt_on_new=True))
    spread: Decimal = Field(0.002, client_data=ClientFieldData(prompt_on_new=True))
    interval: int = Field(15, client_data=ClientFieldData(prompt_on_new=True))
    max_position_ratio: Decimal = Field(0.2, client_data=ClientFieldData(prompt_on_new=True))
    volatility_threshold: Decimal = Field(0.15, client_data=ClientFieldData(prompt_on_new=True))


# Strategy Class

class EnhancedMM(ScriptStrategyBase):
    def __init__(self, connectors: Dict[str, ExchangeBase], config: EnhancedConfig):
        super().__init__(connectors)
        self.config = config
        self.last_tick = 0
        self.rsi = 50
        self.natr = 0.0
        self.shift = 0.0
        self.bid_price = 0.0
        self.ask_price = 0.0
        self.mid_price = 0.0
        self.base_balance = Decimal(0)
        self.quote_balance = Decimal(0)

    def on_tick(self):
        if self.current_timestamp < self.last_tick + self.config.interval:
            return

        try:
            self.cancel_all_orders()
            self.fetch_indicators()
            self.fetch_inventory()

            if self.natr > self.config.volatility_threshold:
                self.logger().warning("[CIRCUIT BREAKER] High volatility detected. Skipping order placement.")
                return

            self.mid_price = self.connectors[self.config.exchange].get_price_by_type(
                self.config.trading_pair, PriceType.MidPrice)

            spread_multiplier = 1 + self.natr * 0.01
            shifted_mid = self.mid_price * (1 + self.shift)

            inventory_ratio = self.base_balance * self.mid_price / (self.base_balance * self.mid_price + self.quote_balance + 1e-8)
            inventory_asymmetry = 1 + ((0.5 - inventory_ratio) * 2)

            bid_price = shifted_mid * (1 - self.config.spread * spread_multiplier * (2 - inventory_asymmetry))
            ask_price = shifted_mid * (1 + self.config.spread * spread_multiplier * inventory_asymmetry)

            position_value = self.base_balance * self.mid_price + self.quote_balance
            position_size = min(self.config.order_amount, position_value * self.config.max_position_ratio / self.mid_price)

            self.bid_price = bid_price
            self.ask_price = ask_price

            buy_order = OrderCandidate(self.config.trading_pair, True, OrderType.LIMIT, TradeType.BUY,
                                       position_size, Decimal(str(bid_price)))
            sell_order = OrderCandidate(self.config.trading_pair, True, OrderType.LIMIT, TradeType.SELL,
                                        position_size, Decimal(str(ask_price)))

            orders = self.connectors[self.config.exchange].budget_checker.adjust_candidates([buy_order, sell_order])

            for order in orders:
                self.place_order(self.config.exchange, order)

            self.last_tick = self.current_timestamp

        except Exception as e:
            self.logger().error(f"Tick Error: {e}", exc_info=True)

    def fetch_indicators(self):
        candles_df = self.connectors[self.config.exchange].get_candles(
            self.config.trading_pair, "3m")[-30:]
        df = pd.DataFrame(candles_df, columns=["timestamp", "open", "high", "low", "close", "volume"])
        self.rsi = ta.rsi(df["close"], length=14).iloc[-1]
        self.natr = ta.natr(df["high"], df["low"], df["close"], length=14).iloc[-1]
        self.shift = 0.002 * (1 if self.rsi > 60 else -1 if self.rsi < 40 else 0)

    def fetch_inventory(self):
        self.base_balance = self.connectors[self.config.exchange].get_balance(self.config.trading_pair.split("-")[0])
        self.quote_balance = self.connectors[self.config.exchange].get_balance(self.config.trading_pair.split("-")[1])

    def format_status(self) -> str:
        return "\n".join([
            f"Enhanced Market Maker - {self.config.exchange} {self.config.trading_pair}",
            f"Mid Price          : {self.mid_price:.4f}",
            f"Shifted Mid Price  : {self.mid_price * (1 + self.shift):.4f}",
            f"Bid Price          : {self.bid_price:.4f}",
            f"Ask Price          : {self.ask_price:.4f}",
            f"RSI_14             : {self.rsi:.2f}",
            f"NATR_14            : {self.natr:.4f}",
            f"Spread Multiplier  : {(1 + self.natr * 0.01):.4f}",
            f"Price Shift Factor : {self.shift:.4f}",
            f"Base Inventory     : {self.base_balance:.4f}",
            f"Quote Inventory    : {self.quote_balance:.2f}"
        ])

    def did_fill_order(self, event: OrderFilledEvent):
        msg = f"FILLED: {event.trade_type.name} {event.amount} {event.trading_pair} at {event.price}"
        self.log_with_clock(logging.INFO, msg)
        self.notify_hb_app_with_timestamp(msg)

    def cancel_all_orders(self):
        for order in self.get_active_orders(self.config.exchange):
            self.cancel(self.config.exchange, order.trading_pair, order.client_order_id)

    def place_order(self, connector_name: str, order: OrderCandidate):
        if order.order_side == TradeType.SELL:
            self.sell(connector_name, order.trading_pair, order.amount, order.order_type, order.price)
        else:
            self.buy(connector_name, order.trading_pair, order.amount, order.order_type, order.price)

    @classmethod
    def init_markets(cls, config: EnhancedConfig):
        cls.markets = {config.exchange: {config.trading_pair}}
