import logging
from decimal import Decimal
from typing import Dict, List, Optional

import pandas as pd
import pandas_ta as ta
from hummingbot.connector.connector_base import ConnectorBase
from hummingbot.core.data_type.common import OrderType, PriceType, TradeType
from hummingbot.core.data_type.order_candidate import OrderCandidate
from hummingbot.core.event.events import BuyOrderCompletedEvent, OrderFilledEvent, SellOrderCompletedEvent
from hummingbot.data_feed.candles_feed.candles_factory import CandlesFactory
from hummingbot.strategy.script_strategy_base import ScriptStrategyBase
from hummingbot.connector.exchange.binance.binance_exchange import BinanceExchange


class PMMShiftedMidPriceDynamicSpread(ScriptStrategyBase):
    # Strategy configuration
    spread_base = Decimal("0.008")
    spread_multiplier = Decimal("1")
    price_source = PriceType.MidPrice
    price_multiplier = Decimal("1")
    order_refresh_time = 15
    order_amount = Decimal("7")
    trading_pair = "RLC-USDT"
    exchange = "binance"
    candle_interval = "3m"
    nair_period = 14

    # Tracking variables
    total_sell_orders = 0
    total_buy_orders = 0
    total_sell_volume = Decimal("0")
    total_buy_volume = Decimal("0")
    create_timestamp = 0
    mid_price = Decimal("0")
    reference_price = Decimal("0")

    markets = {exchange: {trading_pair}}

    def __init__(self, connectors: Dict[str, ConnectorBase]):
        super().__init__(connectors)
        self.candles = CandlesFactory.get_candle(
            connector=self.exchange,
            trading_pair=self.trading_pair,
            interval=self.candle_interval
        )
        self.candles.start()

    def on_stop(self):
        self.candles.stop()

    def on_tick(self):
        if self.create_timestamp <= self.current_timestamp and self.candles.is_ready:
            self.cancel_all_orders()
            self.update_multipliers()
            proposal = self.create_proposal()
            proposal_adjusted = self.adjust_proposal_to_budget(proposal)
            self.place_orders(proposal_adjusted)
            self.create_timestamp = self.order_refresh_time + self.current_timestamp

    def get_candles_with_features(self) -> pd.DataFrame:
        candles_df = self.candles.candles_df
        candles_df.ta.rsi(length=14, append=True)
        candles_df.ta.natr(length=14, scalar=0.5, append=True)
        return candles_df

    def update_multipliers(self):
        candles_df = self.get_candles_with_features()
        last_rsi = candles_df["RSI_14"].iloc[-1]
        last_natr = candles_df["NATR_14"].iloc[-1]
        
        self.price_multiplier = Decimal(str(((50 - last_rsi) / 50) * last_natr))
        self.spread_multiplier = Decimal(str(last_natr / float(self.spread_base)))
        self.mid_price = self.connectors[self.exchange].get_price_by_type(self.trading_pair, self.price_source)
        self.reference_price = self.mid_price * (Decimal("1") + self.price_multiplier)

    def create_proposal(self) -> List[OrderCandidate]:
        spread_adjusted = self.spread_multiplier * self.spread_base
        buy_price = self.reference_price * (Decimal("1") - spread_adjusted)
        sell_price = self.reference_price * (Decimal("1") + spread_adjusted)

        buy_order = OrderCandidate(
            trading_pair=self.trading_pair,
            is_maker=True,
            order_type=OrderType.LIMIT,
            order_side=TradeType.BUY,
            amount=self.order_amount,
            price=buy_price
        )

        sell_order = OrderCandidate(
            trading_pair=self.trading_pair,
            is_maker=True,
            order_type=OrderType.LIMIT,
            order_side=TradeType.SELL,
            amount=self.order_amount,
            price=sell_price
        )

        return [buy_order, sell_order]

    def cancel_all_orders(self):
        for order in self.get_active_orders(connector_name=self.exchange):
            self.cancel(self.exchange, order.trading_pair, order.client_order_id)

    def did_fill_order(self, event: OrderFilledEvent):
        msg = (f"{event.trade_type.name} {round(event.amount, 2)} {event.trading_pair} "
               f"at {round(event.price, 2)}")
        self.log_with_clock(logging.INFO, msg)
        if event.trade_type == TradeType.BUY:
            self.total_buy_volume += Decimal(str(event.amount))
        else:
            self.total_sell_volume += Decimal(str(event.amount))

    def did_complete_buy_order(self, event: BuyOrderCompletedEvent):
        self.total_buy_orders += 1

    def did_complete_sell_order(self, event: SellOrderCompletedEvent):
        self.total_sell_orders += 1

    def format_status(self) -> str:
        if not self.ready_to_trade:
            return "Market connectors are not ready."
        
        status = []
        # Exchange balances
        status.extend(["\nExchange Asset Total Balance Available Balance"])
        for connector_name, connector in self.connectors.items():
            for asset, balance in connector.get_balances().items():
                if asset in ["RLC", "USDT"]:
                    status.append(f"{connector_name: <10}{asset: <8}{balance.total_balance: <15.5f}"
                                  f"{balance.available_balance: <15.5f}")

        # Active orders
        status.append("\nOrders:")
        status.append("Exchange Market Side Price Amount Age")
        for order in self.get_active_orders(self.exchange):
            age = pd.Timestamp(self.current_timestamp, unit='s') - pd.Timestamp(order.creation_timestamp, unit='s')
            status.append(f"{self.exchange: <10}{order.trading_pair: <8}{order.trade_type.name: <6}"
                          f"{order.price: <8.5f}{order.amount: <10.5f}{age}")

        # Strategy metrics
        status.append(f"\nTotal Buy Orders: {self.total_buy_orders} | Total Sell Orders: {self.total_sell_orders}")
        status.append(f"Total Buy Volume: {self.total_buy_volume:.2f} | Total Sell Volume: {self.total_sell_volume:.2f}")
        status.append(f"Spread Base: {self.spread_base:.4f} | Spread Adjusted: {float(self.spread_multiplier * self.spread_base):.4f} | "
                      f"Spread Multiplier: {self.spread_multiplier:.4f}")
        status.append(f"Mid Price: {self.mid_price:.4f} | Price shifted: {self.reference_price:.4f} | "
                      f"Price Multiplier: {self.price_multiplier:.4f}")

        # Candle data
        if self.candles.is_ready:
            candles_df = self.get_candles_with_features()
            status.append(f"\nCandles: {self.exchange}_{self.trading_pair} | Interval: {self.candle_interval}")
            status.append("timestamp open high low close volume RSI_14 NATR_14")
            for index, row in candles_df.tail().iterrows():
                status.append(f"{index} {row['open']:.3f} {row['high']:.3f} {row['low']:.3f} {row['close']:.3f} "
                              f"{row['volume']:.1f} {row['RSI_14']:.2f} {row['NATR_14']:.6f}")

        return "\n".join(status)