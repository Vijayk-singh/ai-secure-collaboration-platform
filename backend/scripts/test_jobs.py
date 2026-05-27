import sys
import time
import httpx
import uuid

BASE_URL = "http://localhost:8000/api/v1"

def run_jobs_integration_tests() -> None:
    print("=========================================================")
    print("   AI PLATFORM: BACKGROUND JOBS & DLQ INTEGRATION TESTS  ")
    print("=========================================================")

    # Generate unique emails to prevent collisions on repeat runs
    unique_suffix = str(uuid.uuid4())[:8]
    test_email = f"jobtester_{unique_suffix}@example.com"
    invitee_email = f"invitee_{unique_suffix}@example.com"

    # ---------------------------------------------------------
    # 1. REGISTER NEW USER (TRIGGERS WELCOME EMAIL TASK)
    # ---------------------------------------------------------
    print(f"\n[1] Registering unique test user '{test_email}'...")
    signup_payload = {
        "email": test_email,
        "password": "securepassword123",
        "full_name": "Job Tester"
    }
    
    res = httpx.post(f"{BASE_URL}/auth/register", json=signup_payload)
    if res.status_code == 201:
        print("    ✓ User registered successfully.")
    else:
        print(f"    ✗ User registration failed! Status: {res.status_code}")
        print("    Response:", res.json())
        sys.exit(1)

    # ---------------------------------------------------------
    # 2. AUTHENTICATE TO RETRIEVE ACCESS TOKEN
    # ---------------------------------------------------------
    print("\n[2] Authenticating test user...")
    login_data = {
        "username": test_email,
        "password": "securepassword123"
    }
    
    res = httpx.post(f"{BASE_URL}/auth/login", data=login_data)
    if res.status_code == 200:
        print("    ✓ Login successful.")
        access_token = res.json()["access_token"]
        headers = {"Authorization": f"Bearer {access_token}"}
    else:
        print(f"    ✗ Login failed! Status: {res.status_code}")
        print("    Response:", res.json())
        sys.exit(1)

    # ---------------------------------------------------------
    # 3. VERIFY INITIAL QUEUE DIAGNOSTICS
    # ---------------------------------------------------------
    print("\n[3] Querying initial jobs queue statistics `/jobs/stats`...")
    res = httpx.get(f"{BASE_URL}/jobs/stats", headers=headers)
    if res.status_code == 200:
        stats = res.json()
        print("    ✓ Initial stats retrieved:", stats)
        # The welcome email was enqueued immediately. The worker is running concurrently
        # and has likely processed it. Let's make sure stats returns successfully.
    else:
        print(f"    ✗ Failed to retrieve queue stats! Status: {res.status_code}")
        print("    Response:", res.json())
        sys.exit(1)

    # ---------------------------------------------------------
    # 4. REGISTER INVITEE & CREATE WORKSPACE & INVITE (TRIGGERS WORKSPACE INVITE EMAIL TASK)
    # ---------------------------------------------------------
    print(f"\n[4] Creating workspace and inviting member '{invitee_email}' to trigger invite email task...")
    
    # First register the invitee
    invitee_payload = {
        "email": invitee_email,
        "password": "securepassword123",
        "full_name": "Jane Invitee"
    }
    res = httpx.post(f"{BASE_URL}/auth/register", json=invitee_payload)
    if res.status_code != 201:
        print(f"    ✗ Failed to register invitee! Status: {res.status_code}")
        sys.exit(1)

    # Create workspace
    workspace_payload = {
        "name": "Secure Testing Lab",
        "description": "A workspace for async job verification"
    }
    res = httpx.post(f"{BASE_URL}/workspaces", json=workspace_payload, headers=headers)
    if res.status_code == 201:
        workspace_id = res.json()["id"]
        print(f"    ✓ Workspace created successfully. ID: {workspace_id}")
    else:
        print(f"    ✗ Workspace creation failed! Status: {res.status_code}")
        sys.exit(1)

    # Invite member to workspace
    invite_payload = {
        "email": invitee_email,
        "role": "member"
    }
    res = httpx.post(f"{BASE_URL}/workspaces/{workspace_id}/members", json=invite_payload, headers=headers)
    if res.status_code in [200, 201]:
        print("    ✓ Member added to workspace successfully. Invite email task enqueued.")
    else:
        print(f"    ✗ Failed to add member to workspace! Status: {res.status_code}")
        print("    Response:", res.json())
        sys.exit(1)

    # ---------------------------------------------------------
    # 5. TRIGGER SIMULATED RETRY / DLQ TASK
    # ---------------------------------------------------------
    print("\n[5] Enqueuing intentionally failing task via `/jobs/test-fail`...")
    res = httpx.post(f"{BASE_URL}/jobs/test-fail", headers=headers)
    if res.status_code == 202:
        task_info = res.json()
        task_id = task_info["task_id"]
        print(f"    ✓ Failure simulator task enqueued. Task ID: {task_id}")
    else:
        print(f"    ✗ Failed to enqueue simulator task! Status: {res.status_code}")
        print("    Response:", res.json())
        sys.exit(1)

    # ---------------------------------------------------------
    # 6. POLL QUEUE STATS AND VERIFY EXPONENTIAL RETRY BACKOFF
    # ---------------------------------------------------------
    print("\n[6] Polling queue diagnostics to witness retry backoff...")
    
    # We will poll for up to 15 seconds to let the task retry and fail 3 times total
    # Attempt 1: instant fail -> delayed (1s)
    # Attempt 2: fail -> delayed (2s)
    # Attempt 3: fail -> DLQ
    start_time = time.time()
    task_in_dlq = False
    
    while time.time() - start_time < 20:
        time.sleep(1.5)
        res = httpx.get(f"{BASE_URL}/jobs/stats", headers=headers)
        if res.status_code == 200:
            stats = res.json()
            print(f"    [+{round(time.time() - start_time, 1)}s] Stats: {stats}")
            if stats.get("dlq_size", 0) >= 1:
                task_in_dlq = True
                break
        else:
            print(f"    ✗ Failed to poll stats! Status: {res.status_code}")

    if not task_in_dlq:
        print("    ✗ Timeout waiting for failing task to be shunted to DLQ!")
        sys.exit(1)
        
    print("    ✓ Confirmed: Task was successfully shunted to DLQ after exhausting retries.")

    # ---------------------------------------------------------
    # 7. AUDIT DEAD-LETTER QUEUE PAYLOADS
    # ---------------------------------------------------------
    print("\n[7] Auditing Dead-Letter Queue records `/jobs/dlq`...")
    res = httpx.get(f"{BASE_URL}/jobs/dlq", headers=headers)
    if res.status_code == 200:
        dlq_list = res.json()
        print(f"    ✓ DLQ count: {len(dlq_list)}")
        
        # Search for our specific failing task
        matching_task = None
        for task in dlq_list:
            if task.get("task_id") == task_id:
                matching_task = task
                break
                
        if matching_task:
            print("    ✓ Successfully audited matching DLQ record:")
            print(f"      - Task ID:    {matching_task.get('task_id')}")
            print(f"      - Task Name:  {matching_task.get('name')}")
            print(f"      - Max Retries:{matching_task.get('max_retries')}")
            print(f"      - Retry Count:{matching_task.get('retry_count')}")
            print(f"      - Timestamp:  {matching_task.get('dlq_timestamp')}")
            print(f"      - DLQ Reason: {matching_task.get('dlq_reason')}")
            
            # Assertions for safety
            assert matching_task["name"] == "mock_failed_task"
            assert matching_task["retry_count"] == 2  # Max retries was 2
            assert "Simulated connection timeout" in matching_task["dlq_reason"]
            print("\n    ✓ ALL INTEGRATION TESTS PASSED TRIUMPHANTLY! CONGRATULATIONS!")
        else:
            print(f"    ✗ Error: Enqueued task '{task_id}' was not found in the retrieved DLQ list!")
            sys.exit(1)
    else:
        print(f"    ✗ Failed to audit DLQ! Status: {res.status_code}")
        sys.exit(1)

if __name__ == "__main__":
    try:
        run_jobs_integration_tests()
    except Exception as err:
        print(f"    ✗ Integration Test caught unexpected exception: {err}")
        sys.exit(1)
