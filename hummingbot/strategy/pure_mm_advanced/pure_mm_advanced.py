from hummingbot.strategy.script_strategy_base import ScriptStrategyBase
from hummingbot.connector.connector_base import ConnectorBase
import numpy as np
import time
from statistics import mean

class PureMMAdvancedStrategy(ScriptStrategyBase):
    def __init__(self):
        super().__init__()
        self.exchange = "binance_paper_trade"
        self.trading_pair = "ETH-USDT"

        # === Strategy Config ===
        self.order_amount = 0.01
        self.spread = 0.002
        self.max_inventory_percent = 0.8
        self.min_inventory_percent = 0.2
        self.inventory_skew_enabled = True

        # === Risk Management ===
        self.stop_loss_threshold = 0.02  # 2%
        self.cooldown_period = 300  # seconds
        self.last_stop_loss_time = 0
        self.entry_price = None

        # === Indicators ===
        self.price_history = []
        self.fast_ema_period = 5
        self.slow_ema_period = 15
        self.rsi_period = 14

    def on_tick(self):
        if not self.connector_ready(self.exchange):
            self.logger().info("Waiting for connector to be ready...")
            return

        mid_price = self.get_price()
        if mid_price is None:
            return

        self.price_history.append(mid_price)
        if len(self.price_history) > max(self.slow_ema_period, self.rsi_period, 20):
            self.price_history.pop(0)

        if len(self.price_history) < max(self.slow_ema_period, self.rsi_period):
            return  # Wait for indicators to warm up

        # === Risk Check: Stop-loss ===
        if self.entry_price:
            pnl = (mid_price - self.entry_price) / self.entry_price
            if pnl < -self.stop_loss_threshold:
                self.logger().warning(f"Stop-loss triggered: {pnl:.2%}. Cooling down.")
                self.cancel_all_orders()
                self.last_stop_loss_time = time.time()
                self.entry_price = None
                return

        # === Cooldown after stop-loss ===
        if time.time() - self.last_stop_loss_time < self.cooldown_period:
            self.logger().info("Cooling down after stop-loss...")
            return

        # === Indicators ===
        fast_ema = self.ema(self.price_history, self.fast_ema_period)
        slow_ema = self.ema(self.price_history, self.slow_ema_period)
        rsi = self.rsi(self.price_history, self.rsi_period)
        upper_bb, lower_bb = self.bollinger_bands(self.price_history)

        if not all([fast_ema, slow_ema, rsi, upper_bb, lower_bb]):
            return

        self.cancel_all_orders()

        # === Dynamic Spread ===
        volatility = np.std(self.price_history)
        dynamic_spread = self.spread + (volatility / mid_price)

        # === Inventory Skew Logic ===
        base_balance = self.connectors[self.exchange].get_balance(self.trading_pair.split("-")[0])
        quote_balance = self.connectors[self.exchange].get_balance(self.trading_pair.split("-")[1])
        total_value = base_balance * mid_price + quote_balance

        base_pct = (base_balance * mid_price) / total_value if total_value > 0 else 0.5
        skew = 0

        if self.inventory_skew_enabled:
            if base_pct < self.min_inventory_percent:
                skew = -0.001
            elif base_pct > self.max_inventory_percent:
                skew = 0.001

        bid_price = max(lower_bb, mid_price * (1 - dynamic_spread + skew))
        ask_price = min(upper_bb, mid_price * (1 + dynamic_spread + skew))

        # === Market Bias: EMA and RSI ===
        if fast_ema > slow_ema and rsi < 70:
            # Bullish Bias
            self.buy(self.exchange, self.trading_pair, bid_price, self.order_amount)
            self.sell(self.exchange, self.trading_pair, ask_price * 1.01, self.order_amount)
        elif fast_ema < slow_ema and rsi > 30:
            # Bearish Bias
            self.buy(self.exchange, self.trading_pair, bid_price * 0.99, self.order_amount)
            self.sell(self.exchange, self.trading_pair, ask_price, self.order_amount)
        else:
            # Neutral Market
            self.buy(self.exchange, self.trading_pair, bid_price, self.order_amount)
            self.sell(self.exchange, self.trading_pair, ask_price, self.order_amount)

        # Set entry price for stop-loss monitoring
        self.entry_price = mid_price

    def get_price(self):
        return self.connectors[self.exchange].get_mid_price(self.trading_pair)

    def ema(self, prices, period):
        if len(prices) < period:
            return None
        return np.mean(prices[-period:])  # Simplified EMA for now

    def rsi(self, prices, period):
        if len(prices) < period + 1:
            return None
        deltas = np.diff(prices[-(period + 1):])
        ups = deltas[deltas > 0].sum() / period
        downs = -deltas[deltas < 0].sum() / period
        if downs == 0:
            return 100
        rs = ups / downs
        return 100 - (100 / (1 + rs))

    def bollinger_bands(self, prices):
        if len(prices) < 20:
            return None, None
        sma = mean(prices[-20:])
        stddev = np.std(prices[-20:])
        return sma + 2 * stddev, sma - 2 * stddev
