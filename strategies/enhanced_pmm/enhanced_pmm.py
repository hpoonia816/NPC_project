import logging
from decimal import Decimal
from typing import Dict, List
import os

import pandas as pd
import pandas_ta as ta
from hummingbot.connector.connector_base import ConnectorBase
from hummingbot.core.data_type.common import OrderType, PriceType, TradeType
from hummingbot.core.event.events import BuyOrderCompletedEvent, OrderFilledEvent, SellOrderCompletedEvent
from hummingbot.strategy.script_strategy_base import ScriptStrategyBase
from hummingbot.connector.exchange.binance.binance_exchange import BinanceExchange


class EnhancedPMM(ScriptStrategyBase):
    trading_pair = "RLC-USDT"
    exchange = "binance"
    order_amount = Decimal("7")
    spread_base = Decimal("0.008")
    spread_multiplier = Decimal("1")
    price_source = PriceType.MidPrice
    price_multiplier = Decimal("1")
    order_refresh_time = 15
    candle_interval = "3m"
    
    total_buy_orders = 0
    total_sell_orders = 0
    total_buy_volume = Decimal("0")
    total_sell_volume = Decimal("0")
    
    markets = {exchange: {trading_pair}}

    def __init__(self, connectors: Dict[str, ConnectorBase]):
        super().__init__(connectors)
        self.binance = connectors[self.exchange]
        self.candles = self.initialize_candles()

    def initialize_candles(self):
        from hummingbot.data_feed.candles_feed.candles_factory import CandlesFactory
        candles = CandlesFactory.get_candle(
            connector=self.exchange, trading_pair=self.trading_pair, interval=self.candle_interval
        )
        candles.start()
        return candles

    def on_stop(self):
        self.candles.stop()

    def on_tick(self):
        if self.candles.is_ready:
            self.cancel_all_orders()
            self.update_multipliers()
            self.execute_orders()

    def update_multipliers(self):
        candles_df = self.get_candles_with_features()
        last_rsi = candles_df["RSI_14"].iloc[-1]
        last_natr = candles_df["NATR_14"].iloc[-1]
        
        self.price_multiplier = Decimal(str(((50 - last_rsi) / 50) * last_natr))
        self.spread_multiplier = Decimal(str(last_natr / float(self.spread_base)))
        self.mid_price = self.binance.get_price_by_type(self.trading_pair, self.price_source)
        self.reference_price = self.mid_price * (Decimal("1") + self.price_multiplier)

    def get_candles_with_features(self) -> pd.DataFrame:
        candles_df = self.candles.candles_df
        candles_df.ta.rsi(length=14, append=True)
        candles_df.ta.natr(length=14, scalar=0.5, append=True)
        return candles_df

    def execute_orders(self):
        spread_adjusted = self.spread_multiplier * self.spread_base
        bid_price = self.reference_price * (Decimal("1") - spread_adjusted)
        ask_price = self.reference_price * (Decimal("1") + spread_adjusted)
        
        self.buy(
            connector_name=self.exchange,
            trading_pair=self.trading_pair,
            amount=self.order_amount,
            price=bid_price.quantize(Decimal("0.0001")),
            order_type=OrderType.LIMIT
        )
        
        self.sell(
            connector_name=self.exchange,
            trading_pair=self.trading_pair,
            amount=self.order_amount,
            price=ask_price.quantize(Decimal("0.0001")),
            order_type=OrderType.LIMIT
        )

    def cancel_all_orders(self):
        for order in self.get_active_orders(self.exchange):
            self.cancel(self.exchange, order.trading_pair, order.client_order_id)

    def did_fill_order(self, event: OrderFilledEvent):
        if event.trade_type == TradeType.BUY:
            self.total_buy_orders += 1
            self.total_buy_volume += Decimal(str(event.amount))
        else:
            self.total_sell_orders += 1
            self.total_sell_volume += Decimal(str(event.amount))
        
        self.logger().info(f"Filled {event.trade_type.name}: {event.amount} {event.trading_pair} at {event.price}")

    def format_status(self) -> str:
        status = ["Market Making Status:"]
        status.append(f"Total Buy Orders: {self.total_buy_orders} | Total Sell Orders: {self.total_sell_orders}")
        status.append(f"Total Buy Volume: {self.total_buy_volume} | Total Sell Volume: {self.total_sell_volume}")
        status.append(f"Mid Price: {self.mid_price} | Reference Price: {self.reference_price}")
        return "\n".join(status)
