import asyncio
import json
import sys
import httpx
import websockets

BASE_URL = "http://localhost:8000/api/v1"
WS_URL = "ws://localhost:8000"

def register_and_login(email: str, password: str, name: str) -> str:
    """
    Helper to register a user and return their active Bearer Access Token.
    """
    signup_payload = {
        "email": email,
        "password": password,
        "full_name": name
    }
    httpx.post(f"{BASE_URL}/auth/register", json=signup_payload)
    
    login_data = {
        "username": email,
        "password": password
    }
    res = httpx.post(f"{BASE_URL}/auth/login", data=login_data)
    if res.status_code == 200:
        return res.json()["access_token"]
    else:
        print(f"✗ Login failed for {email}!")
        sys.exit(1)

async def test_chat_realtime() -> None:
    print("=========================================================")
    print("      AI PLATFORM: REALTIME CHAT INTEGRATION TESTS       ")
    print("=========================================================")
    
    # ---------------------------------------------------------
    # 1. SETUP IDENTITIES
    # ---------------------------------------------------------
    print("\n[1] Enrolling system identities (User One, User Two, Intruder)...")
    u1_token = register_and_login("chat1@example.com", "chatpassword123", "User One")
    u2_token = register_and_login("chat2@example.com", "chatpassword123", "User Two")
    intruder_token = register_and_login("chat3@example.com", "chatpassword123", "Ivan Intruder")
    
    # Dynamically resolve User Two's ID to avoid database state collision assertions
    res_me = httpx.get(f"{BASE_URL}/users/me", headers={"Authorization": f"Bearer {u2_token}"})
    u2_id = res_me.json()["id"]
    
    u1_headers = {"Authorization": f"Bearer {u1_token}"}
    print("    ✓ Identities authenticated successfully.")

    # ---------------------------------------------------------
    # 2. CREATE WORKSPACE & ROOM
    # ---------------------------------------------------------
    print("\n[2] Creating Workspace and enrolling User Two...")
    res = httpx.post(f"{BASE_URL}/workspaces", json={"name": "Chat Deck"}, headers=u1_headers)
    workspace_id = res.json()["id"]
    
    # Enroll User Two
    httpx.post(
        f"{BASE_URL}/workspaces/{workspace_id}/members", 
        json={"email": "chat2@example.com", "role": "member"}, 
        headers=u1_headers
    )
    
    print("\n[3] Creating Chat Room 'Lounge'...")
    res = httpx.post(f"{BASE_URL}/workspaces/{workspace_id}/rooms", json={"name": "Lounge"}, headers=u1_headers)
    room_id = res.json()["id"]
    print(f"    ✓ Chat room 'Lounge' created. Room ID: {room_id}")

    # ---------------------------------------------------------
    # 3. HANDSHAKE SECURITY CHECKS (EXPECTED REJECTIONS)
    # ---------------------------------------------------------
    print("\n[4] Security Check: Handshake with invalid token query parameter...")
    try:
        async with websockets.connect(f"{WS_URL}/ws/workspace/{workspace_id}/room/{room_id}?token=badtoken"):
            print("    ✗ Error: Connection was accepted, should have been rejected!")
            sys.exit(1)
    except websockets.exceptions.InvalidStatus as e:
        print(f"    ✓ Handshake correctly rejected. Status: {e.response.status_code} (Policy Violation).")

    print("\n[5] Security Check: Intruder attempts connection (not in workspace)...")
    try:
        async with websockets.connect(f"{WS_URL}/ws/workspace/{workspace_id}/room/{room_id}?token={intruder_token}"):
            print("    ✗ Error: Intruder allowed to connect!")
            sys.exit(1)
    except websockets.exceptions.InvalidStatus as e:
        print(f"    ✓ Handshake correctly rejected. Status: {e.response.status_code} (Policy Violation).")

    # ---------------------------------------------------------
    # 4. REAL-TIME BROADCASTS & ONLINE PRESENCE
    # ---------------------------------------------------------
    print("\n[6] Establishing concurrent WebSocket links for User One and User Two...")
    uri_u1 = f"{WS_URL}/ws/workspace/{workspace_id}/room/{room_id}?token={u1_token}"
    uri_u2 = f"{WS_URL}/ws/workspace/{workspace_id}/room/{room_id}?token={u2_token}"
    
    async with websockets.connect(uri_u1) as ws1, websockets.connect(uri_u2) as ws2:
        print("    ✓ Both user sockets connected.")

        # Proceed to messaging verification directly

        # ---------------------------------------------------------
        # 5. REAL-TIME MESSAGING BROADCAST
        # ---------------------------------------------------------
        print("\n[7] Sending real-time message: User One -> 'Hello Lounge!'...")
        msg_payload = {
            "type": "message",
            "content": "Hello Lounge! Distributed scaling test."
        }
        await ws1.send(json.dumps(msg_payload))

        # User Two should receive it instantly over their socket
        print("    User Two listening for broadcast...")
        msg2_recv = await ws2.recv()
        evt2_recv = json.loads(msg2_recv)
        print("    User Two received message event:", evt2_recv)
        assert evt2_recv["type"] == "message"
        assert evt2_recv["content"] == "Hello Lounge! Distributed scaling test."
        assert evt2_recv["user"]["full_name"] == "User One"

        # User One (author) also receives the broadcast
        msg1_recv = await ws1.recv()
        evt1_recv = json.loads(msg1_recv)
        assert evt1_recv["type"] == "message"
        print("    ✓ Real-time message broadcast validated successfully.")

        # ---------------------------------------------------------
        # 6. EPHEMERAL TYPING INDICATORS
        # ---------------------------------------------------------
        print("\n[8] Sending typing indicator: User Two is typing...")
        typing_payload = {
            "type": "typing",
            "is_typing": True
        }
        await ws2.send(json.dumps(typing_payload))

        # User One should receive the typing indicator instantly
        print("    User One listening for typing status...")
        msg1_typing = await ws1.recv()
        evt1_typing = json.loads(msg1_typing)
        print("    User One received typing event:", evt1_typing)
        assert evt1_typing["type"] == "typing"
        assert evt1_typing["is_typing"] is True
        assert evt1_typing["user_id"] == u2_id  # User Two ID
        print("    ✓ Ephemeral typing indicator broadcast validated successfully.")

    # ---------------------------------------------------------
    # 7. RECONNECTION CATCH-UP HISTORY
    # ---------------------------------------------------------
    print("\n[9] Checking REST Catch-up History endpoint for persisted messages...")
    res = httpx.get(f"{BASE_URL}/rooms/{room_id}/messages", headers=u1_headers)
    if res.status_code == 200:
        history = res.json()
        print(f"    ✓ Catch-up history loaded. Count: {len(history)}")
        print("    Last message details:", history[-1])
        assert history[-1]["content"] == "Hello Lounge! Distributed scaling test."
    else:
        print(f"    ✗ History fetch failed! Status: {res.status_code}")
        sys.exit(1)

    print("\n=========================================================")
    print("      ✓ ALL REALTIME CHAT INTEGRATION TESTS PASSED       ")
    print("=========================================================")

if __name__ == "__main__":
    asyncio.run(test_chat_realtime())
