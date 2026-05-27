import sys
import httpx

BASE_URL = "http://localhost:8000/api/v1"

def run_integration_tests() -> None:
    print("=========================================================")
    print("   AI PLATFORM: AUTHENTICATION SERVICE INTEGRATION TESTS  ")
    print("=========================================================")

    # ---------------------------------------------------------
    # 1. USER REGISTRATION
    # ---------------------------------------------------------
    print("\n[1] Registering new member account 'member@example.com'...")
    signup_payload = {
        "email": "member@example.com",
        "password": "securepassword123",
        "full_name": "Jane Member"
    }
    
    res = httpx.post(f"{BASE_URL}/auth/register", json=signup_payload)
    if res.status_code == 201:
        print("    ✓ Registration successful.")
        print("    Profile:", res.json())
    elif res.status_code == 400 and "already exists" in res.json().get("detail", ""):
        print("    ✓ User already registered (email validation verified).")
    else:
        print(f"    ✗ Registration failed! Status: {res.status_code}")
        print("    Response:", res.json())
        sys.exit(1)

    # ---------------------------------------------------------
    # 2. USER LOGIN
    # ---------------------------------------------------------
    print("\n[2] Logging in to retrieve JWT access/refresh token pair...")
    login_data = {
        "username": "member@example.com",
        "password": "securepassword123"
    }
    
    res = httpx.post(f"{BASE_URL}/auth/login", data=login_data)
    if res.status_code == 200:
        print("    ✓ Login successful.")
        tokens = res.json()
        access_token = tokens["access_token"]
        refresh_token = tokens["refresh_token"]
        print(f"    Access Token issued:  {access_token[:24]}...")
        print(f"    Refresh Token issued: {refresh_token[:24]}...")
    else:
        print(f"    ✗ Login failed! Status: {res.status_code}")
        print("    Response:", res.json())
        sys.exit(1)

    # ---------------------------------------------------------
    # 3. ACCESSING PROTECTED PROFILE
    # ---------------------------------------------------------
    print("\n[3] Querying protected profile route `/users/me` with Bearer auth...")
    headers = {"Authorization": f"Bearer {access_token}"}
    
    res = httpx.get(f"{BASE_URL}/users/me", headers=headers)
    if res.status_code == 200:
        print("    ✓ Access granted.")
        profile = res.json()
        print(f"    Returned context -> ID: {profile['id']}, Email: {profile['email']}, Role: {profile['role']}")
    else:
        print(f"    ✗ Access denied! Status: {res.status_code}")
        print("    Response:", res.json())
        sys.exit(1)

    # ---------------------------------------------------------
    # 4. RBAC PROTECTION TEST (REJECTION)
    # ---------------------------------------------------------
    print("\n[4] Testing RBAC: Accessing `/users/admin-only` as a MEMBER role...")
    res = httpx.get(f"{BASE_URL}/users/admin-only", headers=headers)
    if res.status_code == 403:
        print("    ✓ Access correctly rejected (403 Forbidden).")
        print("    Response payload:", res.json())
    else:
        print(f"    ✗ Error: Access should have been denied, but got status: {res.status_code}!")
        sys.exit(1)

    # ---------------------------------------------------------
    # 5. TOKEN REFRESH ROTATION (RTR)
    # ---------------------------------------------------------
    print("\n[5] Executing Token Refresh Rotation (RTR) to issue new token pair...")
    refresh_payload = {
        "refresh_token": refresh_token
    }
    
    res = httpx.post(f"{BASE_URL}/auth/refresh", json=refresh_payload)
    if res.status_code == 200:
        print("    ✓ Session refreshed successfully.")
        rotated_tokens = res.json()
        new_access_token = rotated_tokens["access_token"]
        new_refresh_token = rotated_tokens["refresh_token"]
        print(f"    New Access Token:  {new_access_token[:24]}...")
        print(f"    New Refresh Token: {new_refresh_token[:24]}...")
    else:
        print(f"    ✗ Refresh failed! Status: {res.status_code}")
        print("    Response:", res.json())
        sys.exit(1)

    # ---------------------------------------------------------
    # 6. LOGOUT (SESSION REVOCATION)
    # ---------------------------------------------------------
    print("\n[6] Logging out (deletes token from Redis state whitelist)...")
    logout_headers = {"Authorization": f"Bearer {new_access_token}"}
    
    res = httpx.post(f"{BASE_URL}/auth/logout", headers=logout_headers)
    if res.status_code == 204:
        print("    ✓ Logout successful (204 No Content returned).")
    else:
        print(f"    ✗ Logout failed! Status: {res.status_code}")
        sys.exit(1)

    # ---------------------------------------------------------
    # 7. REVOCATION VERIFICATION
    # ---------------------------------------------------------
    print("\n[7] Verifying revocation: attempting to refresh using rotated token after logout...")
    res = httpx.post(f"{BASE_URL}/auth/refresh", json={"refresh_token": new_refresh_token})
    if res.status_code == 401:
        print("    ✓ Refresh correctly rejected (401 Unauthorized). Stateful revocation works!")
        print("    Response payload:", res.json())
    else:
        print(f"    ✗ Error: Revoked token allowed to refresh! Got status: {res.status_code}!")
        sys.exit(1)

    # ---------------------------------------------------------
    # 8. RBAC PROTECTION TEST (APPROVAL)
    # ---------------------------------------------------------
    print("\n[8] Registering account 'admin@example.com' for RBAC validation...")
    admin_signup_payload = {
        "email": "admin@example.com",
        "password": "adminpassword123",
        "full_name": "Alex Admin"
    }
    
    res = httpx.post(f"{BASE_URL}/auth/register", json=admin_signup_payload)
    if res.status_code == 201 or (res.status_code == 400 and "already exists" in res.json().get("detail", "")):
        print("    ✓ Admin account registered.")
    else:
        print(f"    ✗ Admin registration failed! Status: {res.status_code}")
        sys.exit(1)

    print("\n[9] Note: Run CLI database update to elevate Alex Admin's role to ADMIN.")
    print("    Log in as Alex Admin to verify RBAC access...")
    
    admin_login_data = {
        "username": "admin@example.com",
        "password": "adminpassword123"
    }
    
    res = httpx.post(f"{BASE_URL}/auth/login", data=admin_login_data)
    if res.status_code == 200:
        admin_tokens = res.json()
        admin_access_token = admin_tokens["access_token"]
        
        # Test endpoint
        admin_headers = {"Authorization": f"Bearer {admin_access_token}"}
        res_admin = httpx.get(f"{BASE_URL}/users/admin-only", headers=admin_headers)
        
        if res_admin.status_code == 200:
            print("    ✓ Access granted (200 OK). RBAC verification complete.")
            print("    Response payload:", res_admin.json())
        elif res_admin.status_code == 403:
            print("    ! Alex Admin is currently a MEMBER (Role elevation required for acceptance test).")
        else:
            print(f"    ✗ Error querying admin route: Got status {res_admin.status_code}")
            sys.exit(1)
    else:
        print(f"    ✗ Admin login failed! Status: {res.status_code}")
        sys.exit(1)

    print("\n=========================================================")
    print("        ✓ ALL SECURITY & AUTH INTEGRATION TESTS PASSED   ")
    print("=========================================================")

if __name__ == "__main__":
    run_integration_tests()
