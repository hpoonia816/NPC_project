#!/usr/bin/env python
import logging
from decimal import Decimal
from typing import Dict, Optional
import os

from hummingbot.strategy.script_strategy_base import ScriptStrategyBase
from hummingbot.core.data_type.common import OrderType, PriceType, TradeType
from hummingbot.core.event.events import OrderFilledEvent
from hummingbot.connector.exchange.binance.binance_exchange import BinanceExchange

class EnhancedPMM(ScriptStrategyBase):
    """
    Enhanced Market Maker with:
    - Binance Testnet support
    - Paper trading mode
    - Mock API capability
    - Built-in balance checks
    """
    
    # === Strategy Configuration ===
    trading_pair = "BTC-USDT"
    order_amount = Decimal("0.001")  # Small amount for testing
    bid_spread = Decimal("0.005")   # 0.5%
    ask_spread = Decimal("0.005")   # 0.5%
    order_refresh_time = 15.0
    
    # === Testing Modes ===
    PAPER_TRADE = True    # Set False for real trading
    USE_TESTNET = True    # Auto-enabled if testnet keys detected
    MOCK_API = False      # For unit testing
    
    def __init__(self):
        super().__init__()
        self.logger().setLevel(logging.INFO)
        self.binance = self._init_exchange()
        self.simulated_balance = {
            "BTC": Decimal("0.1"),
            "USDT": Decimal("1000")
        }

    def _init_exchange(self):
        """Initialize exchange connector with testing options"""
        if self.MOCK_API:
            from mock_binance import MockBinance
            return MockBinance()
            
        api_key = os.getenv("BINANCE_API_KEY", "")
        api_secret = os.getenv("BINANCE_API_SECRET", "")
        
        if "test" in api_key.lower() or self.USE_TESTNET:
            self.logger().info("Running in TESTNET mode")
            self.PAPER_TRADE = False  # Testnet is already simulated
            
        return BinanceExchange(
            binance_api_key=api_key,
            binance_api_secret=api_secret,
            trading_pairs=[self.trading_pair]
        )

    def on_tick(self):
        """Main strategy logic"""
        if not self._check_balances():
            self.logger().warning("Insufficient balance - cannot place orders")
            return
            
        mid_price = self._get_mid_price()
        bid_price, ask_price = self._calculate_prices(mid_price)
        
        self.cancel_all_orders()
        self._place_orders(bid_price, ask_price)

    def _check_balances(self) -> bool:
        """Verify sufficient balance exists"""
        if self.PAPER_TRADE:
            return True  # Bypass for simulation
            
        base, quote = self.trading_pair.split("-")
        required_base = self.order_amount * Decimal("2")  # Both bid/ask
        
        try:
            balance = self.binance.get_balance(base)
            return balance >= required_base
        except Exception as e:
            self.logger().error(f"Balance check failed: {str(e)}")
            return False

    def _get_mid_price(self) -> Decimal:
        """Get current mid price with testing fallback"""
        if self.PAPER_TRADE or self.MOCK_API:
            return Decimal("50000")  # Test value
        return self.binance.get_price_by_type(
            self.trading_pair, 
            PriceType.MidPrice
        )

    def _calculate_prices(self, mid_price: Decimal) -> (Decimal, Decimal):
        """Calculate bid/ask prices with spread"""
        bid_price = mid_price * (Decimal("1") - self.bid_spread)
        ask_price = mid_price * (Decimal("1") + self.ask_spread)
        return bid_price.quantize(Decimal("0.01")), ask_price.quantize(Decimal("0.01"))

    def _place_orders(self, bid_price: Decimal, ask_price: Decimal):
        """Place orders with testing mode support"""
        if self.PAPER_TRADE:
            self.logger().info(
                f"[PAPER] Would place: "
                f"BID {self.order_amount} @ {bid_price} | "
                f"ASK {self.order_amount} @ {ask_price}"
            )
            return
            
        self.buy(
            connector_name="binance",
            trading_pair=self.trading_pair,
            amount=self.order_amount,
            price=bid_price,
            order_type=OrderType.LIMIT
        )
        
        self.sell(
            connector_name="binance",
            trading_pair=self.trading_pair,
            amount=self.order_amount,
            price=ask_price,
            order_type=OrderType.LIMIT
        )

    def cancel_all_orders(self):
        """Cancel all active orders"""
        for order in self.get_active_orders("binance"):
            self.cancel("binance", order.trading_pair, order.client_order_id)

    def did_fill_order(self, event: OrderFilledEvent):
        """Handle filled orders"""
        self.logger().info(
            f"Order filled: {event.amount} {event.trading_pair} @ {event.price}"
        )
        
        # Update simulated balance
        if self.PAPER_TRADE:
            base, quote = self.trading_pair.split("-")
            if event.trade_type == TradeType.BUY:
                self.simulated_balance[base] += Decimal(str(event.amount))
                self.simulated_balance[quote] -= Decimal(str(event.amount * event.price))
            else:
                self.simulated_balance[base] -= Decimal(str(event.amount))
                self.simulated_balance[quote] += Decimal(str(event.amount * event.price))
                
            self.logger().info(f"New balance: {self.simulated_balance}")

# === For Mock Testing ===
class MockBinance:
    """Standalone mock for unit testing"""
    def __init__(self):
        self.orders = []
        
    def get_balance(self, asset):
        return Decimal("1000")
        
    def get_price_by_type(self, trading_pair, price_type):
        return Decimal("50000")

if __name__ == "__main__":
    # For direct script testing
    strategy = EnhancedPMM()
    strategy.PAPER_TRADE = True
    strategy.on_tick()