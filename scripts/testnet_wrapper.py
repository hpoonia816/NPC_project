from hummingbot.client.config.config_helpers import create_yml_files

def setup_testnet():
    create_yml_files()  # Generates configs if missing
    with open("conf/conf_global_BINANCE.yml", "w") as f:
        f.write("""
        template_version: 3
        exchange: binance
        testnet: true
        """)
    print("Testnet configured. Get keys from testnet.binance.vision")

if __name__ == "__main__":
    setup_testnet()