from hummingbot.strategy.combined_pmm import combined_pmm_config_map

STRATEGIES = {
    "combined_pmm_strategy": load_strategy_config_file
}

def load_strategy_config_file(strategy_name: str):
    if strategy_name == "combined_pmm_strategy":
        return combined_pmm_config_map.strategy_config_map()
