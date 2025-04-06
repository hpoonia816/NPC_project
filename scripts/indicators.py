import pandas as pd
import numpy as np

class VolatilityCalculator:
    @staticmethod
    def bollinger_bands(prices: pd.Series, window=20, multiplier=2):
        rolling_mean = prices.rolling(window).mean()
        rolling_std = prices.rolling(window).std()
        return {
            'upper': rolling_mean + (rolling_std * multiplier),
            'lower': rolling_mean - (rolling_std * multiplier),
            'width': (rolling_std / rolling_mean) * 100  # % volatility
        }

class TrendAnalyzer:
    @staticmethod
    def ema_crossover(prices: pd.Series, fast=9, slow=21):
        ema_fast = prices.ewm(span=fast).mean()
        ema_slow = prices.ewm(span=slow).mean()
        return {
            'trend': 'up' if ema_fast.iloc[-1] > ema_slow.iloc[-1] else 'down',
            'strength': abs(ema_fast.iloc[-1] - ema_slow.iloc[-1]) / prices.iloc[-1]
        }

    @staticmethod
    def rsi(prices: pd.Series, window=14):
        delta = prices.diff()
        gain = delta.where(delta > 0, 0)
        loss = -delta.where(delta < 0, 0)
        avg_gain = gain.rolling(window).mean()
        avg_loss = loss.rolling(window).mean()
        rs = avg_gain / avg_loss
        return 100 - (100 / (1 + rs))