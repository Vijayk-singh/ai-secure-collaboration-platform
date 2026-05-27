/* 🌐 UNIFIED SINGLE PAGE APPLICATION (SPA) CONTROLLER */

// --- 📦 STATE MANAGEMENT ENGINE ---
const state = {
    token: localStorage.getItem("accessToken") || null,
    refreshToken: localStorage.getItem("refreshToken") || null,
    user: null,
    
    // Catalogs
    workspaces: [],
    activeWorkspaceId: null,
    
    rooms: [],
    activeRoomId: null,
    
    members: [],
    onlineUsers: new Set(), // active online user IDs
    
    notes: [],
    activeNoteId: null,
    
    // WebSockets
    wsActiveRoom: null,
    wsWorkspace0: null,
    
    // Timeouts / Debouncers
    typingTimeout: null,
    autoSaveTimeout: null,
    jobsInterval: null
};

// --- 🌐 API UTILITIES & AUTOMATIC RE-AUTHENTICATION ---
async function apiFetch(url, options = {}) {
    options.headers = options.headers || {};
    
    // Inject Bearer Token
    if (state.token) {
        options.headers["Authorization"] = `Bearer ${state.token}`;
    }
    
    let response = await fetch(url, options);
    
    // If token expired (401 Unauthorized), attempt transparent token rotation
    if (response.status === 401 && state.refreshToken) {
        console.warn("Access token expired. Requesting refresh...");
        const refreshed = await attemptTokenRefresh();
        if (refreshed) {
            // Retry original request with new token
            options.headers["Authorization"] = `Bearer ${state.token}`;
            response = await fetch(url, options);
        } else {
            // Refresh failed or revoked; kick user to authentication gate
            handleLogout();
            throw new Error("Session expired. Please sign in again.");
        }
    }
    
    return response;
}

async function attemptTokenRefresh() {
    try {
        const response = await fetch("/api/v1/auth/refresh", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ refresh_token: state.refreshToken })
        });
        
        if (response.ok) {
            const data = await response.json();
            state.token = data.access_token;
            state.refreshToken = data.refresh_token;
            localStorage.setItem("accessToken", data.access_token);
            localStorage.setItem("refreshToken", data.refresh_token);
            console.log("Token refreshed successfully.");
            return true;
        }
    } catch (e) {
        console.error("Token refresh operation failed:", e);
    }
    return false;
}

// --- 🔐 AUTHENTICATION PORTAL FLOWS ---
function switchAuthTab(tab) {
    const triggerSignin = document.getElementById("trigger-signin");
    const triggerSignup = document.getElementById("trigger-signup");
    const formSignin = document.getElementById("form-signin");
    const formSignup = document.getElementById("form-signup");
    const feedback = document.getElementById("auth-feedback");
    
    feedback.style.display = "none";
    
    if (tab === "signin") {
        triggerSignin.classList.add("active");
        triggerSignup.classList.remove("active");
        formSignin.classList.remove("hidden");
        formSignup.classList.add("hidden");
    } else {
        triggerSignup.classList.add("active");
        triggerSignin.classList.remove("active");
        formSignup.classList.remove("hidden");
        formSignin.classList.add("hidden");
    }
}

async function handleSignIn(event) {
    event.preventDefault();
    const email = document.getElementById("signin-email").value;
    const password = document.getElementById("signin-password").value;
    const feedback = document.getElementById("auth-feedback");
    
    feedback.className = "feedback-msg";
    feedback.style.display = "none";
    
    // Construct OAuth2-compliant Form URL-Encoded request
    const params = new URLSearchParams();
    params.append("username", email);
    params.append("password", password);
    
    try {
        const response = await fetch("/api/v1/auth/login", {
            method: "POST",
            headers: { "Content-Type": "application/x-www-form-urlencoded" },
            body: params
        });
        
        if (!response.ok) {
            const errData = await response.json();
            throw new Error(errData.detail || "Authentication validation failed.");
        }
        
        const data = await response.json();
        state.token = data.access_token;
        state.refreshToken = data.refresh_token;
        localStorage.setItem("accessToken", data.access_token);
        localStorage.setItem("refreshToken", data.refresh_token);
        
        feedback.className = "feedback-msg success";
        feedback.textContent = "Identity Authenticated! Access granted.";
        feedback.style.display = "block";
        
        setTimeout(bootstrapDashboard, 800);
    } catch (err) {
        feedback.className = "feedback-msg error";
        feedback.textContent = err.message;
        feedback.style.display = "block";
    }
}

async function handleSignUp(event) {
    event.preventDefault();
    const name = document.getElementById("signup-name").value;
    const email = document.getElementById("signup-email").value;
    const password = document.getElementById("signup-password").value;
    const feedback = document.getElementById("auth-feedback");
    
    feedback.className = "feedback-msg";
    feedback.style.display = "none";
    
    try {
        const response = await fetch("/api/v1/auth/register", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                email: email,
                password: password,
                full_name: name
            })
        });
        
        if (!response.ok) {
            const errData = await response.json();
            throw new Error(errData.detail || "Identity registration failed.");
        }
        
        feedback.className = "feedback-msg success";
        feedback.textContent = "Identity established successfully! Please switch tabs to Sign In.";
        feedback.style.display = "block";
        
        // Auto switch tab to sign-in after quick delay
        setTimeout(() => {
            switchAuthTab("signin");
            document.getElementById("signin-email").value = email;
        }, 1500);
    } catch (err) {
        feedback.className = "feedback-msg error";
        feedback.textContent = err.message;
        feedback.style.display = "block";
    }
}

async function handleLogout() {
    // Graceful Socket Disconnections
    teardownSockets();
    
    if (state.token) {
        try {
            await apiFetch("/api/v1/auth/logout", { method: "POST" });
        } catch (e) {
            console.warn("Logout endpoint notification bypassed or failed.");
        }
    }
    
    // Clear Session Cache
    state.token = null;
    state.refreshToken = null;
    state.user = null;
    state.workspaces = [];
    state.activeWorkspaceId = null;
    state.rooms = [];
    state.activeRoomId = null;
    state.members = [];
    state.onlineUsers.clear();
    state.notes = [];
    state.activeNoteId = null;
    
    localStorage.removeItem("accessToken");
    localStorage.removeItem("refreshToken");
    
    // Clear UI state pollers
    if (state.jobsInterval) {
        clearInterval(state.jobsInterval);
        state.jobsInterval = null;
    }
    
    document.getElementById("auth-portal").classList.remove("hidden");
    document.getElementById("dashboard").classList.add("hidden");
}

function teardownSockets() {
    if (state.wsActiveRoom) {
        state.wsActiveRoom.close();
        state.wsActiveRoom = null;
    }
    if (state.wsWorkspace0) {
        state.wsWorkspace0.close();
        state.wsWorkspace0 = null;
    }
}

// --- 💻 INITIALIZATION & PROFILE RECOVERY ---
async function bootstrapDashboard() {
    document.getElementById("auth-portal").classList.add("hidden");
    document.getElementById("dashboard").classList.remove("hidden");
    
    try {
        const response = await apiFetch("/api/v1/users/me");
        if (!response.ok) throw new Error("Failed to retrieve profile context.");
        
        state.user = await response.json();
        
        // Populate profile badges
        document.getElementById("profile-name").textContent = state.user.full_name || state.user.email;
        document.getElementById("profile-role").textContent = state.user.role.toUpperCase();
        
        // Sync Workspaces lists
        await loadWorkspaces();
    } catch (err) {
        console.error("Dashboard bootstrap initialization encountered errors:", err);
        handleLogout();
    }
}

// --- 📁 SIDEBAR CONTROLLERS ---
async function loadWorkspaces() {
    try {
        const response = await apiFetch("/api/v1/workspaces");
        if (response.ok) {
            state.workspaces = await response.json();
            renderWorkspaces();
            
            // Select first workspace if present and none active
            if (state.workspaces.length > 0 && !state.activeWorkspaceId) {
                await selectWorkspace(state.workspaces[0].id);
            }
        }
    } catch (e) {
        console.error("Failed to load workspaces list:", e);
    }
}

function renderWorkspaces() {
    const list = document.getElementById("workspace-list");
    list.innerHTML = "";
    
    state.workspaces.forEach(ws => {
        const li = document.createElement("li");
        li.textContent = `📁 ${ws.name}`;
        li.className = (ws.id === state.activeWorkspaceId) ? "active" : "";
        li.onclick = () => selectWorkspace(ws.id);
        list.appendChild(li);
    });
}

async function selectWorkspace(workspaceId) {
    state.activeWorkspaceId = workspaceId;
    
    const activeWs = state.workspaces.find(ws => ws.id === workspaceId);
    if (activeWs) {
        document.getElementById("active-workspace-badge").textContent = activeWs.name;
    }
    
    renderWorkspaces();
    teardownSockets();
    
    // Refresh scopes
    await Promise.all([
        loadRooms(),
        loadMembers(),
        loadNotes()
    ]);
    
    // Establish permanent workspace-wide background presence updates loop
    connectWorkspacePresenceSocket();
    
    // Auto-select first room channel if present
    if (state.rooms.length > 0) {
        await selectRoom(state.rooms[0].id);
    } else {
        state.activeRoomId = null;
        document.getElementById("chat-placeholder").classList.remove("hidden");
        document.getElementById("chat-active").classList.add("hidden");
    }
}

async function createWorkspace() {
    const input = document.getElementById("new-workspace-name");
    const name = input.value.trim();
    if (!name) return;
    
    try {
        const response = await apiFetch("/api/v1/workspaces", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ name: name, description: "Collaborative Workspace created over dashboard UI" })
        });
        
        if (response.ok) {
            input.value = "";
            await loadWorkspaces();
            // Automatically select newly created workspace
            const newWs = state.workspaces.find(ws => ws.name === name);
            if (newWs) await selectWorkspace(newWs.id);
        }
    } catch (e) {
        console.error("Failed to create workspace:", e);
    }
}

async function loadRooms() {
    try {
        const response = await apiFetch(`/api/v1/workspaces/${state.activeWorkspaceId}/rooms`);
        if (response.ok) {
            state.rooms = await response.json();
            renderRooms();
        }
    } catch (e) {
        console.error("Failed to load workspace rooms:", e);
    }
}

function renderRooms() {
    const list = document.getElementById("room-list");
    list.innerHTML = "";
    
    state.rooms.forEach(r => {
        const li = document.createElement("li");
        li.textContent = `# ${r.name}`;
        li.className = (r.id === state.activeRoomId) ? "active" : "";
        li.onclick = () => selectRoom(r.id);
        list.appendChild(li);
    });
}

async function selectRoom(roomId) {
    state.activeRoomId = roomId;
    renderRooms();
    
    const activeRoom = state.rooms.find(r => r.id === roomId);
    if (activeRoom) {
        document.getElementById("chat-room-title").textContent = `# ${activeRoom.name}`;
        document.getElementById("chat-placeholder").classList.add("hidden");
        document.getElementById("chat-active").classList.remove("hidden");
        
        // Clear message log viewport
        document.getElementById("chat-messages").innerHTML = "<p class='placeholder-text'>Loading secure transcript history...</p>";
        
        // Fetch catch-up message logs history
        await loadChatHistory(roomId);
        
        // Establish Active Chat WebSocket connection loop
        connectActiveRoomSocket();
    }
}

async function createRoom() {
    const input = document.getElementById("new-room-name");
    const name = input.value.trim();
    if (!name) return;
    
    try {
        const response = await apiFetch(`/api/v1/workspaces/${state.activeWorkspaceId}/rooms`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ name: name })
        });
        
        if (response.ok) {
            input.value = "";
            await loadRooms();
            const newRoom = state.rooms.find(r => r.name === name);
            if (newRoom) await selectRoom(newRoom.id);
        }
    } catch (e) {
        console.error("Failed to create room:", e);
    }
}

async function loadMembers() {
    try {
        const response = await apiFetch(`/api/v1/workspaces/${state.activeWorkspaceId}/members`);
        if (response.ok) {
            state.members = await response.json();
            renderMembers();
        }
    } catch (e) {
        console.error("Failed to load workspace members list:", e);
    }
}

function renderMembers() {
    const roster = document.getElementById("member-roster");
    roster.innerHTML = "";
    
    state.members.forEach(member => {
        const user = member.user;
        const li = document.createElement("li");
        li.className = "member-item";
        
        // Online Presence indicator checks
        const isOnline = state.onlineUsers.has(user.id);
        
        const presence = document.createElement("span");
        presence.className = `presence-dot ${isOnline ? 'online' : ''}`;
        presence.title = isOnline ? "Connected securely" : "Offline";
        
        const text = document.createElement("span");
        text.textContent = user.full_name || user.email;
        
        const role = document.createElement("span");
        role.className = "member-role";
        role.textContent = member.role.toLowerCase();
        
        li.appendChild(presence);
        li.appendChild(text);
        li.appendChild(role);
        
        roster.appendChild(li);
    });
}

async function inviteMember() {
    const input = document.getElementById("invite-email");
    const email = input.value.trim();
    if (!email) return;
    
    try {
        const response = await apiFetch(`/api/v1/workspaces/${state.activeWorkspaceId}/members`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ email: email, role: "member" })
        });
        
        if (response.ok) {
            input.value = "";
            alert(`Invitation enqueued inside workers! Added member ${email} to roster.`);
            await loadMembers();
        } else {
            const err = await response.json();
            alert(`Invitation failed: ${err.detail || "User must be registered first."}`);
        }
    } catch (e) {
        console.error("Failed to invite member:", e);
    }
}

// --- 💬 REAL-TIME CHAT DECK (WEBSOCKET ENGINE) ---
function connectWorkspacePresenceSocket() {
    if (state.wsWorkspace0) state.wsWorkspace0.close();
    
    const wsProtocol = (window.location.protocol === "https:") ? "wss:" : "ws:";
    const host = window.location.host;
    const wsUrl = `${wsProtocol}//${host}/ws/workspace/${state.activeWorkspaceId}/room/0?token=${state.token}`;
    
    console.log("Establishing background Presence connection scoped to Room 0...");
    state.wsWorkspace0 = new WebSocket(wsUrl);
    
    state.wsWorkspace0.onmessage = (event) => {
        try {
            const payload = JSON.parse(event.data);
            if (payload.type === "presence") {
                const uid = parseInt(payload.user_id);
                if (payload.event === "online") {
                    state.onlineUsers.add(uid);
                } else if (payload.event === "offline") {
                    state.onlineUsers.delete(uid);
                }
                renderMembers();
            }
        } catch (e) {
            console.error("Presence WS payload parsing error:", e);
        }
    };
    
    state.wsWorkspace0.onclose = (event) => {
        if (event.code !== 1000 && state.activeWorkspaceId) {
            console.warn("Workspace Presence socket disconnected. Attempting reconnect in 3s...");
            setTimeout(connectWorkspacePresenceSocket, 3000);
        }
    };
}

function connectActiveRoomSocket() {
    if (state.wsActiveRoom) state.wsActiveRoom.close();
    
    const wsProtocol = (window.location.protocol === "https:") ? "wss:" : "ws:";
    const host = window.location.host;
    const wsUrl = `${wsProtocol}//${host}/ws/workspace/${state.activeWorkspaceId}/room/${state.activeRoomId}?token=${state.token}`;
    
    console.log(`Establishing active Room Chat connection to Room ${state.activeRoomId}...`);
    state.wsActiveRoom = new WebSocket(wsUrl);
    
    state.wsActiveRoom.onmessage = (event) => {
        try {
            const payload = JSON.parse(event.data);
            
            if (payload.type === "message") {
                appendChatMessage(payload);
            } else if (payload.type === "typing") {
                const ticker = document.getElementById("chat-typing-ticker");
                const uid = parseInt(payload.user_id);
                
                // Exclude typing notifications from current self user profile
                if (uid === state.user.id) return;
                
                if (payload.is_typing) {
                    ticker.textContent = `✍️ ${payload.full_name} is drafting a message...`;
                } else {
                    ticker.textContent = "";
                }
            }
        } catch (e) {
            console.error("Room Chat WS payload parsing error:", e);
        }
    };
    
    state.wsActiveRoom.onclose = (event) => {
        if (event.code !== 1000 && state.activeRoomId) {
            console.warn("Active Chat socket disconnected. Attempting reconnect in 3s...");
            setTimeout(connectActiveRoomSocket, 3000);
        }
    };
}

async function loadChatHistory(roomId) {
    try {
        const response = await apiFetch(`/api/v1/rooms/${roomId}/messages?limit=50`);
        if (response.ok) {
            const history = await response.json();
            const deck = document.getElementById("chat-messages");
            deck.innerHTML = "";
            
            // Messages arrive ordered from oldest to newest in list history
            history.forEach(appendChatMessage);
        }
    } catch (e) {
        console.error("Failed to load chat history:", e);
    }
}

function appendChatMessage(msg) {
    const deck = document.getElementById("chat-messages");
    
    // Clear placeholder loader text if any
    const placeholder = deck.querySelector(".placeholder-text");
    if (placeholder) placeholder.remove();
    
    const isSelf = msg.user_id === state.user.id;
    const card = document.createElement("div");
    card.className = `message-card ${isSelf ? 'self' : ''}`;
    
    const meta = document.createElement("div");
    meta.className = "msg-meta";
    
    const author = document.createElement("span");
    author.className = "msg-author";
    author.textContent = isSelf ? "You" : (msg.user.full_name || msg.user.email);
    
    const time = document.createElement("span");
    time.className = "msg-time";
    const date = new Date(msg.created_at);
    time.textContent = date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    
    meta.appendChild(author);
    meta.appendChild(time);
    
    const body = document.createElement("div");
    body.className = "msg-body";
    body.textContent = msg.content;
    
    card.appendChild(meta);
    card.appendChild(body);
    deck.appendChild(card);
    
    // Scroll viewport to bottom securely
    deck.scrollTop = deck.scrollHeight;
}

function sendChatMessage() {
    const input = document.getElementById("chat-message-input");
    const content = input.value.trim();
    if (!content || !state.wsActiveRoom) return;
    
    // Clear active typing indicator triggers instantly
    clearTimeout(state.typingTimeout);
    state.wsActiveRoom.send(JSON.stringify({ type: "typing", is_typing: false }));
    
    // Publish message payload frame
    state.wsActiveRoom.send(JSON.stringify({
        type: "message",
        content: content
    }));
    
    input.value = "";
    input.focus();
}

function handleMessageKeydown(event) {
    if (event.key === "Enter") {
        sendChatMessage();
    }
}

function handleTypingIndicator() {
    if (!state.wsActiveRoom) return;
    
    // Debounce typing status broadcast events
    if (!state.typingTimeout) {
        state.wsActiveRoom.send(JSON.stringify({ type: "typing", is_typing: true }));
    }
    
    clearTimeout(state.typingTimeout);
    state.typingTimeout = setTimeout(() => {
        state.wsActiveRoom.send(JSON.stringify({ type: "typing", is_typing: false }));
        state.typingTimeout = null;
    }, 2000);
}

// --- 📝 COLLABORATIVE NOTES SYSTEM & AUTO-SAVE EMBEDDINGS ---
async function loadNotes() {
    const searchVal = document.getElementById("note-search-input").value.trim();
    let url = `/api/v1/workspaces/${state.activeWorkspaceId}/notes?limit=100`;
    if (searchVal) url += `&search=${encodeURIComponent(searchVal)}`;
    
    try {
        const response = await apiFetch(url);
        if (response.ok) {
            const data = await response.json();
            state.notes = data.items;
            renderNotesCatalog();
        }
    } catch (e) {
        console.error("Failed to list notes:", e);
    }
}

function renderNotesCatalog() {
    const catalog = document.getElementById("notes-list");
    catalog.innerHTML = "";
    
    if (state.notes.length === 0) {
        catalog.innerHTML = "<p class='placeholder-text' style='padding:20px 0;'>No documents matching search.</p>";
        return;
    }
    
    state.notes.forEach(note => {
        const li = document.createElement("li");
        li.className = (note.id === state.activeNoteId) ? "active" : "";
        li.onclick = () => selectNote(note.id);
        
        const titleArea = document.createElement("span");
        titleArea.textContent = note.title;
        titleArea.style.fontWeight = "600";
        
        li.appendChild(titleArea);
        catalog.appendChild(li);
    });
}

async function selectNote(noteId) {
    state.activeNoteId = noteId;
    renderNotesCatalog();
    
    try {
        const response = await apiFetch(`/api/v1/notes/${noteId}`);
        if (response.ok) {
            const note = await response.json();
            
            document.getElementById("note-view-default").classList.add("hidden");
            const core = document.getElementById("note-editor-container");
            core.classList.remove("hidden");
            
            document.getElementById("current-note-id").value = note.id;
            document.getElementById("note-title").value = note.title;
            
            // Map tag relationships commas
            const tagNames = note.tags.map(t => t.name).join(", ");
            document.getElementById("note-tags").value = tagNames;
            
            document.getElementById("note-content").value = note.content || "";
            updateNotePreview();
        }
    } catch (e) {
        console.error("Failed to fetch note details:", e);
    }
}

function openNewNoteForm() {
    state.activeNoteId = null;
    renderNotesCatalog();
    
    document.getElementById("note-view-default").classList.add("hidden");
    const core = document.getElementById("note-editor-container");
    core.classList.remove("hidden");
    
    document.getElementById("current-note-id").value = "";
    document.getElementById("note-title").value = "New Document";
    document.getElementById("note-tags").value = "";
    document.getElementById("note-content").value = "";
    
    updateNotePreview();
    document.getElementById("note-title").focus();
}

async function saveNote() {
    const idVal = document.getElementById("current-note-id").value;
    const title = document.getElementById("note-title").value.trim() || "Untitled Note";
    const tagsVal = document.getElementById("note-tags").value;
    const content = document.getElementById("note-content").value;
    
    // Parse comma string into standard tags clean array
    const tags = tagsVal.split(",")
                        .map(t => t.trim())
                        .filter(t => t.length > 0);
                        
    const isNew = !idVal;
    const url = isNew ? `/api/v1/workspaces/${state.activeWorkspaceId}/notes` : `/api/v1/notes/${idVal}`;
    const method = isNew ? "POST" : "PUT";
    
    try {
        const response = await apiFetch(url, {
            method: method,
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                title: title,
                content: content,
                tags: tags
            })
        });
        
        if (response.ok) {
            const saved = await response.json();
            if (isNew) {
                state.activeNoteId = saved.id;
                document.getElementById("current-note-id").value = saved.id;
            }
            await loadNotes();
            renderNotesCatalog();
        }
    } catch (e) {
        console.error("Failed to save note:", e);
    }
}

function triggerAutoSave() {
    clearTimeout(state.autoSaveTimeout);
    state.autoSaveTimeout = setTimeout(() => {
        console.log("Auto-saving wiki changes... Vector embeddings scheduled.");
        saveNote();
    }, 1500);
}

async function deleteCurrentNote() {
    const idVal = document.getElementById("current-note-id").value;
    if (!idVal) return;
    
    if (!confirm("Are you sure you want to permanently delete this collaborative document?")) return;
    
    try {
        const response = await apiFetch(`/api/v1/notes/${idVal}`, { method: "DELETE" });
        if (response.ok) {
            state.activeNoteId = null;
            document.getElementById("note-editor-container").classList.add("hidden");
            document.getElementById("note-view-default").classList.remove("hidden");
            await loadNotes();
        }
    } catch (e) {
        console.error("Failed to delete note:", e);
    }
}

/* 📝 LIGHTWEIGHT LIVE MARKDOWN PREVIEW COMPILER */
function updateNotePreview() {
    const raw = document.getElementById("note-content").value;
    const preview = document.getElementById("note-preview");
    
    if (!raw) {
        preview.innerHTML = "<p style='color:var(--text-disabled); font-style:italic;'>Live preview window...</p>";
        return;
    }
    
    // Escape standard HTML injection tags safely
    let html = raw.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
    
    // 1. Headers Regex compilation
    html = html.replace(/^### (.*$)/gim, '<h3>$1</h3>');
    html = html.replace(/^## (.*$)/gim, '<h2>$1</h2>');
    html = html.replace(/^# (.*$)/gim, '<h1>$1</h1>');
    
    // 2. Preformatted Multi-line code blocks
    html = html.replace(/```([\s\S]*?)```/gm, '<pre><code>$1</code></pre>');
    
    // 3. Inline backtick code elements
    html = html.replace(/`([^`]+)`/gim, '<code>$1</code>');
    
    // 4. Blockquotes
    html = html.replace(/^\&gt;\s(.*$)/gim, '<blockquote>$1</blockquote>');
    
    // 5. Bold syntax
    html = html.replace(/\*\*([^*]+)\*\*/gim, '<strong>$1</strong>');
    
    // 6. Bullet Lists tags
    html = html.replace(/^\s*\-\s(.*$)/gim, '<li>$1</li>');
    html = html.replace(/(<li>.*<\/li>)/im, '<ul>$1</ul>');
    
    // 7. Standard Newlines
    html = html.replace(/\n$/gim, '<br />');
    
    preview.innerHTML = html;
}

// --- 🤖 AI COMMAND CENTER INTERACTION FLOWS ---
async function runSemanticSearch() {
    const query = document.getElementById("ai-search-query").value.trim();
    const deck = document.getElementById("ai-search-results");
    
    if (!query) return;
    deck.innerHTML = "<p class='placeholder-text'>Scanned vectors query matching in DB...</p>";
    
    try {
        const response = await apiFetch(`/api/v1/ai/search?workspace_id=${state.activeWorkspaceId}&q=${encodeURIComponent(query)}`);
        if (response.ok) {
            const data = await response.json();
            deck.innerHTML = "";
            
            if (data.results.length === 0) {
                deck.innerHTML = "<p class='placeholder-text'>No relevant contextual note chunks matched the similarity query threshold.</p>";
                return;
            }
            
            data.results.forEach(match => {
                const item = document.createElement("div");
                item.className = "semantic-match-card";
                
                const header = document.createElement("div");
                header.className = "match-header";
                
                const title = document.createElement("span");
                title.className = "match-title";
                title.textContent = `📓 ${match.note_title} (Chunk #${match.chunk_index})`;
                
                const score = document.createElement("span");
                score.className = "match-score";
                // Render similarity percentage
                score.textContent = `${(match.score * 100).toFixed(1)}% match`;
                
                header.appendChild(title);
                header.appendChild(score);
                
                const snippet = document.createElement("p");
                snippet.className = "match-snippet";
                snippet.textContent = match.content;
                
                // Add click event to go straight to matching note
                item.style.cursor = "pointer";
                item.onclick = () => jumpToNote(match.note_id);
                
                item.appendChild(header);
                item.appendChild(snippet);
                deck.appendChild(item);
            });
        }
    } catch (e) {
        deck.innerHTML = `<p class='placeholder-text' style='color:var(--color-danger);'>Search execution failure: ${e.message}</p>`;
    }
}

async function runRAGQuery() {
    const query = document.getElementById("ai-rag-query").value.trim();
    const deck = document.getElementById("ai-rag-answer-container");
    
    if (!query) return;
    deck.innerHTML = "<p class='placeholder-text'>Vectorizing vectors, context-matching notes, and generating response...</p>";
    
    try {
        const response = await apiFetch(`/api/v1/ai/rag?workspace_id=${state.activeWorkspaceId}`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ query: query })
        });
        
        if (response.ok) {
            const data = await response.json();
            deck.innerHTML = "";
            
            const body = document.createElement("div");
            body.className = "rag-answer-body";
            
            // Format answer simple markdown bold & lists
            let cleanAnswer = data.answer.replace(/\n/g, "<br/>")
                                          .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
                                          .replace(/\* (.*$)/gi, "<li>$1</li>");
            body.innerHTML = cleanAnswer;
            deck.appendChild(body);
            
            // Render Citation Pills
            if (data.sources && data.sources.length > 0) {
                const srcSection = document.createElement("div");
                srcSection.className = "rag-sources-section";
                
                const header = document.createElement("h4");
                header.textContent = "Verified Catalog Sources Utilized:";
                srcSection.appendChild(header);
                
                // deduplicate source citations by parent note id
                const seenIds = new Set();
                data.sources.forEach(src => {
                    if (seenIds.has(src.note_id)) return;
                    seenIds.add(src.note_id);
                    
                    const pill = document.createElement("span");
                    pill.className = "citation-pill";
                    pill.innerHTML = `🎓 ${src.note_title}`;
                    pill.onclick = () => jumpToNote(src.note_id);
                    srcSection.appendChild(pill);
                });
                
                deck.appendChild(srcSection);
            }
        }
    } catch (e) {
        deck.innerHTML = `<p class='placeholder-text' style='color:var(--color-danger);'>RAG query execution failure: ${e.message}</p>`;
    }
}

// Custom Citation handler linking back to notes space
function jumpToNote(noteId) {
    switchContentTab("notes");
    selectNote(noteId);
}

async function openChatSummaryModal() {
    const modal = document.getElementById("summary-modal");
    const content = document.getElementById("modal-summary-content");
    
    modal.classList.remove("hidden");
    content.innerHTML = "<p class='placeholder-text'>Synthesizing room chat logs transcript and generating summaries...</p>";
    
    try {
        const response = await apiFetch(`/api/v1/ai/summarize-chat?room_id=${state.activeRoomId}`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ limit: 50 })
        });
        
        if (response.ok) {
            const data = await response.json();
            // Format bullet lists and headers for summaries
            let cleanSummary = data.summary.replace(/\n/g, "<br/>")
                                            .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
                                            .replace(/### (.*$)/gi, "<h4>$1</h4>")
                                            .replace(/\- (.*$)/gi, "<li>$1</li>");
                                            
            content.innerHTML = `
                <div style="margin-bottom:14px; font-size:0.8rem; color:var(--text-muted)">
                    Processed context: <strong>${data.message_count} chat messages</strong>.
                </div>
                <div>${cleanSummary}</div>
            `;
        } else {
            const err = await response.json();
            content.innerHTML = `<p class='placeholder-text' style='color:var(--color-danger);'>Summary pipeline failure: ${err.detail}</p>`;
        }
    } catch (e) {
        content.innerHTML = `<p class='placeholder-text' style='color:var(--color-danger);'>Summary pipeline execution failure: ${e.message}</p>`;
    }
}

function closeChatSummaryModal() {
    document.getElementById("summary-modal").classList.add("hidden");
}

// --- ⚙️ QUEUE MONITORING CONSOLE & DIAGNOSTICS CONTROL ---
async function refreshQueueStats() {
    try {
        const response = await apiFetch("/api/v1/jobs/stats");
        if (response.ok) {
            const stats = await response.json();
            document.getElementById("queue-stat-default").textContent = stats.default_queue_size;
            document.getElementById("queue-stat-delayed").textContent = stats.delayed_queue_size;
            document.getElementById("queue-stat-dlq").textContent = stats.dlq_size;
        }
    } catch (e) {
        console.error("Queue statistics fetch encountered error:", e);
    }
}

async function loadDLQTimeline() {
    const timeline = document.getElementById("dlq-timeline");
    try {
        const response = await apiFetch("/api/v1/jobs/dlq");
        if (response.ok) {
            const failures = await response.json();
            timeline.innerHTML = "";
            
            if (failures.length === 0) {
                timeline.innerHTML = "<p class='placeholder-text'>Dead-Letter Queue is empty. No diagnostic task errors recorded.</p>";
                return;
            }
            
            failures.forEach(task => {
                const log = document.createElement("div");
                log.className = "dlq-log-card";
                
                const header = document.createElement("div");
                header.className = "dlq-log-header";
                
                const name = document.createElement("span");
                name.textContent = `❌ Task: ${task.name} (${task.id.slice(0,8)})`;
                
                const attempts = document.createElement("span");
                attempts.textContent = `Attempts: ${task.retries} / max`;
                
                header.appendChild(name);
                header.appendChild(attempts);
                
                const errBlock = document.createElement("pre");
                errBlock.className = "dlq-log-error";
                errBlock.textContent = `Error: ${task.error || "Simulated Task Failure"}\nPayload: ${JSON.stringify(task.args || {})}`;
                
                log.appendChild(header);
                log.appendChild(errBlock);
                timeline.appendChild(log);
            });
        }
    } catch (e) {
        timeline.innerHTML = `<p class='placeholder-text' style='color:var(--color-danger);'>Failed to load DLQ Logs: ${e.message}</p>`;
    }
}

async function triggerSimulatedFailure() {
    try {
        const response = await apiFetch("/api/v1/jobs/test-fail", { method: "POST" });
        if (response.ok) {
            alert("Intentionally failing task queued inside workers! Exponential retries starting now.");
            await refreshQueueStats();
            await loadDLQTimeline();
        }
    } catch (e) {
        console.error("Simulated task failure triggers encountered error:", e);
    }
}

// --- 📑 TAB CONTROL SYSTEM & CONSOLE POLLERS ---
function switchContentTab(tab) {
    const buttons = document.querySelectorAll(".content-tab-btn");
    buttons.forEach(btn => btn.classList.remove("active"));
    
    const panels = document.querySelectorAll(".tab-panel");
    panels.forEach(p => p.classList.add("hidden"));
    
    // Activate target
    document.getElementById(`tab-${tab}`).classList.add("active");
    document.getElementById(`panel-${tab}`).classList.remove("hidden");
    
    // Clear jobs monitoring poll interval when navigating away
    if (state.jobsInterval) {
        clearInterval(state.jobsInterval);
        state.jobsInterval = null;
    }
    
    // Load contextual properties
    if (tab === "notes") {
        loadNotes();
    } else if (tab === "chat") {
        if (state.activeRoomId) selectRoom(state.activeRoomId);
    } else if (tab === "jobs") {
        refreshQueueStats();
        loadDLQTimeline();
        // Setup background diagnostics metrics dashboard polling every 5s
        state.jobsInterval = setInterval(() => {
            refreshQueueStats();
            loadDLQTimeline();
        }, 5000);
    }
}

// --- 🏁 WINDOW LOAD CONTROLLER ---
window.onload = () => {
    // Determine initial state: active session vs authentication gate
    if (state.token && state.refreshToken) {
        bootstrapDashboard();
    } else {
        document.getElementById("auth-portal").classList.remove("hidden");
        document.getElementById("dashboard").classList.add("hidden");
    }
};
