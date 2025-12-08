# MLM VSV Unite - Backend Architecture

## 📁 Project Structure

```
/app/backend/
├── app/
│   ├── __init__.py
│   │
│   ├── core/                    # Core configuration
│   │   ├── __init__.py
│   │   ├── config.py           # Environment variables & settings
│   │   ├── database.py         # MongoDB connection & collections
│   │   └── security.py         # JWT, authentication, permissions
│   │
│   ├── models/                  # Pydantic schemas
│   │   ├── __init__.py
│   │   ├── user.py             # User registration, login schemas
│   │   ├── plan.py             # Plan create/update schemas
│   │   ├── transaction.py      # Transaction schemas
│   │   └── withdrawal.py       # Withdrawal request schemas
│   │
│   ├── routes/                  # API endpoints (To be created)
│   │   ├── __init__.py
│   │   ├── auth.py             # /api/auth/*
│   │   ├── users.py            # /api/user/*
│   │   ├── admin.py            # /api/admin/*
│   │   ├── plans.py            # /api/plans/*
│   │   ├── wallet.py           # /api/wallet/*
│   │   ├── withdrawals.py      # /api/withdrawal/*
│   │   ├── settings.py         # /api/settings/*
│   │   └── reports.py          # /api/admin/reports/*
│   │
│   ├── services/                # Business logic
│   │   ├── __init__.py
│   │   ├── mlm_service.py      # Binary MLM calculations
│   │   └── wallet_service.py   # Wallet operations
│   │
│   └── utils/                   # Utilities
│       ├── __init__.py
│       ├── helpers.py          # Common helper functions
│       └── reports.py          # Excel/PDF generation
│
├── main.py                      # Application entry point
├── server.py                    # Old monolithic file (to be deprecated)
├── requirements.txt
└── .env
```

## 🏗️ Architecture Pattern

**Type:** Layered Architecture (Clean Architecture inspired)

**Layers:**
1. **Core Layer** - Configuration, database, security
2. **Model Layer** - Data validation (Pydantic)
3. **Service Layer** - Business logic
4. **Route Layer** - API endpoints (FastAPI)
5. **Utility Layer** - Helper functions

## 📊 Component Breakdown

### Core Components

**config.py** (50 lines)
- Environment variable management
- Application settings
- Configuration validation

**database.py** (30 lines)
- MongoDB connection
- Collection references
- Database utilities

**security.py** (80 lines)
- Password hashing (bcrypt)
- JWT token generation/validation
- User authentication
- Permission checks (user/admin)

### Models (Pydantic Schemas)

**user.py** - User-related schemas
- UserRegister: Registration validation
- UserLogin: Login credentials
- UserUpdate: Profile updates

**plan.py** - Plan schemas
- PlanCreate: New plan creation
- PlanUpdate: Plan modifications

**transaction.py** - Transaction schemas
- TransactionCreate: New transaction

**withdrawal.py** - Withdrawal schemas
- WithdrawalRequest: Withdrawal creation

### Services (Business Logic)

**mlm_service.py** (200 lines)
- `distribute_pv_upward()` - PV distribution in binary tree
- `calculate_matching_income()` - Single user matching
- `calculate_daily_matching_for_all_users()` - Batch calculation
- `add_user_to_binary_tree()` - Add user to tree

**wallet_service.py** (120 lines)
- `create_wallet()` - Initialize wallet
- `get_wallet_balance()` - Check balance
- `credit_wallet()` - Add funds
- `debit_wallet()` - Deduct funds
- `get_transactions()` - Transaction history

### Utilities

**helpers.py** (60 lines)
- `serialize_doc()` - MongoDB to JSON
- `generate_referral_id()` - Unique ID generation
- `parse_date_range()` - Date validation

**reports.py** (120 lines)
- `generate_excel_report()` - Excel file creation
- `generate_pdf_report()` - PDF file creation

## 🔄 Data Flow

### Example: User Registration

```
1. Request → Route (auth.py)
   ↓
2. Validation → Model (UserRegister)
   ↓
3. Business Logic → Service (wallet_service, mlm_service)
   ↓
4. Database → Core (database.py)
   ↓
5. Response ← Route (auth.py)
```

### Example: Matching Income Calculation

```
1. Trigger (End of day)
   ↓
2. Service (mlm_service.calculate_daily_matching_for_all_users)
   ↓
3. For each user:
   - Check leftPV, rightPV
   - Calculate min(left, right)
   - Apply daily capping
   - Credit wallet (wallet_service)
   - Create transaction
   - Flush PV
```

## 🎯 Design Principles

1. **Separation of Concerns**
   - Routes handle HTTP
   - Services handle business logic
   - Models handle validation
   - Core handles infrastructure

2. **Dependency Injection**
   - FastAPI's Depends() for authentication
   - Services injected into routes

3. **Single Responsibility**
   - Each file has one clear purpose
   - Small, focused functions

4. **DRY (Don't Repeat Yourself)**
   - Common logic in services
   - Utilities for shared functions

## 📈 Scalability

**Current Structure Supports:**
- ✅ 50,000 users
- ✅ 500-1000 DAU
- ✅ 20-40 concurrent users

**Easy to Scale:**
1. Add caching layer (Redis)
2. Add message queue (Celery)
3. Separate read/write databases
4. Microservices (if needed)

## 🧪 Testing Strategy

**Unit Tests** (per module)
- test_mlm_service.py
- test_wallet_service.py
- test_auth_routes.py

**Integration Tests**
- test_user_flow.py
- test_matching_income.py

**Load Tests**
- Test with 10,000 users
- Test concurrent requests

## 🚀 Deployment

**Development:**
```bash
uvicorn main:app --reload --port 8001
```

**Production:**
```bash
gunicorn main:app -w 4 -k uvicorn.workers.UvicornWorker
```

## 📝 Migration Status

✅ Core modules created
✅ Models created
✅ Services created
✅ Utilities created
✅ Main.py entry point
⏳ Routes (using old server.py temporarily)
⏳ Full migration
⏳ Test suite
⏳ Remove old server.py

## 🎯 Next Steps

1. Extract routes from server.py
2. Update imports
3. Test each route independently
4. Remove server.py
5. Add comprehensive tests
6. Add API documentation
