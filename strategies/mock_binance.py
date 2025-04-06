from unittest.mock import MagicMock

class MockBinance:
    def __init__(self):
        self.mock = MagicMock()
        self.mock.get_balance.return_value = {
            "USDT": 1000.0,
            "BTC": 0.5
        }
        
    def __getattr__(self, name):
        return getattr(self.mock, name)

# Usage in your strategy:
# binance = MockBinance() instead of real connector