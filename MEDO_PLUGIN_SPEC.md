# LabMate Backend — MeDo Custom Plugin Spec

Paste the block below into MeDo's **Plugins → Create Plugin → Paste API documentation** field.

**Before pasting**, replace these two placeholders:
- `YOUR_RENDER_URL` — e.g. `https://labmate-backend.onrender.com`
- `YOUR_API_SECRET` — the same string you set in Render's env vars

---

## 🔽 PASTE THIS INTO MEDO

Please help me create a plugin with the following details:

**Plugin Name:** LabMate Backend API

**Plugin Description:** Custom backend service for LabMate AI. Provides the Dr. Ada AI Tutor chat endpoint, RBAC role verification, user progress tracking, and audit trail logging. Powered by OpenRouter (Llama 3.3 70B) for conversational AI tutoring of lab instrument training.

**Base URL:** YOUR_RENDER_URL

**Authentication Method:** Custom header `X-API-Secret` with value `YOUR_API_SECRET`

---

### Endpoint 1: Dr. Ada AI Tutor Chat

**Request URL:** YOUR_RENDER_URL/tutor/chat
**Request Method:** POST
**Purpose:** Get Dr. Ada's next response based on the student's current lab instrument scenario and conversation history.

**Request Headers:**
- Content-Type: application/json
- X-API-Secret: YOUR_API_SECRET

**Request Parameters (JSON body):**
- instrument_name (string, required): Name of the instrument, e.g. "Microplate Reader"
- scenario_title (string, required): Name of the current scenario, e.g. "ELISA Absorbance Reading"
- step_number (integer, required): Current step number (1-indexed)
- total_steps (integer, required): Total number of steps in scenario
- step_description (string, required): Title or description of current step
- troubleshoot_mode (boolean, optional): Whether this is a troubleshooting scenario. Default false.
- hint_request_count (integer, optional): How many hints user has requested. Default 0. Tutor gives progressively more specific hints starting at 3.
- messages (array, required): Array of conversation messages. Each item has {role: "user"|"assistant", content: string}. Send last 10 messages, with newest user message last.
- user_id (string, optional): User identifier for audit logging.

**Request Example (curl):**
```
curl -X POST "YOUR_RENDER_URL/tutor/chat" \
  -H "Content-Type: application/json" \
  -H "X-API-Secret: YOUR_API_SECRET" \
  -d '{
    "instrument_name": "Microplate Reader",
    "scenario_title": "ELISA Absorbance Reading",
    "step_number": 1,
    "total_steps": 5,
    "step_description": "Select 450nm wavelength",
    "troubleshoot_mode": false,
    "hint_request_count": 0,
    "messages": [
      {"role": "user", "content": "Why do I need to use 450nm specifically?"}
    ],
    "user_id": "user-demo"
  }'
```

**Response Example:**
```
{
  "reply": "Great question! 450nm is the standard wavelength for ELISA with TMB substrate. Can you think about what happens chemically when TMB is oxidized by HRP — what color does the product become? And which wavelength would that color absorb most strongly?",
  "model": "meta-llama/llama-3.3-70b-instruct:free",
  "tokens_used": 147
}
```

**Error Response Example:**
```
{
  "detail": "LLM provider timed out"
}
```

**Error Codes:**
- 401 Unauthorized: Missing or invalid X-API-Secret header
- 502 Bad Gateway: LLM provider returned an error
- 504 Gateway Timeout: LLM provider took too long

---

### Endpoint 2: Verify User Role (RBAC)

**Request URL:** YOUR_RENDER_URL/auth/verify
**Request Method:** POST
**Purpose:** Server-side role verification beyond client-side checks.

**Request Headers:**
- Content-Type: application/json
- X-API-Secret: YOUR_API_SECRET

**Request Parameters (JSON body):**
- user_id (string, required): User identifier
- required_role (string, optional): One of "student", "instructor", "admin". Default "student".

**Request Example (curl):**
```
curl -X POST "YOUR_RENDER_URL/auth/verify" \
  -H "Content-Type: application/json" \
  -H "X-API-Secret: YOUR_API_SECRET" \
  -d '{"user_id": "user-demo", "required_role": "student"}'
```

**Response Example:**
```
{"ok": true, "user_id": "user-demo", "role": "student"}
```

---

### Endpoint 3: Get User Progress

**Request URL:** YOUR_RENDER_URL/users/{user_id}/progress
**Request Method:** GET
**Purpose:** Retrieve all scenario progress records for a user.

**Request Headers:**
- X-API-Secret: YOUR_API_SECRET

**Path Parameters:**
- user_id (string, required): User identifier

**Request Example (curl):**
```
curl -X GET "YOUR_RENDER_URL/users/user-demo/progress" \
  -H "X-API-Secret: YOUR_API_SECRET"
```

**Response Example:**
```
{
  "user_id": "user-demo",
  "progress": [
    {
      "user_id": "user-demo",
      "scenario_id": "scen-1",
      "step_index": 4,
      "completed": true,
      "score": 0.87,
      "time_spent_seconds": 420,
      "updated_at": "2026-04-19T12:30:00Z"
    }
  ],
  "count": 1
}
```

---

### Endpoint 4: Update User Progress

**Request URL:** YOUR_RENDER_URL/progress/update
**Request Method:** POST
**Purpose:** Create or update a user's progress on a specific scenario.

**Request Headers:**
- Content-Type: application/json
- X-API-Secret: YOUR_API_SECRET

**Request Parameters (JSON body):**
- user_id (string, required)
- scenario_id (string, required)
- step_index (integer, required): Current step index the user is on
- completed (boolean, optional): Whether the scenario is complete. Default false.
- score (number, optional): Quiz score 0.0-1.0
- time_spent_seconds (integer, optional): Time spent on scenario

**Request Example (curl):**
```
curl -X POST "YOUR_RENDER_URL/progress/update" \
  -H "Content-Type: application/json" \
  -H "X-API-Secret: YOUR_API_SECRET" \
  -d '{
    "user_id": "user-demo",
    "scenario_id": "scen-1",
    "step_index": 4,
    "completed": true,
    "score": 0.87,
    "time_spent_seconds": 420
  }'
```

**Response Example:**
```
{
  "ok": true,
  "progress": {
    "user_id": "user-demo",
    "scenario_id": "scen-1",
    "step_index": 4,
    "completed": true,
    "score": 0.87,
    "time_spent_seconds": 420,
    "updated_at": "2026-04-19T12:30:00Z"
  }
}
```

---

### Endpoint 5: Get Audit Log

**Request URL:** YOUR_RENDER_URL/audit/{user_id}
**Request Method:** GET
**Purpose:** Retrieve audit trail entries for a user.

**Request Headers:**
- X-API-Secret: YOUR_API_SECRET

**Path Parameters:**
- user_id (string, required)

**Query Parameters:**
- limit (integer, optional): Max entries to return. Default 50.

**Response Example:**
```
{
  "user_id": "user-demo",
  "events": [
    {
      "id": "uuid-here",
      "user_id": "user-demo",
      "event_type": "tutor_chat",
      "metadata": {"instrument": "Microplate Reader", "step": 1},
      "timestamp": "2026-04-19T12:30:00Z"
    }
  ],
  "total": 1
}
```

---

### Endpoint 6: Log Audit Event

**Request URL:** YOUR_RENDER_URL/audit/log
**Request Method:** POST
**Purpose:** Append an event to the audit log.

**Request Headers:**
- Content-Type: application/json
- X-API-Secret: YOUR_API_SECRET

**Request Parameters (JSON body):**
- user_id (string, required)
- event_type (string, required): e.g. "scenario_started", "quiz_submitted", "role_changed"
- metadata (object, optional): Any contextual key-value data

**Response Example:**
```
{
  "ok": true,
  "entry": {
    "id": "uuid",
    "user_id": "user-demo",
    "event_type": "scenario_started",
    "metadata": {"scenario_id": "scen-1"},
    "timestamp": "2026-04-19T12:30:00Z"
  }
}
```
