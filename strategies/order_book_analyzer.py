from hummingbot.core.data_type.order_book import OrderBook

class OrderBookAnalyzer:
    def __init__(self, trading_pair: str, depth_levels: int = 5):
        self.trading_pair = trading_pair
        self.depth_levels = depth_levels
        
    def get_liquidity_imbalance(self, order_book: OrderBook) -> float:
        bids = order_book.bid_entries()[:self.depth_levels]
        asks = order_book.ask_entries()[:self.depth_levels]
        
        total_bid = sum(float(bid.amount) for bid in bids)
        total_ask = sum(float(ask.amount) for ask in asks)
        
        return (total_bid - total_ask) / (total_bid + total_ask) if (total_bid + total_ask) > 0 else 0