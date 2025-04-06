# advanced_pmm.py
import logging
import pandas as pd
import pandas_ta as ta
import numpy as np
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, List, Tuple
from hummingbot.strategy.pure_market_making import PureMarketMakingStrategy
from hummingbot.core.data_type import OrderBook
from hummingbot.core.event.events import (
    OrderFilledEvent, 
    OrderType, 
    TradeType,
    OrderBookEvent,
    OrderCancelledEvent,
    MarketEvent
)
from hummingbot.core.data_type.common import PriceType
from hummingbot.core.utils.async_utils import safe_ensure_future

class AdvancedPMMStrategy(PureMarketMakingStrategy):
    """
    Complete Market Making Strategy with:
    - Volatility-adjusted spreads (ATR + Bollinger Bands)
    - Trend-aware pricing (MACD + SMA)
    - Inventory risk management
    - Dynamic position sizing
    - Circuit breakers
    """

    def __init__(self,
                 bid_spread: float,
                 ask_spread: float,
                 order_amount: float,
                 volatility_period: int = 20,
                 trend_period: int = 50,
                 risk_threshold: float = 0.3,
                 max_position_ratio: float = 0.2,
                 emergency_stop_vol: float = 0.2,
                 **kwargs):
        
        super().__init__(
            bid_spread=bid_spread,
            ask_spread=ask_spread,
            order_amount=order_amount,
            **kwargs
        )

        # Volatility Configuration
        self.volatility_period = volatility_period
        self.atr_period = 14
        self.emergency_stop_vol = emergency_stop_vol
        self.current_volatility = 0.0

        # Trend Analysis
        self.trend_period = trend_period
        self.macd_fast = 12
        self.macd_slow = 26
        self.macd_signal = 9
        self.trend_score = 0.5

        # Risk Management
        self.risk_threshold = risk_threshold
        self.max_position_ratio = max_position_ratio
        self.inventory_asymmetry = 1.0
        self.position_size = order_amount
        self.last_rebalance = datetime.now()

        # Order Management
        self._order_refresh_time = 10
        self._event_listeners = []
        self.register_events()

    def register_events(self):
        """Register required event listeners"""
        self._event_listeners.append(
            self._order_book_tracker.order_book.add_listener(
                OrderBookEvent.Diff, self._order_book_diff_listener)
        )
        self._event_listeners.append(
            self.add_listener(MarketEvent.OrderFilled, self._order_filled_listener)
        )

    async def _order_book_diff_listener(self, event_tag: int, payload: Dict):
        """Trigger order refresh on market changes"""
        safe_ensure_future(self.active_order_refresh())

    def _order_filled_listener(self, event_tag: int, payload: OrderFilledEvent):
        """Handle inventory changes after fills"""
        self.logger().info(f"Order filled: {payload}")
        safe_ensure_future(self.active_order_refresh())

    # ------------------------------
    # Core Analytics Engine
    # ------------------------------
    
    async def calculate_volatility(self):
        """Calculate multi-factor volatility"""
        candles = await self.connector.get_candles(
            self.trading_pair, interval="5m", limit=100
        )
        df = pd.DataFrame(candles, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        
        # ATR Calculation
        df['ATR'] = ta.atr(df['high'], df['low'], df['close'], length=self.atr_period)
        
        # Bollinger Band Width
        bbands = ta.bbands(df['close'], length=self.volatility_period)
        df['BB_width'] = (bbands['BBU_5_2.0'] - bbands['BBL_5_2.0']) / bbands['BBM_5_2.0']
        
        # Historical Volatility
        returns = np.log(df['close']).diff()
        hist_vol = returns.rolling(self.volatility_period).std() * np.sqrt(365)
        
        # Composite Score
        self.current_volatility = 0.4*df['ATR'].iloc[-1] + 0.3*df['BB_width'].iloc[-1] + 0.3*hist_vol.iloc[-1]

    async def analyze_trend(self):
        """Calculate trend strength and direction"""
        candles = await self.connector.get_candles(
            self.trading_pair, interval="15m", limit=100
        )
        df = pd.DataFrame(candles, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        
        # MACD Analysis
        macd = ta.macd(df['close'], fast=self.macd_fast, slow=self.macd_slow, signal=self.macd_signal)
        macd_signal = 1 if macd['MACDh_12_26_9'].iloc[-1] > 0 else -1
        
        # SMA Trend
        sma = ta.sma(df['close'], length=self.trend_period)
        ma_signal = 1 if df['close'].iloc[-1] > sma.iloc[-1] else -1
        
        # Price Action
        recent_highs = df['high'].rolling(5).max()
        recent_lows = df['low'].rolling(5).min()
        pa_signal = 1 if (df['high'].iloc[-1] == recent_highs.iloc[-1]) else -1
        
        self.trend_score = (macd_signal + ma_signal + pa_signal) / 3

    def calculate_inventory_risk(self):
        """Dynamic inventory risk assessment"""
        base_balance = self.connector.get_balance(self.base_asset)
        quote_balance = self.connector.get_balance(self.quote_asset)
        mid_price = self.get_price()
        
        total_value = (base_balance * mid_price) + quote_balance
        target_base = total_value * 0.5 / mid_price  # 50/50 inventory target
        
        inventory_deviation = abs(base_balance - target_base) / target_base
        self.inventory_asymmetry = 1 + (2 * (base_balance - target_base)/target_base)
        
        return inventory_deviation

    # ------------------------------
    # Risk-Managed Order Placement
    # ------------------------------
    
    async def active_order_refresh(self):
        """Main order management logic"""
        try:
            if self.current_volatility > self.emergency_stop_vol:
                self.logger().warning("Volatility stop triggered!")
                await self.cancel_all_orders()
                return

            # Cancel existing orders
            await self.cancel_all_orders()

            # Update analytics
            await self.calculate_volatility()
            await self.analyze_trend()
            inventory_risk = self.calculate_inventory_risk()

            # Dynamic position sizing
            self.position_size = self.calculate_position_size()
            
            # Calculate adjusted spreads
            bid_spread, ask_spread = self.calculate_spreads(inventory_risk)
            
            # Calculate order prices
            mid_price = self.get_price()
            bid_price = mid_price * Decimal(1 - bid_spread)
            ask_price = mid_price * Decimal(1 + ask_spread)

            # Place orders
            await self.place_order(TradeType.BUY, bid_price, self.position_size)
            await self.place_order(TradeType.SELL, ask_price, self.position_size)

            self.logger().info(f"""
            Placed Orders:
            BUY: {self.position_size:.4f} @ {bid_price:.4f}
            SELL: {self.position_size:.4f} @ {ask_price:.4f}
            Volatility: {self.current_volatility:.4f}
            Trend Score: {self.trend_score:.2f}
            Inventory Risk: {inventory_risk:.2%}
            """)

        except Exception as e:
            self.logger().error(f"Order Error: {str(e)}", exc_info=True)

    def calculate_position_size(self):
        """Volatility-adjusted position sizing"""
        base_balance = self.connector.get_balance(self.base_asset)
        quote_balance = self.connector.get_balance(self.quote_asset)
        total_value = (base_balance * self.get_price()) + quote_balance
        
        # Volatility scaling
        vol_factor = 1 - min(1, self.current_volatility / 0.2)
        
        # Max position size
        max_size = total_value * self.max_position_ratio * vol_factor
        
        return min(max_size, self.order_amount)

    def calculate_spreads(self, inventory_risk: float):
        """Calculate risk-adjusted spreads"""
        # Base volatility adjustment
        vol_adj = 1 + (self.current_volatility / 0.1)
        
        # Trend adjustment
        trend_adj = 1 + (abs(self.trend_score) * 0.5)
        
        # Risk mitigation
        risk_adj = 1 - (min(inventory_risk, self.risk_threshold) / self.risk_threshold)
        
        # Calculate raw spreads
        bid_spread = self.bid_spread * vol_adj * trend_adj * risk_adj
        ask_spread = self.ask_spread * vol_adj * trend_adj * risk_adj
        
        # Apply inventory asymmetry
        bid_spread *= (2 - self.inventory_asymmetry)
        ask_spread *= self.inventory_asymmetry
        
        return max(0.0001, bid_spread), max(0.0001, ask_spread)

    # ------------------------------
    # Monitoring & Diagnostics
    # ------------------------------
    
    def format_status(self) -> str:
        """Real-time status dashboard"""
        base_balance = self.connector.get_balance(self.base_asset)
        quote_balance = self.connector.get_balance(self.quote_asset)
        mid_price = self.get_price()
        total_value = (base_balance * mid_price) + quote_balance
        
        status = [
            "Advanced PMM Dashboard",
            "-----------------------",
            f"Volatility: {self.current_volatility:.4f} ({'Normal' if self.current_volatility < self.emergency_stop_vol else 'High'})",
            f"Trend Score: {self.trend_score:.2f} ({'Bullish' if self.trend_score > 0 else 'Bearish'})",
            f"Inventory Risk: {self.calculate_inventory_risk():.2%}",
            f"Position Size: {self.position_size:.4f} {self.base_asset}",
            f"Total Value: {total_value:.2f} {self.quote_asset}",
            ""
        ]

        if self.active_orders:
            status.append("Active Orders:")
            for order in self.active_orders:
                status.append(
                    f"{order.trade_type.name} {order.amount:.4f} @ {order.price:.4f}"
                )
        else:
            status.append("No active orders")

        return "\n".join(status)

    # ------------------------------
    # Order Placement Utilities
    # ------------------------------
    
    async def place_order(self, 
                        side: TradeType, 
                        price: Decimal, 
                        amount: Decimal):
        """Safe order placement with checks"""
        if price <= 0 or amount <= 0:
            return

        order_id = f"{side.name}-{datetime.now().timestamp()}"
        return await self.place_order(
            order_id=order_id,
            trading_pair=self.trading_pair,
            amount=amount,
            order_type=OrderType.LIMIT,
            price=price,
            trade_type=side
        )