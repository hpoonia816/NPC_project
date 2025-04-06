# pure_mm_custom.pyx
from hummingbot.strategy.strategy_base import StrategyBase
from hummingbot.connector.connector_base import ConnectorBase
from hummingbot.core.event.events import OrderType, TradeType
from decimal import Decimal
import numpy as np
import time


class PureMMCustomStrategy(StrategyBase):
    def __init__(self,
                 exchange: ConnectorBase,
                 trading_pair: str,
                 order_amount: Decimal,
                 bid_spread: Decimal,
                 ask_spread: Decimal,
                 inventory_skew_enabled: bool = False,
                 inventory_target_base_pct: Decimal = Decimal("0.5"),
                 ema_period: int = 20,
                 rsi_period: int = 14,
                 bollinger_period: int = 20,
                 bollinger_dev: float = 2.0):

        super().__init__()
        self._exchange = exchange
        self._trading_pair = trading_pair
        self._order_amount = order_amount
        self._bid_spread = bid_spread
        self._ask_spread = ask_spread
        self._inventory_skew_enabled = inventory_skew_enabled
        self._inventory_target_base_pct = inventory_target_base_pct
        self._ema_period = ema_period
        self._rsi_period = rsi_period
        self._bollinger_period = bollinger_period
        self._bollinger_dev = bollinger_dev
        self._prices = []

    def on_tick(self):
        mid_price = self._exchange.get_mid_price(self._trading_pair)
        if mid_price is None:
            return

        self._prices.append(mid_price)
        if len(self._prices) > max(self._ema_period, self._rsi_period, self._bollinger_period):
            self._prices.pop(0)

        if len(self._prices) < max(self._ema_period, self._rsi_period, self._bollinger_period):
            return

        bid_price, ask_price = self._calculate_order_prices(mid_price)

        self.cancel_all_orders()
        self.place_orders(bid_price, ask_price)

    def place_orders(self, bid_price, ask_price):
        self.place_order(
            self._exchange,
            self._trading_pair,
            TradeType.BUY,
            OrderType.LIMIT,
            Decimal(str(bid_price)),
            self._order_amount,
        )

        self.place_order(
            self._exchange,
            self._trading_pair,
            TradeType.SELL,
            OrderType.LIMIT,
            Decimal(str(ask_price)),
            self._order_amount,
        )

    def _calculate_order_prices(self, mid_price):
        # Indicators
        ema = self._ema(self._prices, self._ema_period)
        rsi = self._rsi(self._prices, self._rsi_period)
        upper_band, lower_band = self._bollinger_bands(self._prices, self._bollinger_period, self._bollinger_dev)

        bid_spread_adj = self._bid_spread
        ask_spread_adj = self._ask_spread

        if rsi < 30:
            bid_spread_adj *= Decimal("0.8")  # bullish signal
        elif rsi > 70:
            ask_spread_adj *= Decimal("0.8")  # bearish signal

        if self._inventory_skew_enabled:
            base_balance = self._exchange.get_balance(self._trading_pair.split("-")[0])
            quote_balance = self._exchange.get_balance(self._trading_pair.split("-")[1])
            price = mid_price
            total_value = base_balance * price + quote_balance
            target_base = total_value * self._inventory_target_base_pct / price

            if base_balance < target_base:
                bid_spread_adj *= Decimal("0.9")
            elif base_balance > target_base:
                ask_spread_adj *= Decimal("0.9")

        bid_price = mid_price * (Decimal("1") - bid_spread_adj)
        ask_price = mid_price * (Decimal("1") + ask_spread_adj)
        return bid_price, ask_price

    def _ema(self, prices, period):
        weights = np.exp(np.linspace(-1., 0., period))
        weights /= weights.sum()
        return np.convolve(prices, weights, mode='valid')[-1]

    def _rsi(self, prices, period):
        deltas = np.diff(prices)
        seed = deltas[:period+1]
        up = seed[seed >= 0].sum() / period
        down = -seed[seed < 0].sum() / period
        rs = up / down if down != 0 else 0
        rsi = 100. - 100. / (1. + rs)
        return rsi

    def _bollinger_bands(self, prices, period, num_std_dev):
        prices_np = np.array(prices[-period:])
        sma = np.mean(prices_np)
        std = np.std(prices_np)
        upper_band = sma + num_std_dev * std
        lower_band = sma - num_std_dev * std
        return upper_band, lower_band
