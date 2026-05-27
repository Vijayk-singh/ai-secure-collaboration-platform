import sys
import httpx

BASE_URL = "http://localhost:8000/api/v1"

def register_and_login(email: str, password: str, name: str) -> str:
    """
    Helper to register a user and return their active Bearer Access Token.
    """
    signup_payload = {
        "email": email,
        "password": password,
        "full_name": name
    }
    # Register user
    httpx.post(f"{BASE_URL}/auth/register", json=signup_payload)
    
    # Login
    login_data = {
        "username": email,
        "password": password
    }
    res = httpx.post(f"{BASE_URL}/auth/login", data=login_data)
    if res.status_code == 200:
        return res.json()["access_token"]
    else:
        print(f"    ✗ Login failed for {email}! Status: {res.status_code}")
        sys.exit(1)

def run_workspace_tests() -> None:
    print("=========================================================")
    print("      AI PLATFORM: WORKSPACES & NOTES INTEGRATION TESTS  ")
    print("=========================================================")

    # ---------------------------------------------------------
    # 1. SETUP IDENTITIES
    # ---------------------------------------------------------
    print("\n[1] Enrolling system identities (Owner, Guest, Intruder)...")
    owner_token = register_and_login("owner@example.com", "ownerpassword123", "Oscar Owner")
    guest_token = register_and_login("guest@example.com", "guestpassword123", "Grace Guest")
    intruder_token = register_and_login("intruder@example.com", "intruderpassword123", "Ivan Intruder")
    
    owner_headers = {"Authorization": f"Bearer {owner_token}"}
    guest_headers = {"Authorization": f"Bearer {guest_token}"}
    intruder_headers = {"Authorization": f"Bearer {intruder_token}"}
    
    print("    ✓ All identities authenticated successfully.")

    # ---------------------------------------------------------
    # 2. WORKSPACE CREATION
    # ---------------------------------------------------------
    print("\n[2] Owner creates Workspace 'Engineering Desk'...")
    workspace_payload = {
        "name": "Engineering Desk",
        "description": "System designs and specifications"
    }
    
    res = httpx.post(f"{BASE_URL}/workspaces", json=workspace_payload, headers=owner_headers)
    if res.status_code == 201:
        workspace = res.json()
        workspace_id = workspace["id"]
        print(f"    ✓ Workspace created successfully. Assigned ID: {workspace_id}")
        print("    Data:", workspace)
    else:
        print(f"    ✗ Workspace creation failed! Status: {res.status_code}")
        sys.exit(1)

    # ---------------------------------------------------------
    # 3. LIST WORKSPACES
    # ---------------------------------------------------------
    print("\n[3] Owner lists workspaces...")
    res = httpx.get(f"{BASE_URL}/workspaces", headers=owner_headers)
    if res.status_code == 200:
        workspaces = res.json()
        print(f"    ✓ Workspace list retrieved. Count: {len(workspaces)}")
        assert any(w["id"] == workspace_id for w in workspaces)
    else:
        print(f"    ✗ Listing workspaces failed! Status: {res.status_code}")
        sys.exit(1)

    # ---------------------------------------------------------
    # 4. MEMBER INVITATION & LIST MEMBERS
    # ---------------------------------------------------------
    print("\n[4] Owner invites Guest ('guest@example.com') as a MEMBER to 'Engineering Desk'...")
    invite_payload = {
        "email": "guest@example.com",
        "role": "member"
    }
    res = httpx.post(f"{BASE_URL}/workspaces/{workspace_id}/members", json=invite_payload, headers=owner_headers)
    if res.status_code == 201:
        print("    ✓ Member added successfully.")
        print("    Membership details:", res.json())
    else:
        print(f"    ✗ Inviting member failed! Status: {res.status_code}")
        sys.exit(1)

    print("\n[5] Owner lists active workspace membership list...")
    res = httpx.get(f"{BASE_URL}/workspaces/{workspace_id}/members", headers=owner_headers)
    if res.status_code == 200:
        members = res.json()
        print(f"    ✓ Membership list retrieved. Members count: {len(members)}")
        assert any(m["user"]["email"] == "guest@example.com" for m in members)
    else:
        print(f"    ✗ Listing members failed! Status: {res.status_code}")
        sys.exit(1)

    # ---------------------------------------------------------
    # 5. ROSTER GATEKEEPING (SECURITY TEST)
    # ---------------------------------------------------------
    print("\n[6] Security Check: Intruder attempts to list workspace members...")
    res = httpx.get(f"{BASE_URL}/workspaces/{workspace_id}/members", headers=intruder_headers)
    if res.status_code == 403:
        print("    ✓ Access correctly denied (403 Forbidden). Workspace roster is secure!")
    else:
        print(f"    ✗ Error: Intruder was allowed to read members! Status: {res.status_code}")
        sys.exit(1)

    # ---------------------------------------------------------
    # 6. NOTE CREATION WITH TAGS
    # ---------------------------------------------------------
    print("\n[7] Owner creates Note 'FastAPI Deploy Guide' with Many-to-Many Tags...")
    note_payload = {
        "title": "FastAPI Deploy Guide",
        "content": "# Deployment Specs\nUse multi-stage builds and run as appuser.",
        "tags": ["#setup", "#production", "#docker"]
    }
    res = httpx.post(f"{BASE_URL}/workspaces/{workspace_id}/notes", json=note_payload, headers=owner_headers)
    if res.status_code == 201:
        note = res.json()
        note_id = note["id"]
        print(f"    ✓ Note created successfully. Note ID: {note_id}")
        print("    Assigned Tags:", [t["name"] for t in note["tags"]])
    else:
        print(f"    ✗ Note creation failed! Status: {res.status_code}")
        print(res.json())
        sys.exit(1)

    # ---------------------------------------------------------
    # 7. NOTE BOUNDARY GATEKEEPING (SECURITY TEST)
    # ---------------------------------------------------------
    print("\n[8] Member Guest reads note context...")
    res = httpx.get(f"{BASE_URL}/notes/{note_id}", headers=guest_headers)
    if res.status_code == 200:
        print("    ✓ Access granted.")
        print("    Markdown content preview:", res.json()["content"][:32], "...")
    else:
        print(f"    ✗ Access denied for guest! Status: {res.status_code}")
        sys.exit(1)

    print("\n[9] Security Check: Intruder tries to read note details...")
    res = httpx.get(f"{BASE_URL}/notes/{note_id}", headers=intruder_headers)
    if res.status_code == 403:
        print("    ✓ Access correctly denied (403 Forbidden). Note boundaries are secure!")
    else:
        print(f"    ✗ Error: Intruder allowed to view protected note! Status: {res.status_code}")
        sys.exit(1)

    # ---------------------------------------------------------
    # 8. NOTE COLLABORATIVE EDIT
    # ---------------------------------------------------------
    print("\n[10] Wiki Collaboration: Guest edits the note (modifies content & tags)...")
    edit_payload = {
        "title": "FastAPI Production Guide",
        "content": "# Production Guidelines\nThis is updated collaborative wiki content.",
        "tags": ["#setup", "#collab"]  # Rotate tags (removes #docker/#production, adds #collab)
    }
    res = httpx.put(f"{BASE_URL}/notes/{note_id}", json=edit_payload, headers=guest_headers)
    if res.status_code == 200:
        updated_note = res.json()
        print("    ✓ Collaborative update accepted.")
        print("    New title:", updated_note["title"])
        print("    New Tags: ", [t["name"] for t in updated_note["tags"]])
        assert "collab" in [t["name"] for t in updated_note["tags"]]
        assert "production" not in [t["name"] for t in updated_note["tags"]]
    else:
        print(f"    ✗ Note update failed! Status: {res.status_code}")
        sys.exit(1)

    # ---------------------------------------------------------
    # 9. NOTE DELETION PERMISSIONS
    # ---------------------------------------------------------
    print("\n[11] Security Check: Guest attempts to delete Note...")
    res = httpx.delete(f"{BASE_URL}/notes/{note_id}", headers=guest_headers)
    if res.status_code == 403:
        print("    ✓ Deletion correctly denied (403 Forbidden). Note authors/admins only!")
    else:
        print(f"    ✗ Error: Guest allowed to delete note! Status: {res.status_code}")
        sys.exit(1)

    # ---------------------------------------------------------
    # 10. PAGINATION & FILTERING
    # ---------------------------------------------------------
    print("\n[12] Owner generates 5 additional notes inside Workspace with varying tags...")
    extra_notes = [
        {"title": "Docker Setup", "content": "Docker details", "tags": ["setup", "docker"]},
        {"title": "Database Normalization Specs", "content": "Postgres indexing", "tags": ["db", "production"]},
        {"title": "Redis PubSub Spec", "content": "Realtime scaling", "tags": ["redis", "production"]},
        {"title": "Alembic Migrations", "content": "DB upgrades", "tags": ["db", "setup"]},
        {"title": "Workspace Pagination Guide", "content": "Limit offset", "tags": ["setup"]}
    ]
    for i, payload in enumerate(extra_notes, 1):
        httpx.post(f"{BASE_URL}/workspaces/{workspace_id}/notes", json=payload, headers=owner_headers)
    
    print("    ✓ 5 extra notes generated.")

    print("\n[13] Listing notes with pagination query (limit=3, offset=1)...")
    res = httpx.get(f"{BASE_URL}/workspaces/{workspace_id}/notes?limit=3&offset=1", headers=guest_headers)
    if res.status_code == 200:
        page = res.json()
        print(f"    ✓ Pagination successful. Total: {page['total']}, limit: {page['limit']}, offset: {page['offset']}")
        print(f"    Returned items count: {len(page['items'])}")
        assert page["total"] == 6  # 1 original edited + 5 extra
        assert len(page["items"]) == 3
    else:
        print(f"    ✗ Pagination query failed! Status: {res.status_code}")
        sys.exit(1)

    print("\n[14] Querying notes with Tag filtering (tag=db)...")
    res = httpx.get(f"{BASE_URL}/workspaces/{workspace_id}/notes?tag=db", headers=guest_headers)
    if res.status_code == 200:
        page = res.json()
        print(f"    ✓ Tag filtering successful. Notes tagged 'db': {len(page['items'])}")
        for n in page["items"]:
            print(f"      - Note title: '{n['title']}', Tags: {[t['name'] for t in n['tags']]}")
            assert "db" in [t["name"] for t in n["tags"]]
    else:
        print(f"    ✗ Tag filtering failed! Status: {res.status_code}")
        sys.exit(1)

    print("\n[15] Querying notes with full-text search parameters (search=Specs)...")
    res = httpx.get(f"{BASE_URL}/workspaces/{workspace_id}/notes?search=Specs", headers=guest_headers)
    if res.status_code == 200:
        page = res.json()
        print(f"    ✓ Search filtering successful. Matched count: {len(page['items'])}")
        for n in page["items"]:
            print(f"      - Matched: '{n['title']}' (content: '{n['content'][:30]}...')")
            assert "Specs" in n["title"] or "Specs" in n["content"]
    else:
        print(f"    ✗ Search filtering failed! Status: {res.status_code}")
        sys.exit(1)

    # ---------------------------------------------------------
    # 11. DELETION & VERIFICATION
    # ---------------------------------------------------------
    print("\n[16] Owner deletes Note...")
    res = httpx.delete(f"{BASE_URL}/notes/{note_id}", headers=owner_headers)
    if res.status_code == 204:
        print("    ✓ Deletion successful (204 No Content returned).")
    else:
        print(f"    ✗ Note deletion failed! Status: {res.status_code}")
        sys.exit(1)

    print("\n[17] Verifying Deletion: attempting to retrieve the deleted note...")
    res = httpx.get(f"{BASE_URL}/notes/{note_id}", headers=guest_headers)
    if res.status_code == 404:
        print("    ✓ Fetch successfully rejected with 404 Not Found. Note deleted cleanly.")
    else:
        print(f"    ✗ Error: Deleted note still retrievable! Status: {res.status_code}")
        sys.exit(1)

    print("\n=========================================================")
    print("      ✓ ALL WORKSPACES & NOTES INTEGRATION TESTS PASSED  ")
    print("=========================================================")

if __name__ == "__main__":
    run_workspace_tests()
