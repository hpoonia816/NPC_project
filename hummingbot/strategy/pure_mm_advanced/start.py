from hummingbot.strategy.pure_mm_advanced import PureMMAdvancedStrategy
from hummingbot.client.config.config_helpers import ClientConfigAdapter
from hummingbot.client.config.config_data_types import BaseClientConfigMap

def start(self, config: BaseClientConfigMap):
    client_config_map = ClientConfigAdapter(config)

    strategy = PureMMAdvancedStrategy()
    return strategy
