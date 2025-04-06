
import logging
from decimal import Decimal
from typing import List, Dict

import pandas_ta  # Pandas TA library for technical indicators (RSI, ATR)
from hummingbot.strategy.script_strategy_base import ScriptStrategyBase
from hummingbot.connector.connector_base import ConnectorBase
from hummingbot.core.data_type.common import OrderType, TradeType, PriceType
from hummingbot.core.data_type.order_candidate import OrderCandidate
from hummingbot.core.event.events import OrderFilledEvent
from hummingbot.data_feed.candles_feed.candles_factory import CandlesFactory, CandlesConfig

class CombinedPMMStrategy(ScriptStrategyBase):
   
    # Strategy Configuration 
    exchange: str = "binance"                
    trading_pair: str = "ETH-USDT"           
    order_amount: Decimal = Decimal("0.01")   
    order_refresh_time: float = 15.0      
    price_source: PriceType = PriceType.MidPrice  
    
    # Candles/Indicators settings
    candles_exchange: str = "binance"       
    candles_interval: str = "1m"          
    candles_length: int = 30         
    max_records: int = 1000                 
    
    # Volatility Spread parameters
    bid_spread_scalar: Decimal = Decimal("120")  
    ask_spread_scalar: Decimal = Decimal("60")  
    # Note: We will compute actual spreads as NATR * scalar 
    # Different values for bid vs ask allow asymmetric spreads if desired (here bid is wider than ask by default).
    
    # Price shift limits
    max_shift_spread: Decimal = Decimal("0.0001")  
    
    # Trend (RSI) parameters
    trend_scalar: Decimal = Decimal("-1")  # Scalar for trend impact: -1 for contrarian (sell on high RSI, buy on low RSI), +1 for momentum following.
    
    # Inventory management parameters
    target_base_pct: Decimal = Decimal("0.5")  # Target fraction of portfolio in base asset (50% = balanced inventory)
    # The inventory adjustment will be scaled such that if inventory is off by 100% of target, it can shift price by max_shift_spread.
    inventory_scalar: Decimal = Decimal("1") 
    
    # Internal state (will be updated in runtime)
    candles = None                # Candle feed object
    bid_spread: Decimal = Decimal("0")       
    ask_spread: Decimal = Decimal("0")        
    price_multiplier: Decimal = Decimal("0") 
    inventory_multiplier: Decimal = Decimal("0") 
    reference_price: Decimal = Decimal("0")  
    orig_price: Decimal = Decimal("0")        
    current_ratio: float = 0.5             
    inventory_delta: float = 0.0             
    
    def __init__(self, connectors: Dict[str, ConnectorBase]):
        super().__init__(connectors)
        # Initialize and start candle data feed for the specified market and interval
        candle_config = CandlesConfig(connector=self.candles_exchange or self.exchange,
                                      trading_pair=self.trading_pair,
                                      interval=self.candles_interval,
                                      max_records=self.max_records)
        self.candles = CandlesFactory.get_candle(candle_config)
        self.candles.start()
        # Ensure we set target_base_pct as a fraction (e.g., 50% -> 0.5)
        if self.target_base_pct > 1:
            self.target_base_pct = self.target_base_pct / Decimal("100")
        self.logger().info(f"Initialized candle feed: {self.candles.name}, interval {self.candles.interval}")
    
    def on_stop(self):
        """Cleanup on strategy stop."""
        if self.candles is not None:
            self.candles.stop()
    
    def on_tick(self):
        """Called at each clock tick (each second by default) to update orders."""
        # Only act when ready and at refresh interval
        if not self.ready_to_trade:
            return  # wait until connectors are ready
        current_time = self.current_timestamp
        if self.tick_elapsed(current_time):  # ( helper to check refresh time)
            # Cancel existing orders and recalibrate before placing new ones
            self.cancel_all_orders()
            self.update_indicators_and_parameters()
            order_candidates = self.create_order_candidates()
            adjusted_orders = self.connectors[self.exchange].budget_checker.adjust_candidates(order_candidates, all_or_none=True)
            self.place_orders(adjusted_orders)
    
    def tick_elapsed(self, current_time: float) -> bool:
        """Helper to check if order_refresh_time has passed since last order creation."""
        # We store next_refresh time in create_timestamp 
        # Initialize create_timestamp if this is first tick
        if self.create_timestamp == 0:
            self.create_timestamp = current_time
        # If current time reached the scheduled refresh time, update next refresh and return True
        if current_time >= self.create_timestamp:
            # schedule next refresh
            self.create_timestamp = current_time + self.order_refresh_time
            return True
        return False
    
    def update_indicators_and_parameters(self):
        """Compute latest indicators (RSI, NATR) and update spreads and price multipliers."""
        # Fetch latest candle data as pandas DataFrame
        candles_df = self.candles.candles_df
        if candles_df is None or candles_df.empty:
            
            return
       
        df = candles_df.tail(self.candles_length).copy()
        # Calculate NATR (Normalized ATR) and RSI using pandas_ta
        df.ta.natr(length=self.candles_length, scalar=100, append=True)  # scalar=100 to get NATR in percentage terms
        df.ta.rsi(length=self.candles_length, append=True)
        # The pandas-ta indicators will create columns like "NATR_{period}" and "RSI_{period}"
        natr_col = f"NATR_{self.candles_length}"
        rsi_col = f"RSI_{self.candles_length}"
        if natr_col not in df.columns or rsi_col not in df.columns:
            return
        latest_natr = Decimal(str(df[natr_col].iloc[-1] or 0))   # NATR value (in percent)
        latest_rsi = float(df[rsi_col].iloc[-1] or 0)            # RSI value (0-100 scale)
        # Update spreads based on NATR. NATR (scalar=100) is in percentage points.
        # Divide by 100 to convert percent to fraction of price.
        self.bid_spread = (latest_natr / Decimal("100")) * self.bid_spread_scalar / Decimal("10000")
        self.ask_spread = (latest_natr / Decimal("100")) * self.ask_spread_scalar / Decimal("10000")
        #  if latest_natr = 1.5 (percent), bid_spread_scalar=120 -> bid_spread = 1.5% * 120 / 10000 = 0.0018 (0.18%)
        #  ask_spread would be 0.9% if ask_spread_scalar=60
        # Actually 1.5% * 60 / 10000 = 0.0009 (0.09%). 
        
        # Trend-based price shift via RSI:
        # Normalize RSI to range -0.5 to +0.5: (RSI-50)/100
        trend_offset = (latest_rsi - 50.0) / 100.0  # e.g., RSI=70 -> 0.20, RSI=30 -> -0.20
        # Limit the trend offset to +/-0.5 
        if trend_offset > 0.5: 
            trend_offset = 0.5
        if trend_offset < -0.5:
            trend_offset = -0.5
        # Apply trend scalar and max shift limit
        self.price_multiplier = Decimal(str(trend_offset)) * self.trend_scalar
        # Ensure price_multiplier does not exceed +/- max_shift_spread
        if self.price_multiplier > self.max_shift_spread:
            self.price_multiplier = self.max_shift_spread
        if self.price_multiplier < -self.max_shift_spread:
            self.price_multiplier = -self.max_shift_spread
        
        # Inventory-based price shift:
        base_asset, quote_asset = self.trading_pair.split("-")
        base_balance = self.connectors[self.exchange].get_balance(base_asset)
        quote_balance = self.connectors[self.exchange].get_balance(quote_asset)
        # Compute current inventory ratio (base value / total value)
        mid_price = self.connectors[self.exchange].get_price_by_type(self.trading_pair, self.price_source)
        base_value = base_balance * Decimal(str(mid_price))
        total_value = base_value + quote_balance
        if total_value > 0:
            self.current_ratio = float(base_value / total_value)
        else:
            self.current_ratio = 0.5
        # Compute inventory delta as fractional deviation from target (bounded -1 to 1)
        target = float(self.target_base_pct)  # e.g., 0.5
        delta = 0.0
        if target > 0:
            delta = (target - self.current_ratio) / target  # fraction relative to target
        # Bound delta to [-1, 1]
        if delta > 1.0: 
            delta = 1.0
        if delta < -1.0:
            delta = -1.0
        self.inventory_delta = delta
        
        self.inventory_multiplier = Decimal(str(self.inventory_delta)) * self.inventory_scalar
       
        if self.inventory_multiplier > Decimal("0"):
            self.inventory_multiplier = self.inventory_multiplier * self.max_shift_spread
        else:
            self.inventory_multiplier = self.inventory_multiplier * self.max_shift_spread
       
        
        # Determine final reference price after applying shifts
        self.orig_price = Decimal(str(mid_price))
        # Apply both multipliers: we multiply the price by (1 + trend_shift) * (1 + inventory_shift)
        self.reference_price = self.orig_price * (Decimal("1") + self.price_multiplier) * (Decimal("1") + self.inventory_multiplier)
    
    def create_order_candidates(self) -> List[OrderCandidate]:
        """Create bid and ask OrderCandidate objects based on current spreads and reference price."""
        # Ensure we do not place orders inside the top of the order book:
        best_bid = self.connectors[self.exchange].get_price(self.trading_pair, is_buy=False)  # best_bid price
        best_ask = self.connectors[self.exchange].get_price(self.trading_pair, is_buy=True)   # best_ask price
        # Compute desired quote prices around reference price
        buy_price = self.reference_price * (Decimal("1") - self.bid_spread)
        sell_price = self.reference_price * (Decimal("1") + self.ask_spread)
        # Do not exceed best bid/ask (to avoid crossing the spread)
        if best_bid is not None:
            buy_price = min(buy_price, Decimal(str(best_bid)))
        if best_ask is not None:
            sell_price = max(sell_price, Decimal(str(best_ask)))
        # Create OrderCandidate objects for a buy and a sell
        buy_order = OrderCandidate(trading_pair=self.trading_pair,
                                   order_type=OrderType.LIMIT,
                                   order_side=TradeType.BUY,
                                   amount=Decimal(str(self.order_amount)),
                                   price=buy_price,
                                   is_maker=True)
        sell_order = OrderCandidate(trading_pair=self.trading_pair,
                                    order_type=OrderType.LIMIT,
                                    order_side=TradeType.SELL,
                                    amount=Decimal(str(self.order_amount)),
                                    price=sell_price,
                                    is_maker=True)
        return [buy_order, sell_order]
    
    def place_orders(self, orders: List[OrderCandidate]):
        for order in orders:
            if order.order_side == TradeType.BUY:
                self.buy(self.exchange, order.trading_pair, order.amount, order.order_type, order.price)
            elif order.order_side == TradeType.SELL:
                self.sell(self.exchange, order.trading_pair, order.amount, order.order_type, order.price)
    
    def cancel_all_orders(self):
        for order in self.get_active_orders(connector_name=self.exchange):
            self.cancel(self.exchange, order.trading_pair, order.client_order_id)
    
    def did_fill_order(self, event: OrderFilledEvent):
        msg = (f"{event.trade_type.name} {round(event.amount, 4)} {self.trading_pair} on {self.exchange} at {round(event.price, 4)}")
        self.log_with_clock(logging.INFO, msg)
        self.notify_hb_app_with_timestamp(msg)
    
    def format_status(self) -> str:
        if not self.ready_to_trade:
            return "Market connectors are not ready."
        lines = []
        # Show balances
        balance_df = self.get_balance_df()
        lines.extend(["", "  Balances:"])
        lines.extend(["    " + line for line in balance_df.to_string(index=False).split("\n")])
        # Show active orders
        try:
            df = self.active_orders_df()
            lines.extend(["", "  Orders:"])
            lines.extend(["    " + line for line in df.to_string(index=False).split("\n")])
        except ValueError:
            lines.extend(["", "  Orders:", "    No active maker orders."])
        # Show spreads and mid-price info
        ref_price = self.reference_price
        best_bid = self.connectors[self.exchange].get_price(self.trading_pair, is_buy=False)
        best_ask = self.connectors[self.exchange].get_price(self.trading_pair, is_buy=True)
        best_bid_spread = (ref_price - Decimal(str(best_bid))) / ref_price if best_bid else Decimal("0")
        best_ask_spread = (Decimal(str(best_ask)) - ref_price) / ref_price if best_ask else Decimal("0")
        trend_price_shift = self.price_multiplier * ref_price
        inventory_price_shift = self.inventory_multiplier * ref_price
        # Add spread details
        lines.append("\n  -- Spread & Price Details --")
        lines.append(f"  Base Spread (no adj): { (self.bid_spread + self.ask_spread) * Decimal('10000'):.2f} bps")
        lines.append(f"  Current Bid Spread: {self.bid_spread * Decimal('10000'):.2f} bps | Best Bid Spread: {best_bid_spread * Decimal('10000'):.2f} bps")
        lines.append(f"  Current Ask Spread: {self.ask_spread * Decimal('10000'):.2f} bps | Best Ask Spread: {best_ask_spread * Decimal('10000'):.2f} bps")
        # Add price shift details
        lines.append("\n  -- Trend & Inventory Shift --")
        lines.append(f"  Max Shift (bps): {self.max_shift_spread * Decimal('10000'):.2f}")
        lines.append(f"  Trend Scalar: {self.trend_scalar:+.1f} | Trend Multiplier: {self.price_multiplier * Decimal('10000'):.2f} bps | Trend Price Shift: {trend_price_shift:.4f}")
        lines.append(f"  Target Base %: {float(self.target_base_pct)*100:.1f}% | Current Base %: {self.current_ratio*100:.1f}% | Inventory Delta: {self.inventory_delta:.3f}")
        lines.append(f"  Inventory Multiplier: {self.inventory_multiplier * Decimal('10000'):.2f} bps | Inventory Price Shift: {inventory_price_shift:.4f}")
        lines.append(f"  Mid Price: {self.orig_price:.4f} | Adjusted Mid (Ref Price): {self.reference_price:.4f}")
        # Add recent candles and indicators
        lines.append("\n  -- Recent Candles & Indicators --")
        lines.append(f"  Candles ({self.candles.interval} @ {self.candles.exchange.name}):")
        # Include last few candle data points with RSI and NATR for reference
        candles_df = self.candles.candles_df
        if candles_df is not None and not candles_df.empty:
            # Compute indicators for display (to ensure columns exist)
            df_display = candles_df.tail(3).copy()  # show last 3 candles
            df_display.ta.rsi(length=self.candles_length, append=True)
            df_display.ta.natr(length=self.candles_length, scalar=100, append=True)
            # Select columns to show: time, open, high, low, close, maybe RSI and NATR
            # Ensure time is human-readable:
            try:
                df_display['time'] = df_display.index.strftime("%Y-%m-%d %H:%M:%S")
            except Exception:
                df_display.reset_index(inplace=True)
                if 'timestamp' in df_display.columns:
                    # If index was timestamp
                    df_display['time'] = pd.to_datetime(df_display['timestamp'], unit='ms').dt.strftime("%Y-%m-%d %H:%M:%S")
            cols = ["time", "open", "high", "low", "close"]
            if f"RSI_{self.candles_length}" in df_display.columns:
                cols.append(f"RSI_{self.candles_length}")
            if f"NATR_{self.candles_length}" in df_display.columns:
                cols.append(f"NATR_{self.candles_length}")
            display_lines = df_display[cols].to_string(index=False).split("\n")
            lines.extend(["    " + line for line in display_lines])
        else:
            lines.append("    (No candle data yet)")
        return "\n".join(lines)
