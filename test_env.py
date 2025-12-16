#!/usr/bin/env python3
"""
Test script to verify environment variable loading
"""
import os
from dotenv import load_dotenv

print("Testing environment variable loading...")
print(f"Current working directory: {os.getcwd()}")

# Check if .env file exists and read its content
env_file = ".env"
if os.path.exists(env_file):
    print(f"✅ Found {env_file}")
    with open(env_file, 'r') as f:
        content = f.read()
        print(f"File content preview:\n{content[:200]}...")
        if "JWT_SECRET_KEY" in content:
            print(f"✅ JWT_SECRET_KEY found in {env_file}")
            # Extract the line with JWT_SECRET_KEY
            for line in content.split('\n'):
                if line.startswith('JWT_SECRET_KEY'):
                    print(f"Line: {line}")
        else:
            print(f"❌ JWT_SECRET_KEY not found in {env_file}")
else:
    print(f"❌ {env_file} does not exist")

# Try loading .env from current directory
print("\nLoading .env file...")
result = load_dotenv()
print(f"load_dotenv() result: {result}")

# Check if JWT_SECRET_KEY is loaded
jwt_secret = os.getenv("JWT_SECRET_KEY")
if jwt_secret:
    print(f"✅ JWT_SECRET_KEY loaded successfully (length: {len(jwt_secret)})")
    print(f"✅ JWT_SECRET_KEY value: {jwt_secret}")
else:
    print("❌ JWT_SECRET_KEY not found in environment")

# Check other environment variables
mongo_url = os.getenv("MONGO_URL")
if mongo_url:
    print(f"✅ MONGO_URL loaded: {mongo_url[:50]}...")
else:
    print("❌ MONGO_URL not found")

# List all environment variables that start with JWT or MONGO
print("\nAll relevant environment variables:")
for key, value in os.environ.items():
    if key.startswith(('JWT', 'MONGO', 'ADMIN')):
        print(f"{key}={value[:50]}..." if len(value) > 50 else f"{key}={value}")

# Try loading with explicit path
print("\nTrying explicit path loading...")
explicit_result = load_dotenv(dotenv_path=".env", override=True)
print(f"Explicit load_dotenv() result: {explicit_result}")

jwt_secret_explicit = os.getenv("JWT_SECRET_KEY")
if jwt_secret_explicit:
    print(f"✅ JWT_SECRET_KEY after explicit load: {jwt_secret_explicit}")
else:
    print("❌ JWT_SECRET_KEY still not found after explicit load")