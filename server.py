from fastapi import FastAPI, HTTPException, Depends, status, Body
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

# ==================== HEALTH CHECK ====================

@app.get("/")
async def root():
    return {
        "message": "VSV Unite MLM API",
        "version": "1.0.0",
        "status": "running"
    }

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
