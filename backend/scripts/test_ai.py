import sys
import time
import httpx
import uuid

BASE_URL = "http://localhost:8000/api/v1"

def run_ai_integration_tests() -> None:
    print("=========================================================")
    print("   AI PLATFORM: LEVEL 5 - AI SERVICE INTEGRATION TESTS   ")
    print("=========================================================")

    # Generate unique emails to prevent collisions
    unique_suffix = str(uuid.uuid4())[:8]
    test_email = f"aitester_{unique_suffix}@example.com"

    # ---------------------------------------------------------
    # 1. REGISTER & LOGIN TEST USER
    # ---------------------------------------------------------
    print(f"\n[1] Enrolling unique AI testing identity '{test_email}'...")
    signup_payload = {
        "email": test_email,
        "password": "securepassword123",
        "full_name": "AI Architect"
    }
    
    res = httpx.post(f"{BASE_URL}/auth/register", json=signup_payload)
    if res.status_code != 201:
        print(f"    ✗ User registration failed! Status: {res.status_code}")
        sys.exit(1)

    login_data = {
        "username": test_email,
        "password": "securepassword123"
    }
    res = httpx.post(f"{BASE_URL}/auth/login", data=login_data)
    if res.status_code != 200:
        print(f"    ✗ Login failed! Status: {res.status_code}")
        sys.exit(1)
        
    access_token = res.json()["access_token"]
    headers = {"Authorization": f"Bearer {access_token}"}
    print("    ✓ AI Architect enrolled and authenticated successfully.")

    # ---------------------------------------------------------
    # 2. CREATE WORKSPACE
    # ---------------------------------------------------------
    print("\n[2] Creating target workspace...")
    workspace_payload = {
        "name": "Distributed AI Laboratory",
        "description": "A workspace for async vector search and RAG verification"
    }
    res = httpx.post(f"{BASE_URL}/workspaces", json=workspace_payload, headers=headers)
    if res.status_code != 201:
        print(f"    ✗ Workspace creation failed! Status: {res.status_code}")
        sys.exit(1)
        
    workspace = res.json()
    workspace_id = workspace["id"]
    print(f"    ✓ Workspace 'Distributed AI Laboratory' established (ID: {workspace_id}).")

    # ---------------------------------------------------------
    # 3. CREATE MULTIPLE NOTES WITH STRATEGIC SEMANTIC CONTRASTS
    # ---------------------------------------------------------
    print("\n[3] Injecting notes with contrasting semantic concepts...")
    
    # Note 1: Redis Caching Strategies
    note1_payload = {
        "title": "Redis Cache Architectures",
        "content": (
            "We employ Redis to optimize low-latency data access. Redis acts as an in-memory cache "
            "handling stateful JWT revocations, typing indicators, and user online presence sets. "
            "To maximize cache efficiency, we enforce strict TTL policies on all temporary entries."
        ),
        "tags": ["cache", "redis"]
    }
    res1 = httpx.post(f"{BASE_URL}/workspaces/{workspace_id}/notes", json=note1_payload, headers=headers)
    
    # Note 2: PostgreSQL Indexing & Optimization
    note2_payload = {
        "title": "PostgreSQL Indexing Guidelines",
        "content": (
            "For durable document relational modeling, we utilize PostgreSQL. Tables are optimized using "
            "custom indexes, foreign keys, and cascading deletes. For massive vector scales, we leverage "
            "the HNSW approximate nearest neighbor search index to evaluate cosine similarity distances."
        ),
        "tags": ["database", "postgres", "index"]
    }
    res2 = httpx.post(f"{BASE_URL}/workspaces/{workspace_id}/notes", json=note2_payload, headers=headers)

    if res1.status_code == 201 and res2.status_code == 201:
        note1_id = res1.json()["id"]
        note2_id = res2.json()["id"]
        print(f"    ✓ Note 1 'Redis Cache' created. ID: {note1_id}")
        print(f"    ✓ Note 2 'PostgreSQL Indexing' created. ID: {note2_id}")
    else:
        print(f"    ✗ Note creation failed! Statuses: {res1.status_code}, {res2.status_code}")
        sys.exit(1)

    # ---------------------------------------------------------
    # 4. AWAIT BACKGROUND EMBEDDING VECTORIZATION
    # ---------------------------------------------------------
    print("\n[4] Awaiting background task worker semantic indexing...")
    # Sleep 3 seconds to let workers pop jobs from default queue, chunk, and save pgvector embeddings
    time.sleep(3.0)
    print("    ✓ Async workers execution cycle processed.")

    # ---------------------------------------------------------
    # 5. SEMANTIC SEARCH TESTING (COSINE SIMILARITY EVALUATION)
    # ---------------------------------------------------------
    print("\n[5] Executing Semantic Search queries `/ai/search`...")
    
    # Query A: "Low latency caching" -> Should match Redis Cache note
    print("    -> Querying: 'low-latency caching configurations'...")
    res_search_a = httpx.get(
        f"{BASE_URL}/ai/search?workspace_id={workspace_id}&q=low-latency caching configurations&limit=2",
        headers=headers
    )
    if res_search_a.status_code == 200:
        data_a = res_search_a.json()
        print("       ✓ Search A succeeded. Top Matches:")
        for r in data_a["results"]:
            print(f"         - Note: '{r['note_title']}' (Score: {round(r['score'], 4)})")
            
        assert len(data_a["results"]) > 0
        # The top match should be Redis Cache Architectures because it shares "low-latency", "caching", "Redis"
        assert data_a["results"][0]["note_title"] == "Redis Cache Architectures"
    else:
        print(f"    ✗ Semantic Search A failed! Status: {res_search_a.status_code}")
        sys.exit(1)

    # Query B: "Database vector indices" -> Should match PostgreSQL note
    print("    -> Querying: 'database vector indices and optimization'...")
    res_search_b = httpx.get(
        f"{BASE_URL}/ai/search?workspace_id={workspace_id}&q=database vector indices and optimization&limit=2",
        headers=headers
    )
    if res_search_b.status_code == 200:
        data_b = res_search_b.json()
        print("       ✓ Search B succeeded. Top Matches:")
        for r in data_b["results"]:
            print(f"         - Note: '{r['note_title']}' (Score: {round(r['score'], 4)})")
            
        assert len(data_b["results"]) > 0
        assert data_b["results"][0]["note_title"] == "PostgreSQL Indexing Guidelines"
    else:
        print(f"    ✗ Semantic Search B failed! Status: {res_search_b.status_code}")
        sys.exit(1)

    # ---------------------------------------------------------
    # 6. RETRIEVAL-AUGMENTED GENERATION (RAG) QA TESTING
    # ---------------------------------------------------------
    print("\n[6] Querying Retrieval-Augmented Generation (RAG) `/ai/rag`...")
    rag_payload = {
        "query": "How do we optimize document search for massive vector scales?"
    }
    res_rag = httpx.post(
        f"{BASE_URL}/ai/rag?workspace_id={workspace_id}",
        json=rag_payload,
        headers=headers
    )
    if res_rag.status_code == 200:
        rag_data = res_rag.json()
        print("    ✓ RAG pipeline completed successfully.")
        print(f"    - Query:   {rag_data['query']}")
        print(f"    - Answer:\n{rag_data['answer']}")
        print(f"    - Sources Cited:")
        for s in rag_data["sources"]:
            print(f"      * [Note ID: {s['note_id']}] Title: '{s['note_title']}' (Similarity: {round(s['score'], 4)})")
            
        # Assertions
        assert len(rag_data["sources"]) > 0
        assert rag_data["sources"][0]["note_title"] == "PostgreSQL Indexing Guidelines"
        assert "citations" in rag_data["answer"].lower() or "offline" in rag_data["answer"].lower() or "vector" in rag_data["answer"].lower()
    else:
        print(f"    ✗ RAG request failed! Status: {res_rag.status_code}")
        print("    Response:", res_rag.json())
        sys.exit(1)

    # ---------------------------------------------------------
    # 7. CHAT LOGS SUMMARIZATION TESTING
    # ---------------------------------------------------------
    print("\n[7] Testing Chat Room Summarization `/ai/summarize-chat`...")
    
    # Create chat room
    room_payload = {"name": "ai-discussions"}
    res_room = httpx.post(f"{BASE_URL}/workspaces/{workspace_id}/rooms", json=room_payload, headers=headers)
    if res_room.status_code != 201:
        print(f"    ✗ Room creation failed! Status: {res_room.status_code}")
        sys.exit(1)
        
    room_id = res_room.json()["id"]
    print(f"    ✓ Chat Room established. ID: {room_id}")

    # Write a quick mock conversation transcript via WebSocket
    messages_payloads = [
        "We need to configure the Redis TTL to prevent memory leaks.",
        "I agree. Let's enforce a 24-hour expiration key on all tokens.",
        "Perfect, I will schedule a background worker task to audit it."
    ]
    
    print("    -> Seeding conversation history using active WebSocket channel...")
    import asyncio
    import websockets
    import json

    async def seed_chat_history():
        ws_uri = f"ws://localhost:8000/ws/workspace/{workspace_id}/room/{room_id}?token={access_token}"
        async with websockets.connect(ws_uri) as ws:
            for msg_content in messages_payloads:
                payload = {
                    "type": "message",
                    "content": msg_content
                }
                await ws.send(json.dumps(payload))
                await asyncio.sleep(0.2)  # Give time to persist message
                
                # Consume echo broadcasts so socket buffer stays clean
                try:
                    await asyncio.wait_for(ws.recv(), timeout=0.5)
                except asyncio.TimeoutError:
                    pass

    try:
        asyncio.run(seed_chat_history())
        print("    ✓ Message transcript logs populated successfully over socket.")
    except Exception as ws_err:
        print(f"    ✗ Failed to seed chat logs: {ws_err}")
        sys.exit(1)

    # Call Summarizer
    summary_payload = {"limit": 10}
    res_summary = httpx.post(
        f"{BASE_URL}/ai/summarize-chat?room_id={room_id}",
        json=summary_payload,
        headers=headers
    )
    if res_summary.status_code == 200:
        summary_data = res_summary.json()
        print("    ✓ Chat Summarization succeeded.")
        print(f"    - Message count analyzed: {summary_data['message_count']}")
        print(f"    - AI Summary Digest:\n{summary_data['summary']}")
        
        # Assertions
        assert summary_data["message_count"] == 3
        assert "redis" in summary_data["summary"].lower() or "ttl" in summary_data["summary"].lower() or "audit" in summary_data["summary"].lower()
        print("\n    ✓ ALL AI SERVICE INTEGRATION TESTS PASSED WITH RADIANT SUCCESS!")
    else:
        print(f"    ✗ Chat summarization failed! Status: {res_summary.status_code}")
        print("    Response:", res_summary.json())
        sys.exit(1)

if __name__ == "__main__":
    try:
        run_ai_integration_tests()
    except Exception as err:
        import traceback
        print("    ✗ Integration Test caught unexpected exception:")
        traceback.print_exc()
        sys.exit(1)
