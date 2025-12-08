"""
Wallet Service - Handle all wallet operations
"""
from datetime import datetime
from bson import ObjectId
from app.core.database import wallets_collection, transactions_collection, users_collection

def create_wallet(user_id: str):
    """Create wallet for new user"""
    try:
        wallet = {
            "userId": user_id,
            "balance": 0,
            "totalEarnings": 0,
            "totalWithdrawals": 0,
            "createdAt": datetime.utcnow(),
            "updatedAt": datetime.utcnow()
        }
        wallets_collection.insert_one(wallet)
        return True
    except Exception as e:
        print(f"Error creating wallet: {str(e)}")
        return False

def get_wallet_balance(user_id: str):
    """Get user's wallet balance"""
    wallet = wallets_collection.find_one({"userId": user_id})
    if wallet:
        return {
            "balance": wallet.get("balance", 0),
            "totalEarnings": wallet.get("totalEarnings", 0),
            "totalWithdrawals": wallet.get("totalWithdrawals", 0)
        }
    return {"balance": 0, "totalEarnings": 0, "totalWithdrawals": 0}

def credit_wallet(user_id: str, amount: float, transaction_type: str, description: str):
    """Credit amount to wallet"""
    try:
        # Update wallet
        wallets_collection.update_one(
            {"userId": user_id},
            {
                "$inc": {
                    "balance": amount,
                    "totalEarnings": amount
                },
                "$set": {"updatedAt": datetime.utcnow()}
            }
        )
        
        # Create transaction
        transactions_collection.insert_one({
            "userId": user_id,
            "type": transaction_type,
            "amount": amount,
            "description": description,
            "status": "COMPLETED",
            "createdAt": datetime.utcnow()
        })
        
        return True
    except Exception as e:
        print(f"Error crediting wallet: {str(e)}")
        return False

def debit_wallet(user_id: str, amount: float, transaction_type: str, description: str):
    """Debit amount from wallet"""
    try:
        wallet = wallets_collection.find_one({"userId": user_id})
        if not wallet or wallet.get("balance", 0) < amount:
            return False
        
        # Update wallet
        wallets_collection.update_one(
            {"userId": user_id},
            {
                "$inc": {
                    "balance": -amount,
                    "totalWithdrawals": amount
                },
                "$set": {"updatedAt": datetime.utcnow()}
            }
        )
        
        # Create transaction
        transactions_collection.insert_one({
            "userId": user_id,
            "type": transaction_type,
            "amount": -amount,
            "description": description,
            "status": "COMPLETED",
            "createdAt": datetime.utcnow()
        })
        
        return True
    except Exception as e:
        print(f"Error debiting wallet: {str(e)}")
        return False

def get_transactions(user_id: str, limit: int = 50):
    """Get user's transaction history"""
    transactions = list(transactions_collection.find(
        {"userId": user_id}
    ).sort("createdAt", -1).limit(limit))
    return transactions
