import os

# Base paths
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(os.path.dirname(BASE_DIR), "Global-Position") # Pointing to the original data folder

# Input Files
SAP_FILE = os.path.join(DATA_DIR, "sap_stock.csv")
BINANCE_FILE = os.path.join(DATA_DIR, "binance.csv")
OPERATIONS_FILE = os.path.join(DATA_DIR, "operaciones.csv")
NEW_TRANSACTIONS_FILE = os.path.join(DATA_DIR, "Transactions_new.csv")

# Crypto Processing (input -> processing workflow)
BINANCE_INPUT = os.path.join(BASE_DIR, "input", "Binance.csv")
CRYPTO_DB = os.path.join(BASE_DIR, "processing", "crypto.csv")

# Browser Configuration
CHROME_DRIVER_PATH = r"C:\Users\Usuario\Downloads\chrome-win64\chrome-win64\chrome.exe"
