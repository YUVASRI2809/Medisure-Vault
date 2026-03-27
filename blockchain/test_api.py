"""
MediSure Vault - API Test Script

Quick test script to demonstrate API usage.
"""

import requests
import json

BASE_URL = "http://127.0.0.1:5000"

def test_login():
    """Test login endpoint with default admin credentials."""
    url = f"{BASE_URL}/auth/login"
    
    payload = {
        "username": "admin",
        "password": "admin123"
    }
    
    print("=" * 60)
    print("Testing POST /auth/login")
    print("=" * 60)
    print(f"URL: {url}")
    print(f"Payload: {json.dumps(payload, indent=2)}")
    print()
    
    try:
        response = requests.post(url, json=payload)
        
        print(f"Status Code: {response.status_code}")
        print(f"Response: {json.dumps(response.json(), indent=2)}")
        print("=" * 60)
        
        return response.json()
    except requests.exceptions.ConnectionError:
        print("ERROR: Cannot connect to server. Make sure the app is running on http://127.0.0.1:5000")
        print("Run: python app.py")
        return None
    except Exception as e:
        print(f"ERROR: {e}")
        return None


def test_register():
    """Test user registration."""
    url = f"{BASE_URL}/auth/register"
    
    payload = {
        "username": "test_doctor",
        "password": "TestPass123",
        "email": "doctor@test.com",
        "full_name": "Dr. Test Doctor",
        "role": "DOCTOR",
        "license_number": "MD123456"
    }
    
    print("\n" + "=" * 60)
    print("Testing POST /auth/register")
    print("=" * 60)
    print(f"URL: {url}")
    print(f"Payload: {json.dumps(payload, indent=2)}")
    print()
    
    try:
        response = requests.post(url, json=payload)
        
        print(f"Status Code: {response.status_code}")
        print(f"Response: {json.dumps(response.json(), indent=2)}")
        print("=" * 60)
        
        return response.json()
    except Exception as e:
        print(f"ERROR: {e}")
        return None


def test_health_check():
    """Test health check endpoint."""
    url = f"{BASE_URL}/health"
    
    print("\n" + "=" * 60)
    print("Testing GET /health")
    print("=" * 60)
    print(f"URL: {url}")
    print()
    
    try:
        response = requests.get(url)
        
        print(f"Status Code: {response.status_code}")
        print(f"Response: {json.dumps(response.json(), indent=2)}")
        print("=" * 60)
        
        return response.json()
    except Exception as e:
        print(f"ERROR: {e}")
        return None


if __name__ == "__main__":
    print("\n🏥 MediSure Vault - API Testing\n")
    
    # Test health check first
    health = test_health_check()
    
    # Test login with default admin
    login_result = test_login()
    
    # Test registration
    register_result = test_register()
    
    print("\n✅ API tests completed!")
    print("\nNext steps:")
    print("1. Use the session cookie from login for authenticated requests")
    print("2. Create prescriptions with POST /prescriptions/create")
    print("3. Generate access tokens for patients")
    print("4. Test the complete prescription lifecycle")
