"""Database connection"""
from pymongo import MongoClient, ASCENDING, DESCENDING
from .config import settings

client = MongoClient(settings.MONGO_URL)
db = client[settings.MONGO_DB_NAME]

# Collections
users_collection = db["users"]
plans_collection = db["plans"]
teams_collection = db["teams"]
transactions_collection = db["transactions"]
wallets_collection = db["wallets"]
withdrawals_collection = db["withdrawals"]
topups_collection = db["topups"]
settings_collection = db["settings"]
email_configs_collection = db["email_configs"]
