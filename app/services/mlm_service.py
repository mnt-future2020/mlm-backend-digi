"""
MLM Service - Binary MLM Calculations
Handles matching income, PV distribution, and team management
"""
from datetime import datetime, timedelta
import pytz
from bson import ObjectId
from app.core.database import (
    users_collection, teams_collection, transactions_collection,
    wallets_collection, plans_collection
)

IST = pytz.timezone('Asia/Kolkata')

def distribute_pv_upward(user_id: str, pv_amount: int):
    """
    Distribute PV upward in the binary tree
    PV flows from child to all ancestors based on placement
    """
    try:
        current_user_id = user_id
        
        # Traverse up the tree
        for _ in range(100):  # Max 100 levels
            # Get current user's team record
            team_record = teams_collection.find_one({"userId": current_user_id})
            
            if not team_record or not team_record.get("sponsorId"):
                break
            
            sponsor_id = team_record["sponsorId"]
            placement = team_record.get("placement")
            
            # Determine which side to add PV (LEFT or RIGHT)
            if placement == "LEFT":
                update_field = "leftPV"
            elif placement == "RIGHT":
                update_field = "rightPV"
            else:
                break
            
            # Update sponsor's PV
            users_collection.update_one(
                {"_id": ObjectId(sponsor_id)},
                {
                    "$inc": {update_field: pv_amount},
                    "$set": {"updatedAt": datetime.now(IST)}
                }
            )
            
            # Note: Matching income calculated at end of day
            # Not calculated immediately to allow PV accumulation
            
            # Move up to next sponsor
            sponsor_team = teams_collection.find_one({"userId": sponsor_id})
            if not sponsor_team or not sponsor_team.get("sponsorId"):
                break
            
            current_user_id = sponsor_id
    
    except Exception as e:
        print(f"Error in PV distribution: {str(e)}")


def calculate_matching_income(user_id: str):
    """
    Calculate matching income for a single user
    Formula: min(leftPV, rightPV) × ₹25 per PV
    Daily capping applies
    """
    try:
        user = users_collection.find_one({"_id": ObjectId(user_id)})
        if not user:
            return
        
        left_pv = user.get("leftPV", 0)
        right_pv = user.get("rightPV", 0)
        
        # No matching if either side is 0
        if left_pv == 0 or right_pv == 0:
            return
        
        # Get plan details
        plan_id = user.get("currentPlanId")
        if not plan_id:
            plan_name = user.get("currentPlan")
            plan = plans_collection.find_one({"name": plan_name})
        else:
            plan = plans_collection.find_one({"_id": ObjectId(plan_id)})
        
        if not plan:
            return
        
        daily_capping = plan.get("dailyCapping", 500)
        matching_income_rate = 25  # ₹25 per PV
        
        # Calculate matching PV
        matched_pv = min(left_pv, right_pv)
        
        # Check daily capping
        today_date = datetime.now(IST).replace(hour=0, minute=0, second=0, microsecond=0)
        last_matching_date = user.get("lastMatchingDate")
        
        # Reset daily PV if new day
        if not last_matching_date or last_matching_date.replace(hour=0, minute=0, second=0, microsecond=0) != today_date:
            daily_pv_used = 0
        else:
            daily_pv_used = user.get("dailyPVUsed", 0)
        
        # Calculate maximum PV allowed today
        max_pv_per_day = daily_capping // matching_income_rate
        remaining_pv_today = max_pv_per_day - daily_pv_used
        
        if remaining_pv_today <= 0:
            return  # Daily limit reached
        
        # Today's PV = min(matched_pv, remaining_pv_today)
        today_pv = min(matched_pv, remaining_pv_today)
        
        if today_pv <= 0:
            return
        
        # Calculate income
        income = today_pv * matching_income_rate
        
        # Update wallet
        wallets_collection.update_one(
            {"userId": user_id},
            {
                "$inc": {
                    "balance": income,
                    "totalEarnings": income
                },
                "$set": {"updatedAt": datetime.now(IST)}
            }
        )
        
        # Create transaction
        transactions_collection.insert_one({
            "userId": user_id,
            "type": "MATCHING_INCOME",
            "amount": income,
            "description": f"Binary matching income - {today_pv} PV @ ₹{matching_income_rate}/PV",
            "pv": today_pv,
            "status": "COMPLETED",
            "createdAt": datetime.now(IST)
        })
        
        # Flush matched PV from both sides
        # Note: We deduct matched_pv (not today_pv) to properly flush the matched pairs
        # Even if daily capping limits income, the matched PV should be removed
        # Example: left=12, right=14, matched=12, daily_cap=10
        # Income = 10 * 25 = 250, but we flush 12 from each side
        # Result: left=0, right=2
        users_collection.update_one(
            {"_id": ObjectId(user_id)},
            {
                "$inc": {
                    "leftPV": -matched_pv,
                    "rightPV": -matched_pv,
                    "totalPV": today_pv
                },
                "$set": {
                    "lastMatchingDate": today_date,
                    "dailyPVUsed": daily_pv_used + today_pv,
                    "updatedAt": datetime.now(IST)
                }
            }
        )
        
    except Exception as e:
        print(f"Error in matching income calculation: {str(e)}")


def calculate_daily_matching_for_all_users():
    """
    Calculate matching income for all users (called at end of day)
    Returns summary of calculations
    """
    try:
        users = list(users_collection.find({
            "role": "user",
            "isActive": True,
            "currentPlan": {"$ne": None}
        }))
        
        total_processed = 0
        total_income_paid = 0
        
        for user in users:
            user_id = str(user["_id"])
            calculate_matching_income(user_id)
            total_processed += 1
        
        return {
            "success": True,
            "processed": total_processed,
            "total_income": total_income_paid
        }
    
    except Exception as e:
        return {"success": False, "error": str(e)}


def add_user_to_binary_tree(user_id: str, sponsor_id: str, placement: str):
    """
    Add new user to binary tree
    Returns success status
    """
    try:
        teams_collection.insert_one({
            "userId": user_id,
            "sponsorId": sponsor_id,
            "placement": placement.upper(),
            "createdAt": datetime.now(IST)
        })
        return True
    except Exception as e:
        print(f"Error adding to tree: {str(e)}")
        return False
