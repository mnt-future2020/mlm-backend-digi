from fastapi import FastAPI, HTTPException, Depends, status, Body, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, EmailStr, Field, field_validator
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
from jose import JWTError, jwt
from passlib.context import CryptContext
from pymongo import MongoClient, ASCENDING, DESCENDING
from bson import ObjectId
import os
from dotenv import load_dotenv
import random
import string
import re

# Load environment variables
load_dotenv()

# Initialize FastAPI app
app = FastAPI(title="VSV Unite MLM API", version="1.0.0")

# CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:3001"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# MongoDB Configuration
MONGO_URL = os.getenv("MONGO_URL", "mongodb://localhost:27017/")
MONGO_DB_NAME = os.getenv("MONGO_DB_NAME", "mlm_vsv_unite")
client = MongoClient(MONGO_URL)
db = client[MONGO_DB_NAME]

# Collections
users_collection = db["users"]
plans_collection = db["plans"]
wallets_collection = db["wallets"]
transactions_collection = db["transactions"]
teams_collection = db["teams"]
withdrawals_collection = db["withdrawals"]
settings_collection = db["settings"]
email_configs_collection = db["email_configs"]
topups_collection = db["topups"]

# JWT Configuration
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
JWT_ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", 10080))

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Helper functions
def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=JWT_ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)
    return encoded_jwt

def generate_referral_id(prefix="VSV"):
    """Generate unique referral ID"""
    while True:
        random_str = ''.join(random.choices(string.ascii_uppercase + string.digits, k=7))
        referral_id = f"{prefix}{random_str}"
        if not users_collection.find_one({"referralId": referral_id}):
            return referral_id

def serialize_doc(doc):
    """Convert MongoDB document to JSON serializable format"""
    if doc is None:
        return None
    if isinstance(doc, list):
        return [serialize_doc(item) for item in doc]
    if isinstance(doc, dict):
        result = {}
        for key, value in doc.items():
            if key == "_id":
                result["id"] = str(value)
            elif isinstance(value, ObjectId):
                result[key] = str(value)
            elif isinstance(value, datetime):
                result[key] = value.isoformat()
            elif isinstance(value, dict):
                result[key] = serialize_doc(value)
            elif isinstance(value, list):
                result[key] = [serialize_doc(item) for item in value]
            else:
                result[key] = value
        return result
    return doc

# Get current user from token
async def get_current_user(authorization: Optional[str] = None):
    """Extract user from JWT token in Authorization header"""
    from fastapi import Header
    
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    token = authorization.replace("Bearer ", "")
    
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        user_id: str = payload.get("userId")
        if user_id is None:
            raise HTTPException(status_code=401, detail="Invalid token")
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")
    
    user = users_collection.find_one({"_id": ObjectId(user_id)})
    if user is None:
        raise HTTPException(status_code=401, detail="User not found")
    
    return serialize_doc(user)

async def get_current_active_user(authorization: Optional[str] = Header(None)):
    """Get current active user"""
    user = await get_current_user(authorization)
    if not user.get("isActive"):
        raise HTTPException(status_code=400, detail="Inactive user")
    return user

async def get_current_admin(authorization: Optional[str] = Header(None)):
    """Get current admin user"""
    user = await get_current_user(authorization)
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Not authorized")
    return user

# Pydantic Models
class UserRegister(BaseModel):
    name: str
    username: str
    email: Optional[EmailStr] = None
    password: str
    mobile: str
    referralId: Optional[str] = None
    placement: Optional[str] = None  # LEFT or RIGHT
    
    @field_validator('placement')
    def validate_placement(cls, v):
        if v and v not in ['LEFT', 'RIGHT']:
            raise ValueError('Placement must be LEFT or RIGHT')
        return v

class UserLogin(BaseModel):
    email: Optional[str] = None
    username: Optional[str] = None
    password: str

class ReferralLookup(BaseModel):
    referralId: str

class PasswordChange(BaseModel):
    oldPassword: str
    newPassword: str

class PlanActivation(BaseModel):
    planId: str
    paymentProof: Optional[str] = None

class WithdrawalRequest(BaseModel):
    amount: float
    bankDetails: Dict[str, Any]

class SettingsUpdate(BaseModel):
    companyName: Optional[str] = None
    companyEmail: Optional[str] = None
    companyPhone: Optional[str] = None
    companyAddress: Optional[str] = None
    companyDescription: Optional[str] = None
    metaTitle: Optional[str] = None
    metaDescription: Optional[str] = None
    metaKeywords: Optional[str] = None
    ogImage: Optional[str] = None
    heroBadge: Optional[str] = None
    heroSlides: Optional[List[Dict[str, Any]]] = None

# Initialize default plans
def initialize_plans():
    """Initialize membership plans if they don't exist"""
    existing_plans = plans_collection.count_documents({})
    if existing_plans == 0:
        plans = [
            {
                "name": "Basic",
                "amount": 111,
                "pv": 1,
                "referralIncome": 25,
                "dailyCapping": 250,
                "matchingIncome": 25,
                "description": "Start small, earn steady",
                "features": [
                    "Income Start: ₹25",
                    "Daily Capping: ₹250",
                    "Binary: Left 10 - Right 10 = ₹250",
                    "Basic Support"
                ],
                "isActive": True,
                "createdAt": datetime.utcnow()
            },
            {
                "name": "Standard",
                "amount": 599,
                "pv": 2,
                "referralIncome": 50,
                "dailyCapping": 500,
                "matchingIncome": 50,
                "description": "Popular choice for growth",
                "features": [
                    "Income Start: ₹50",
                    "Daily Capping: ₹500",
                    "Binary: Left 10 - Right 10 = ₹500",
                    "Standard Support"
                ],
                "isActive": True,
                "popular": True,
                "createdAt": datetime.utcnow()
            },
            {
                "name": "Advanced",
                "amount": 1199,
                "pv": 4,
                "referralIncome": 100,
                "dailyCapping": 1000,
                "matchingIncome": 100,
                "description": "Accelerate your earnings",
                "features": [
                    "Income Start: ₹100",
                    "Daily Capping: ₹1000",
                    "Binary: Left 10 - Right 10 = ₹1000",
                    "Priority Support"
                ],
                "isActive": True,
                "createdAt": datetime.utcnow()
            },
            {
                "name": "Premium",
                "amount": 1799,
                "pv": 6,
                "referralIncome": 150,
                "dailyCapping": 1500,
                "matchingIncome": 150,
                "description": "Maximum earning potential",
                "features": [
                    "Income Start: ₹150",
                    "Daily Capping: ₹1500",
                    "Binary: Left 10 - Right 10 = ₹1500",
                    "VIP Support"
                ],
                "isActive": True,
                "createdAt": datetime.utcnow()
            }
        ]
        plans_collection.insert_many(plans)
        print("✅ Default plans initialized")

# Initialize admin user
def initialize_admin():
    """Create admin user if not exists"""
    admin_email = os.getenv("ADMIN_EMAIL", "admin@vsvunite.com")
    admin_user = users_collection.find_one({"email": admin_email})
    
    if not admin_user:
        admin_password = os.getenv("ADMIN_PASSWORD", "Admin@123")
        admin_referral_id = os.getenv("ADMIN_REFERRAL_ID", "VSV00001")
        
        admin_data = {
            "name": os.getenv("ADMIN_NAME", "VSV Admin"),
            "username": os.getenv("ADMIN_USERNAME", "vsvadmin"),
            "email": admin_email,
            "password": hash_password(admin_password),
            "mobile": "9999999999",
            "referralId": admin_referral_id,
            "role": "admin",
            "isActive": True,
            "isEmailVerified": True,
            "placement": None,
            "sponsorId": None,
            "currentPlan": None,
            "totalPV": 0,
            "leftPV": 0,
            "rightPV": 0,
            "createdAt": datetime.utcnow(),
            "updatedAt": datetime.utcnow()
        }
        
        result = users_collection.insert_one(admin_data)
        
        # Create admin wallet
        wallets_collection.insert_one({
            "userId": str(result.inserted_id),
            "balance": 0,
            "totalEarnings": 0,
            "totalWithdrawals": 0,
            "createdAt": datetime.utcnow(),
            "updatedAt": datetime.utcnow()
        })
        
        print(f"✅ Admin user created - Email: {admin_email}, Password: {admin_password}")

# Startup event
@app.on_event("startup")
async def startup_event():
    """Initialize database on startup"""
    # Create indexes
    users_collection.create_index([("email", ASCENDING)], unique=True, sparse=True)
    users_collection.create_index([("username", ASCENDING)], unique=True)
    users_collection.create_index([("referralId", ASCENDING)], unique=True)
    users_collection.create_index([("mobile", ASCENDING)])
    
    wallets_collection.create_index([("userId", ASCENDING)], unique=True)
    transactions_collection.create_index([("userId", ASCENDING)])
    teams_collection.create_index([("userId", ASCENDING)])
    teams_collection.create_index([("sponsorId", ASCENDING)])
    
    # Initialize data
    initialize_plans()
    initialize_admin()
    
    print("✅ Database initialized successfully")

# ==================== AUTH ROUTES ====================

@app.post("/api/auth/register")
async def register(user: UserRegister):
    """Register new user with MLM structure"""
    try:
        # Check if user already exists
        if user.email and users_collection.find_one({"email": user.email}):
            raise HTTPException(status_code=400, detail="Email already registered")
        
        if users_collection.find_one({"username": user.username}):
            raise HTTPException(status_code=400, detail="Username already taken")
        
        # Validate referral ID if provided
        sponsor = None
        if user.referralId:
            sponsor = users_collection.find_one({"referralId": user.referralId})
            if not sponsor:
                raise HTTPException(status_code=400, detail="Invalid referral ID")
            
            if not user.placement:
                raise HTTPException(status_code=400, detail="Placement is required when using referral ID")
        
        # Generate unique referral ID
        referral_id = generate_referral_id()
        
        # Create user
        user_data = {
            "name": user.name,
            "username": user.username,
            "email": user.email,
            "password": hash_password(user.password),
            "mobile": user.mobile,
            "referralId": referral_id,
            "role": "user",
            "isActive": True,
            "isEmailVerified": False,
            "placement": user.placement,
            "sponsorId": user.referralId,
            "currentPlan": None,
            "totalPV": 0,
            "leftPV": 0,
            "rightPV": 0,
            "createdAt": datetime.utcnow(),
            "updatedAt": datetime.utcnow()
        }
        
        result = users_collection.insert_one(user_data)
        user_id = str(result.inserted_id)
        
        # Create wallet
        wallets_collection.insert_one({
            "userId": user_id,
            "balance": 0,
            "totalEarnings": 0,
            "totalWithdrawals": 0,
            "createdAt": datetime.utcnow(),
            "updatedAt": datetime.utcnow()
        })
        
        # Add to team structure if has sponsor
        if sponsor:
            teams_collection.insert_one({
                "userId": user_id,
                "sponsorId": str(sponsor["_id"]),
                "placement": user.placement,
                "level": 1,
                "createdAt": datetime.utcnow()
            })
        
        # Create access token
        access_token = create_access_token(data={"sub": user.username, "userId": user_id})
        
        # Get created user
        created_user = users_collection.find_one({"_id": result.inserted_id})
        user_response = serialize_doc(created_user)
        user_response.pop("password", None)
        
        return {
            "success": True,
            "message": "Registration successful",
            "user": user_response,
            "token": access_token
        }
        
    except HTTPException as he:
        raise he
    except Exception as e:
        print(f"Registration error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/auth/sign-in/email")
async def login_email(credentials: dict = Body(...)):
    """Login with email and password"""
    try:
        email = credentials.get("email")
        password = credentials.get("password")
        
        if not email or not password:
            raise HTTPException(status_code=400, detail="Email and password required")
        
        # Find user
        user = users_collection.find_one({"email": email})
        if not user:
            raise HTTPException(status_code=401, detail="Invalid credentials")
        
        # Verify password
        if not verify_password(password, user["password"]):
            raise HTTPException(status_code=401, detail="Invalid credentials")
        
        # Check if active
        if not user.get("isActive", False):
            raise HTTPException(status_code=403, detail="Account is inactive")
        
        # Create token
        user_id = str(user["_id"])
        access_token = create_access_token(data={"sub": user["username"], "userId": user_id})
        
        # Prepare response
        user_response = serialize_doc(user)
        user_response.pop("password", None)
        
        return {
            "user": user_response,
            "token": access_token,
            "session": {"token": access_token}
        }
        
    except HTTPException as he:
        raise he
    except Exception as e:
        print(f"Login error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/auth/sign-in/username")
async def login_username(credentials: dict = Body(...)):
    """Login with username and password"""
    try:
        username = credentials.get("username")
        password = credentials.get("password")
        
        if not username or not password:
            raise HTTPException(status_code=400, detail="Username and password required")
        
        # Find user
        user = users_collection.find_one({"username": username})
        if not user:
            raise HTTPException(status_code=401, detail="Invalid credentials")
        
        # Verify password
        if not verify_password(password, user["password"]):
            raise HTTPException(status_code=401, detail="Invalid credentials")
        
        # Check if active
        if not user.get("isActive", False):
            raise HTTPException(status_code=403, detail="Account is inactive")
        
        # Create token
        user_id = str(user["_id"])
        access_token = create_access_token(data={"sub": user["username"], "userId": user_id})
        
        # Prepare response
        user_response = serialize_doc(user)
        user_response.pop("password", None)
        
        return {
            "user": user_response,
            "token": access_token,
            "session": {"token": access_token}
        }
        
    except HTTPException as he:
        raise he
    except Exception as e:
        print(f"Login error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/auth/lookup-referral")
async def lookup_referral(data: ReferralLookup):
    """Lookup user by referral ID"""
    try:
        user = users_collection.find_one({"referralId": data.referralId})
        if not user:
            return {"success": False, "message": "Invalid referral ID"}
        
        return {
            "success": True,
            "data": {
                "username": user["username"],
                "email": user.get("email", ""),
                "name": user["name"]
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/auth/get-session")
async def get_session():
    """Get current session - placeholder"""
    # In real implementation, you'd validate JWT token from cookie/header
    return {"user": None}

@app.post("/api/auth/sign-out")
async def logout():
    """Logout user"""
    return {"success": True, "message": "Logged out successfully"}

# ==================== USER ROUTES ====================

@app.get("/api/user/profile")
async def get_profile(current_user: dict = Depends(get_current_active_user)):
    """Get user profile"""
    try:
        user_data = serialize_doc(current_user)
        user_data.pop("password", None)
        
        # Get wallet info
        wallet = wallets_collection.find_one({"userId": current_user["id"]})
        if wallet:
            user_data["wallet"] = serialize_doc(wallet)
        
        # Get team count
        team_count = teams_collection.count_documents({"sponsorId": current_user["id"]})
        user_data["teamSize"] = team_count
        
        # Get left and right team counts
        left_count = teams_collection.count_documents({
            "sponsorId": current_user["id"],
            "placement": "LEFT"
        })
        right_count = teams_collection.count_documents({
            "sponsorId": current_user["id"],
            "placement": "RIGHT"
        })
        user_data["leftTeamSize"] = left_count
        user_data["rightTeamSize"] = right_count
        
        return {"success": True, "data": user_data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.put("/api/user/profile")
async def update_profile(
    data: dict = Body(...),
    current_user: dict = Depends(get_current_active_user)
):
    """Update user profile"""
    try:
        # Fields that can be updated
        allowed_fields = ["name", "mobile", "email"]
        update_data = {k: v for k, v in data.items() if k in allowed_fields}
        update_data["updatedAt"] = datetime.utcnow()
        
        users_collection.update_one(
            {"_id": ObjectId(current_user["id"])},
            {"$set": update_data}
        )
        
        return {"success": True, "message": "Profile updated successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/user/change-password")
async def change_password(
    data: dict = Body(...),
    current_user: dict = Depends(get_current_active_user)
):
    """Change user password"""
    try:
        old_password = data.get("oldPassword")
        new_password = data.get("newPassword")
        
        if not old_password or not new_password:
            raise HTTPException(status_code=400, detail="Old and new password required")
        
        # Get user from database
        user = users_collection.find_one({"_id": ObjectId(current_user["id"])})
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        # Verify old password
        if not verify_password(old_password, user["password"]):
            raise HTTPException(status_code=400, detail="Incorrect old password")
        
        # Update password
        users_collection.update_one(
            {"_id": ObjectId(current_user["id"])},
            {"$set": {
                "password": hash_password(new_password),
                "updatedAt": datetime.utcnow()
            }}
        )
        
        return {"success": True, "message": "Password changed successfully"}
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/user/referral/{referral_id}")
async def get_referral_info(referral_id: str):
    """Get referral user information"""
    try:
        user = users_collection.find_one({"referralId": referral_id})
        if not user:
            raise HTTPException(status_code=404, detail="Referral ID not found")
        
        return {
            "success": True,
            "data": {
                "name": user["name"],
                "referralId": user["referralId"],
                "isActive": user.get("isActive", False)
            }
        }
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/user/dashboard")
async def get_user_dashboard(current_user: dict = Depends(get_current_active_user)):
    """Get user dashboard statistics"""
    try:
        user_id = current_user["id"]
        
        # Get wallet
        wallet = wallets_collection.find_one({"userId": user_id})
        wallet_data = serialize_doc(wallet) if wallet else {
            "balance": 0,
            "totalEarnings": 0,
            "totalWithdrawals": 0
        }
        
        # Get team statistics
        total_team = teams_collection.count_documents({"sponsorId": user_id})
        left_team = teams_collection.count_documents({
            "sponsorId": user_id,
            "placement": "LEFT"
        })
        right_team = teams_collection.count_documents({
            "sponsorId": user_id,
            "placement": "RIGHT"
        })
        
        # Get current plan
        current_plan = None
        if current_user.get("currentPlan"):
            plan = plans_collection.find_one({"_id": ObjectId(current_user["currentPlan"])})
            if plan:
                current_plan = serialize_doc(plan)
        
        # Get recent transactions
        transactions = list(transactions_collection.find(
            {"userId": user_id}
        ).sort("createdAt", DESCENDING).limit(5))
        
        return {
            "success": True,
            "data": {
                "wallet": wallet_data,
                "team": {
                    "total": total_team,
                    "left": left_team,
                    "right": right_team
                },
                "currentPlan": current_plan,
                "recentTransactions": serialize_doc(transactions)
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/user/team/tree")
async def get_team_tree(current_user: dict = Depends(get_current_active_user)):
    """Get user's team tree (binary structure)"""
    try:
        user_id = current_user["id"]
        
        def build_tree(parent_id, depth=0, max_depth=3):
            if depth > max_depth:
                return None
            
            user = users_collection.find_one({"_id": ObjectId(parent_id)})
            if not user:
                return None
            
            # Get children
            left_child = teams_collection.find_one({
                "sponsorId": parent_id,
                "placement": "LEFT"
            })
            right_child = teams_collection.find_one({
                "sponsorId": parent_id,
                "placement": "RIGHT"
            })
            
            node = {
                "id": str(user["_id"]),
                "name": user["name"],
                "referralId": user["referralId"],
                "placement": user.get("placement"),
                "currentPlan": user.get("currentPlan"),
                "isActive": user.get("isActive", False),
                "left": None,
                "right": None
            }
            
            if left_child:
                node["left"] = build_tree(left_child["userId"], depth + 1, max_depth)
            
            if right_child:
                node["right"] = build_tree(right_child["userId"], depth + 1, max_depth)
            
            return node
        
        tree = build_tree(user_id)
        
        return {
            "success": True,
            "data": tree
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/user/team/list")
async def get_team_list(current_user: dict = Depends(get_current_active_user)):
    """Get user's team list"""
    try:
        user_id = current_user["id"]
        
        # Get all team members
        team_members = list(teams_collection.find({"sponsorId": user_id}))
        
        result = []
        for member in team_members:
            user = users_collection.find_one({"_id": ObjectId(member["userId"])})
            if user:
                result.append({
                    "id": str(user["_id"]),
                    "name": user["name"],
                    "referralId": user["referralId"],
                    "mobile": user.get("mobile", ""),
                    "placement": member.get("placement"),
                    "currentPlan": user.get("currentPlan"),
                    "isActive": user.get("isActive", False),
                    "joinedAt": user.get("createdAt", datetime.utcnow()).isoformat()
                })
        
        return {
            "success": True,
            "data": serialize_doc(result)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ==================== PLANS ROUTES ====================

@app.get("/api/plans")
async def get_plans():
    """Get all active plans"""
    try:
        plans = list(plans_collection.find({"isActive": True}))
        return {
            "success": True,
            "data": serialize_doc(plans)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/plans/activate")
async def activate_plan(
    data: dict = Body(...),
    current_user: dict = Depends(get_current_active_user)
):
    """Activate a plan for user"""
    try:
        plan_id = data.get("planId")
        if not plan_id:
            raise HTTPException(status_code=400, detail="Plan ID required")
        
        # Get plan
        plan = plans_collection.find_one({"_id": ObjectId(plan_id)})
        if not plan:
            raise HTTPException(status_code=404, detail="Plan not found")
        
        user_id = current_user["id"]
        
        # Update user's current plan
        users_collection.update_one(
            {"_id": ObjectId(user_id)},
            {
                "$set": {
                    "currentPlan": str(plan["_id"]),
                    "totalPV": plan["pv"],
                    "updatedAt": datetime.utcnow()
                }
            }
        )
        
        # Create transaction
        transactions_collection.insert_one({
            "userId": user_id,
            "type": "PLAN_ACTIVATION",
            "amount": plan["amount"],
            "description": f"Activated {plan['name']} plan",
            "status": "COMPLETED",
            "createdAt": datetime.utcnow()
        })
        
        # Add referral income to sponsor if exists
        if current_user.get("sponsorId"):
            sponsor = users_collection.find_one({"referralId": current_user["sponsorId"]})
            if sponsor:
                sponsor_id = str(sponsor["_id"])
                
                # Update sponsor wallet
                wallets_collection.update_one(
                    {"userId": sponsor_id},
                    {
                        "$inc": {
                            "balance": plan["referralIncome"],
                            "totalEarnings": plan["referralIncome"]
                        },
                        "$set": {"updatedAt": datetime.utcnow()}
                    }
                )
                
                # Create transaction for sponsor
                transactions_collection.insert_one({
                    "userId": sponsor_id,
                    "type": "REFERRAL_INCOME",
                    "amount": plan["referralIncome"],
                    "description": f"Referral income from {current_user['name']}",
                    "status": "COMPLETED",
                    "fromUser": user_id,
                    "createdAt": datetime.utcnow()
                })
        
        return {
            "success": True,
            "message": "Plan activated successfully"
        }
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ==================== WALLET & TRANSACTIONS ====================

@app.get("/api/wallet/balance")
async def get_wallet_balance(current_user: dict = Depends(get_current_active_user)):
    """Get wallet balance"""
    try:
        wallet = wallets_collection.find_one({"userId": current_user["id"]})
        if not wallet:
            return {
                "success": True,
                "data": {
                    "balance": 0,
                    "totalEarnings": 0,
                    "totalWithdrawals": 0
                }
            }
        
        return {
            "success": True,
            "data": serialize_doc(wallet)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/wallet/transactions")
async def get_transactions(
    current_user: dict = Depends(get_current_active_user),
    limit: int = 50,
    skip: int = 0
):
    """Get user transactions"""
    try:
        transactions = list(transactions_collection.find(
            {"userId": current_user["id"]}
        ).sort("createdAt", DESCENDING).skip(skip).limit(limit))
        
        total = transactions_collection.count_documents({"userId": current_user["id"]})
        
        return {
            "success": True,
            "data": serialize_doc(transactions),
            "total": total,
            "limit": limit,
            "skip": skip
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ==================== WITHDRAWAL ====================

@app.post("/api/withdrawal/request")
async def create_withdrawal_request(
    data: dict = Body(...),
    current_user: dict = Depends(get_current_active_user)
):
    """Create withdrawal request"""
    try:
        amount = data.get("amount")
        bank_details = data.get("bankDetails", {})
        
        if not amount or amount <= 0:
            raise HTTPException(status_code=400, detail="Invalid amount")
        
        # Check wallet balance
        wallet = wallets_collection.find_one({"userId": current_user["id"]})
        if not wallet or wallet.get("balance", 0) < amount:
            raise HTTPException(status_code=400, detail="Insufficient balance")
        
        # Create withdrawal request
        withdrawal = {
            "userId": current_user["id"],
            "amount": amount,
            "bankDetails": bank_details,
            "status": "PENDING",
            "requestedAt": datetime.utcnow(),
            "processedAt": None,
            "processedBy": None
        }
        
        result = withdrawals_collection.insert_one(withdrawal)
        
        # Deduct from balance (hold)
        wallets_collection.update_one(
            {"userId": current_user["id"]},
            {"$inc": {"balance": -amount}}
        )
        
        # Create transaction
        transactions_collection.insert_one({
            "userId": current_user["id"],
            "type": "WITHDRAWAL_REQUEST",
            "amount": -amount,
            "description": "Withdrawal request created",
            "status": "PENDING",
            "withdrawalId": str(result.inserted_id),
            "createdAt": datetime.utcnow()
        })
        
        return {
            "success": True,
            "message": "Withdrawal request created successfully",
            "withdrawalId": str(result.inserted_id)
        }
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/withdrawal/history")
async def get_withdrawal_history(current_user: dict = Depends(get_current_active_user)):
    """Get withdrawal history"""
    try:
        withdrawals = list(withdrawals_collection.find(
            {"userId": current_user["id"]}
        ).sort("requestedAt", DESCENDING))
        
        return {
            "success": True,
            "data": serialize_doc(withdrawals)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ==================== SETTINGS ROUTES ====================

@app.get("/api/settings/public")
async def get_public_settings():
    """Get public settings"""
    try:
        settings = settings_collection.find_one({})
        if not settings:
            # Return default settings
            return {
                "success": True,
                "data": {
                    "companyName": "VSV Unite",
                    "companyEmail": "info@vsvunite.com",
                    "companyPhone": "+91 9999999999",
                    "metaTitle": "VSV Unite - MLM Platform",
                    "metaDescription": "Join VSV Unite for transparent MLM opportunities"
                }
            }
        
        return {
            "success": True,
            "data": serialize_doc(settings)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/settings")
async def get_settings():
    """Get all settings (admin only)"""
    try:
        settings = settings_collection.find_one({})
        if not settings:
            return {"success": True, "data": {}}
        
        return {
            "success": True,
            "data": serialize_doc(settings)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.put("/api/settings/general")
async def update_general_settings(data: dict = Body(...)):
    """Update general settings"""
    try:
        settings_collection.update_one(
            {},
            {"$set": {**data, "updatedAt": datetime.utcnow()}},
            upsert=True
        )
        return {"success": True, "message": "Settings updated successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.put("/api/settings/seo")
async def update_seo_settings(data: dict = Body(...)):
    """Update SEO settings"""
    try:
        settings_collection.update_one(
            {},
            {"$set": {**data, "updatedAt": datetime.utcnow()}},
            upsert=True
        )
        return {"success": True, "message": "SEO settings updated successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.put("/api/settings/hero")
async def update_hero_settings(data: dict = Body(...)):
    """Update hero settings"""
    try:
        settings_collection.update_one(
            {},
            {"$set": {**data, "updatedAt": datetime.utcnow()}},
            upsert=True
        )
        return {"success": True, "message": "Hero settings updated successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/settings/email-configuration")
async def get_email_config():
    """Get email configuration"""
    try:
        config = email_configs_collection.find_one({})
        if not config:
            return {"success": True, "emailConfig": None}
        
        config_data = serialize_doc(config)
        # Mask password
        if "smtpPassword" in config_data:
            config_data["smtpPassword"] = "****"
        
        return {"success": True, "emailConfig": config_data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/settings/email-configuration")
async def update_email_config(data: dict = Body(...)):
    """Update email configuration"""
    try:
        email_configs_collection.update_one(
            {},
            {"$set": {**data, "updatedAt": datetime.utcnow()}},
            upsert=True
        )
        return {"success": True, "message": "Email configuration updated"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ==================== ADMIN ROUTES ====================

@app.get("/api/admin/dashboard")
async def get_admin_dashboard(current_admin: dict = Depends(get_current_admin)):
    """Get admin dashboard statistics"""
    try:
        # Total users
        total_users = users_collection.count_documents({"role": "user"})
        active_users = users_collection.count_documents({"role": "user", "isActive": True})
        
        # Total earnings (sum of all wallets)
        pipeline = [
            {"$group": {
                "_id": None,
                "totalEarnings": {"$sum": "$totalEarnings"},
                "totalBalance": {"$sum": "$balance"},
                "totalWithdrawals": {"$sum": "$totalWithdrawals"}
            }}
        ]
        wallet_stats = list(wallets_collection.aggregate(pipeline))
        wallet_data = wallet_stats[0] if wallet_stats else {
            "totalEarnings": 0,
            "totalBalance": 0,
            "totalWithdrawals": 0
        }
        
        # Pending withdrawals
        pending_withdrawals = withdrawals_collection.count_documents({"status": "PENDING"})
        
        # Plan distribution
        plan_distribution = {}
        for plan in plans_collection.find({"isActive": True}):
            count = users_collection.count_documents({"currentPlan": str(plan["_id"])})
            plan_distribution[plan["name"]] = count
        
        # Recent users
        recent_users = list(users_collection.find(
            {"role": "user"}
        ).sort("createdAt", DESCENDING).limit(5))
        
        return {
            "success": True,
            "data": {
                "users": {
                    "total": total_users,
                    "active": active_users,
                    "inactive": total_users - active_users
                },
                "earnings": wallet_data,
                "pendingWithdrawals": pending_withdrawals,
                "planDistribution": plan_distribution,
                "recentUsers": serialize_doc(recent_users)
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/admin/users")
async def get_all_users(
    current_admin: dict = Depends(get_current_admin),
    limit: int = 50,
    skip: int = 0,
    search: Optional[str] = None
):
    """Get all users (admin only)"""
    try:
        query = {"role": "user"}
        
        if search:
            query["$or"] = [
                {"name": {"$regex": search, "$options": "i"}},
                {"email": {"$regex": search, "$options": "i"}},
                {"referralId": {"$regex": search, "$options": "i"}},
                {"mobile": {"$regex": search, "$options": "i"}}
            ]
        
        users = list(users_collection.find(query).skip(skip).limit(limit))
        total = users_collection.count_documents(query)
        
        # Remove passwords
        for user in users:
            user.pop("password", None)
        
        return {
            "success": True,
            "data": serialize_doc(users),
            "total": total,
            "limit": limit,
            "skip": skip
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.put("/api/admin/users/{user_id}/status")
async def update_user_status(
    user_id: str,
    data: dict = Body(...),
    current_admin: dict = Depends(get_current_admin)
):
    """Update user status (activate/deactivate)"""
    try:
        is_active = data.get("isActive")
        if is_active is None:
            raise HTTPException(status_code=400, detail="isActive field required")
        
        users_collection.update_one(
            {"_id": ObjectId(user_id)},
            {"$set": {"isActive": is_active, "updatedAt": datetime.utcnow()}}
        )
        
        return {
            "success": True,
            "message": f"User {'activated' if is_active else 'deactivated'} successfully"
        }
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/admin/withdrawals")
async def get_all_withdrawals(
    current_admin: dict = Depends(get_current_admin),
    status: Optional[str] = None
):
    """Get all withdrawal requests"""
    try:
        query = {}
        if status:
            query["status"] = status.upper()
        
        withdrawals = list(withdrawals_collection.find(query).sort("requestedAt", DESCENDING))
        
        # Add user details
        result = []
        for withdrawal in withdrawals:
            user = users_collection.find_one({"_id": ObjectId(withdrawal["userId"])})
            withdrawal_data = serialize_doc(withdrawal)
            if user:
                withdrawal_data["userName"] = user["name"]
                withdrawal_data["userEmail"] = user.get("email", "")
                withdrawal_data["userMobile"] = user.get("mobile", "")
            result.append(withdrawal_data)
        
        return {
            "success": True,
            "data": result
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.put("/api/admin/withdrawals/{withdrawal_id}/approve")
async def approve_withdrawal(
    withdrawal_id: str,
    current_admin: dict = Depends(get_current_admin)
):
    """Approve withdrawal request"""
    try:
        withdrawal = withdrawals_collection.find_one({"_id": ObjectId(withdrawal_id)})
        if not withdrawal:
            raise HTTPException(status_code=404, detail="Withdrawal not found")
        
        if withdrawal["status"] != "PENDING":
            raise HTTPException(status_code=400, detail="Withdrawal already processed")
        
        # Update withdrawal status
        withdrawals_collection.update_one(
            {"_id": ObjectId(withdrawal_id)},
            {
                "$set": {
                    "status": "APPROVED",
                    "processedAt": datetime.utcnow(),
                    "processedBy": current_admin["id"]
                }
            }
        )
        
        # Update wallet
        wallets_collection.update_one(
            {"userId": withdrawal["userId"]},
            {"$inc": {"totalWithdrawals": withdrawal["amount"]}}
        )
        
        # Update transaction
        transactions_collection.update_one(
            {"withdrawalId": withdrawal_id},
            {"$set": {"status": "COMPLETED"}}
        )
        
        return {
            "success": True,
            "message": "Withdrawal approved successfully"
        }
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.put("/api/admin/withdrawals/{withdrawal_id}/reject")
async def reject_withdrawal(
    withdrawal_id: str,
    data: dict = Body(...),
    current_admin: dict = Depends(get_current_admin)
):
    """Reject withdrawal request"""
    try:
        withdrawal = withdrawals_collection.find_one({"_id": ObjectId(withdrawal_id)})
        if not withdrawal:
            raise HTTPException(status_code=404, detail="Withdrawal not found")
        
        if withdrawal["status"] != "PENDING":
            raise HTTPException(status_code=400, detail="Withdrawal already processed")
        
        reason = data.get("reason", "No reason provided")
        
        # Update withdrawal status
        withdrawals_collection.update_one(
            {"_id": ObjectId(withdrawal_id)},
            {
                "$set": {
                    "status": "REJECTED",
                    "rejectionReason": reason,
                    "processedAt": datetime.utcnow(),
                    "processedBy": current_admin["id"]
                }
            }
        )
        
        # Return amount to wallet
        wallets_collection.update_one(
            {"userId": withdrawal["userId"]},
            {"$inc": {"balance": withdrawal["amount"]}}
        )
        
        # Update transaction
        transactions_collection.update_one(
            {"withdrawalId": withdrawal_id},
            {"$set": {"status": "REJECTED"}}
        )
        
        return {
            "success": True,
            "message": "Withdrawal rejected successfully"
        }
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/admin/plans")
async def get_admin_plans(current_admin: dict = Depends(get_current_admin)):
    """Get all plans (admin)"""
    try:
        plans = list(plans_collection.find({}))
        return {
            "success": True,
            "data": serialize_doc(plans)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/admin/plans")
async def create_plan(
    data: dict = Body(...),
    current_admin: dict = Depends(get_current_admin)
):
    """Create new plan"""
    try:
        plan_data = {
            **data,
            "isActive": data.get("isActive", True),
            "createdAt": datetime.utcnow(),
            "updatedAt": datetime.utcnow()
        }
        
        result = plans_collection.insert_one(plan_data)
        
        return {
            "success": True,
            "message": "Plan created successfully",
            "planId": str(result.inserted_id)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.put("/api/admin/plans/{plan_id}")
async def update_plan(
    plan_id: str,
    data: dict = Body(...),
    current_admin: dict = Depends(get_current_admin)
):
    """Update plan"""
    try:
        data["updatedAt"] = datetime.utcnow()
        
        plans_collection.update_one(
            {"_id": ObjectId(plan_id)},
            {"$set": data}
        )
        
        return {
            "success": True,
            "message": "Plan updated successfully"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ==================== HEALTH CHECK ====================

@app.get("/")
async def root():
    return {
        "message": "VSV Unite MLM API",
        "version": "1.0.0",
        "status": "running"
    }

# ============ TOPUP/PLAN ACTIVATION MANAGEMENT (ADMIN) ============

class TopupRequest(BaseModel):
    userId: str
    planId: str
    amount: float
    paymentMode: str
    transactionId: str
    paymentProof: Optional[str] = None

@app.get("/api/admin/topups")
async def get_all_topups(
    current_admin: dict = Depends(get_current_admin),
    status: Optional[str] = None
):
    """Get all topup/plan activation requests"""
    try:
        query = {}
        if status:
            query["status"] = status.upper()
        
        topups = list(topups_collection.find(query).sort("requestedAt", DESCENDING))
        
        # Enrich with user and plan details
        for topup in topups:
            if topup.get("userId"):
                user = users_collection.find_one({"_id": ObjectId(topup["userId"])})
                if user:
                    topup["userName"] = user.get("name")
                    topup["userEmail"] = user.get("email")
                    topup["referralId"] = user.get("referralId")
            
            if topup.get("planId"):
                plan = plans_collection.find_one({"_id": ObjectId(topup["planId"])})
                if plan:
                    topup["planName"] = plan.get("name")
        
        return {
            "success": True,
            "data": serialize_doc(topups)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/admin/topups/{topup_id}/approve")
async def approve_topup(
    topup_id: str,
    current_admin: dict = Depends(get_current_admin)
):
    """Approve a topup/plan activation request"""
    try:
        topup = topups_collection.find_one({"_id": ObjectId(topup_id)})
        if not topup:
            raise HTTPException(status_code=404, detail="Topup request not found")
        
        if topup["status"] != "PENDING":
            raise HTTPException(status_code=400, detail="Only pending requests can be approved")
        
        user_id = topup["userId"]
        plan_id = topup["planId"]
        
        # Get plan details
        plan = plans_collection.find_one({"_id": ObjectId(plan_id)})
        if not plan:
            raise HTTPException(status_code=404, detail="Plan not found")
        
        # Update user's current plan
        users_collection.update_one(
            {"_id": ObjectId(user_id)},
            {
                "$set": {
                    "currentPlanId": plan_id,
                    "currentPlan": plan["name"],
                    "activatedAt": datetime.utcnow()
                }
            }
        )
        
        # Update topup status
        topups_collection.update_one(
            {"_id": ObjectId(topup_id)},
            {
                "$set": {
                    "status": "APPROVED",
                    "approvedAt": datetime.utcnow(),
                    "approvedBy": current_admin["id"]
                }
            }
        )
        
        # Give referral income to sponsor
        user = users_collection.find_one({"_id": ObjectId(user_id)})
        if user and user.get("sponsorId"):
            sponsor = users_collection.find_one({"_id": ObjectId(user["sponsorId"])})
            if sponsor:
                referral_income = plan.get("referralIncome", 0)
                
                # Update sponsor wallet
                wallets_collection.update_one(
                    {"userId": user["sponsorId"]},
                    {"$inc": {"balance": referral_income}}
                )
                
                # Create transaction for sponsor
                transactions_collection.insert_one({
                    "userId": user["sponsorId"],
                    "type": "REFERRAL_INCOME",
                    "amount": referral_income,
                    "description": f"Referral income from {user['name']} plan activation",
                    "status": "COMPLETED",
                    "createdAt": datetime.utcnow()
                })
        
        return {
            "success": True,
            "message": "Topup approved successfully"
        }
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/admin/topups/{topup_id}/reject")
async def reject_topup(
    topup_id: str,
    data: dict = Body(...),
    current_admin: dict = Depends(get_current_admin)
):
    """Reject a topup/plan activation request"""
    try:
        topup = topups_collection.find_one({"_id": ObjectId(topup_id)})
        if not topup:
            raise HTTPException(status_code=404, detail="Topup request not found")
        
        if topup["status"] != "PENDING":
            raise HTTPException(status_code=400, detail="Only pending requests can be rejected")
        
        reason = data.get("reason", "Rejected by admin")
        
        topups_collection.update_one(
            {"_id": ObjectId(topup_id)},
            {
                "$set": {
                    "status": "REJECTED",
                    "rejectedAt": datetime.utcnow(),
                    "rejectedBy": current_admin["id"],
                    "rejectionReason": reason
                }
            }
        )
        
        return {
            "success": True,
            "message": "Topup rejected successfully"
        }
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ============ REPORTS & ANALYTICS (ADMIN) ============

@app.get("/api/admin/reports/dashboard")
async def get_dashboard_reports(
    current_admin: dict = Depends(get_current_admin)
):
    """Get dashboard analytics and reports"""
    try:
        # Total users count
        total_users = users_collection.count_documents({"role": "user"})
        active_users = users_collection.count_documents({"role": "user", "isActive": True})
        
        # Total earnings (sum of all credit transactions)
        total_earnings_pipeline = [
            {"$match": {"amount": {"$gt": 0}}},
            {"$group": {"_id": None, "total": {"$sum": "$amount"}}}
        ]
        total_earnings_result = list(transactions_collection.aggregate(total_earnings_pipeline))
        total_earnings = total_earnings_result[0]["total"] if total_earnings_result else 0
        
        # Total withdrawals
        total_withdrawals_pipeline = [
            {"$match": {"status": "APPROVED"}},
            {"$group": {"_id": None, "total": {"$sum": "$amount"}}}
        ]
        total_withdrawals_result = list(withdrawals_collection.aggregate(total_withdrawals_pipeline))
        total_withdrawals = total_withdrawals_result[0]["total"] if total_withdrawals_result else 0
        
        # Pending withdrawals
        pending_withdrawals = withdrawals_collection.count_documents({"status": "PENDING"})
        pending_withdrawals_amount_pipeline = [
            {"$match": {"status": "PENDING"}},
            {"$group": {"_id": None, "total": {"$sum": "$amount"}}}
        ]
        pending_withdrawals_amount_result = list(withdrawals_collection.aggregate(pending_withdrawals_amount_pipeline))
        pending_withdrawals_amount = pending_withdrawals_amount_result[0]["total"] if pending_withdrawals_amount_result else 0
        
        # Plan distribution
        plan_distribution = {}
        for plan in plans_collection.find():
            count = users_collection.count_documents({"currentPlanId": str(plan["_id"])})
            plan_distribution[plan["name"]] = count
        
        # Recent registrations (last 7 days)
        seven_days_ago = datetime.utcnow() - timedelta(days=7)
        recent_registrations = users_collection.count_documents({
            "role": "user",
            "createdAt": {"$gte": seven_days_ago}
        })
        
        # Daily business report (last 7 days)
        daily_reports = []
        for i in range(6, -1, -1):
            day_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=i)
            day_end = day_start + timedelta(days=1)
            
            # New users on this day
            new_users = users_collection.count_documents({
                "role": "user",
                "createdAt": {"$gte": day_start, "$lt": day_end}
            })
            
            # Topups on this day
            topups_pipeline = [
                {"$match": {
                    "status": "APPROVED",
                    "approvedAt": {"$gte": day_start, "$lt": day_end}
                }},
                {"$group": {"_id": None, "total": {"$sum": "$amount"}}}
            ]
            topups_result = list(topups_collection.aggregate(topups_pipeline))
            topups_amount = topups_result[0]["total"] if topups_result else 0
            
            # Payouts on this day
            payouts_pipeline = [
                {"$match": {
                    "status": "APPROVED",
                    "approvedAt": {"$gte": day_start, "$lt": day_end}
                }},
                {"$group": {"_id": None, "total": {"$sum": "$amount"}}}
            ]
            payouts_result = list(withdrawals_collection.aggregate(payouts_pipeline))
            payouts_amount = payouts_result[0]["total"] if payouts_result else 0
            
            daily_reports.append({
                "date": day_start.strftime("%Y-%m-%d"),
                "newUsers": new_users,
                "topups": topups_amount,
                "payouts": payouts_amount,
                "netBusiness": topups_amount - payouts_amount
            })
        
        # Income breakdown
        income_types = {}
        for income_type in ["REFERRAL_INCOME", "MATCHING_INCOME", "LEVEL_INCOME"]:
            pipeline = [
                {"$match": {"type": income_type}},
                {"$group": {"_id": None, "total": {"$sum": "$amount"}}}
            ]
            result = list(transactions_collection.aggregate(pipeline))
            income_types[income_type] = result[0]["total"] if result else 0
        
        return {
            "success": True,
            "data": {
                "overview": {
                    "totalUsers": total_users,
                    "activeUsers": active_users,
                    "totalEarnings": total_earnings,
                    "totalWithdrawals": total_withdrawals,
                    "pendingWithdrawals": pending_withdrawals,
                    "pendingWithdrawalsAmount": pending_withdrawals_amount,
                    "recentRegistrations": recent_registrations
                },
                "planDistribution": plan_distribution,
                "dailyReports": daily_reports,
                "incomeBreakdown": income_types
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/health")
async def health_check():
    """Health check endpoint"""
    try:
        # Check MongoDB connection
        client.admin.command('ping')
        return {
            "status": "healthy",
            "database": "connected",
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "database": "disconnected",
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat()
        }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5000)
