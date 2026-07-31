# NexRoute - Intelligent AI Agent Routing & Payment Orchestration Service

NexRoute is a production-quality Node.js + Express backend service acting as "Google Maps for AI agent-to-agent transactions". It intelligently routes incoming AI agent requests to the optimal AI service provider based on real-time price, speed (latency), and reliability (reputation) metrics, and handles dual-sided payment settlement.

---

## 🏗 Project Architecture

```text
c:\Users\Sree Vadrevu\agent-payment-router\backend
├── server.js            # Main Express application entry point
├── routes/
│   ├── router.js        # Core POST /route endpoint & failover orchestration
│   ├── providers.js     # Mock AI service providers (Budget A, Premium B, Balanced C)
│   └── admin.js         # Kill/Revive switches, audit logs, health & failure toggles
├── services/
│   ├── scoring.js       # Dynamic provider scoring algorithm & score normalization
│   └── payment.js       # Algorand x402 payment placeholder with documented interface
├── data/
│   └── state.js         # In-memory store for providers, reputations, and audit logs
├── package.json         # Dependencies (express, cors, axios, dotenv)
├── .env                 # Environment configuration (PORT=3000)
└── README.md            # Comprehensive API reference & quick-start guide
```

---

## ⚡ Quick Start

### 1. Install Dependencies
```bash
npm install
```

### 2. Start the Server
```bash
npm start
```
The server will start on `http://localhost:3000` (or the port specified in your `.env` file).

---

## ⚙️ How It Works

### 1. Provider Profiles
- **Provider A (Budget)**: Price: `$0.001` | Avg Latency: `850ms` | Endpoint: `/provider-a/service`
- **Provider B (Fast & Premium)**: Price: `$0.005` | Avg Latency: `120ms` | Endpoint: `/provider-b/service`
- **Provider C (Balanced)**: Price: `$0.003` | Avg Latency: `400ms` | Endpoint: `/provider-c/service`

### 2. Scoring Algorithm & Optimization Modes
Providers are scored using weighted metrics:
- **`cheapest`**: `70% Price | 10% Speed | 20% Reputation`
- **`fastest`**: `10% Price | 70% Speed | 20% Reputation`
- **`balanced`**: `34% Price | 33% Speed | 33% Reputation`

Scores are normalized across active providers so the winner scores in the `80-95` range and lower choices scale proportionally for clean UI presentation.

### 3. Failover & Reputation Management
- If the highest-scoring provider fails (e.g. timeout or 500 error), NexRoute automatically flags `fallback_triggered: true`, penalizes that provider's reputation (`-0.05`), and retries the next best provider.
- Upon successful execution, the winning provider's reputation is rewarded (`+0.02`, capped at `1.0`).

---

## 💳 Payment Placeholder Integration (Algorand x402)

The file [services/payment.js](file:///c:/Users/Sree%20Vadrevu/agent-payment-router/backend/services/payment.js) contains the payment placeholder logic. 

### Teammate Contract:
To swap the placeholder for real Algorand x402 blockchain settlements, update `payProvider` to conform to:

```javascript
async function payProvider(fromAddress, toAddress, amount) {
  // Inputs:
  // - fromAddress: string (Agent wallet ID or router ID)
  // - toAddress: string (Router ID or Provider wallet ID)
  // - amount: number | string (e.g. 0.005 or "$0.005")

  // Return Shape Required:
  return {
    success: true,
    tx: "0x...",           // Transaction ID/hash
    amount: "$0.005",      // Formatted amount string
    status: "confirmed",   // Transaction status
    timestamp: Date.now()  // Unix epoch timestamp in ms
  };
}
```

---

## 📡 API Endpoint Reference & Curl Examples

### 1. Main Intelligent Routing Endpoint
**`POST /route`**

**Request Headers:** `Content-Type: application/json`

**Request Body:**
```json
{
  "query": "flight to Tokyo",
  "optimize": "fastest",
  "agentId": "agent_123"
}
```

**Curl Command (Fastest Mode):**
```bash
curl -X POST http://localhost:3000/route \
  -H "Content-Type: application/json" \
  -d "{\"query\": \"flight to Tokyo\", \"optimize\": \"fastest\", \"agentId\": \"agent_123\"}"
```

**Curl Command (Cheapest Mode):**
```bash
curl -X POST http://localhost:3000/route \
  -H "Content-Type: application/json" \
  -d "{\"query\": \"hotel in Paris\", \"optimize\": \"cheapest\", \"agentId\": \"agent_456\"}"
```

**Curl Command (Balanced Mode):**
```bash
curl -X POST http://localhost:3000/route \
  -H "Content-Type: application/json" \
  -d "{\"query\": \"summarize article\", \"optimize\": \"balanced\", \"agentId\": \"agent_789\"}"
```

**Example Successful Response:**
```json
{
  "status": "success",
  "timestamp": 1735678200000,
  "total_response_time_ms": 440,
  "chosen_provider": "Provider B (Fast & Premium)",
  "optimization_mode": "fastest",
  "fallback_triggered": false,
  "result": "Flight itinerary found for 'flight to Tokyo': Tokyo Express, Departure 08:00 AM, Economy Class ($850)",
  "providers_evaluated": [
    { "name": "Provider B", "price": "$0.005", "latency": "120ms", "score": 94, "status": "selected" },
    { "name": "Provider C", "price": "$0.003", "latency": "400ms", "score": 42, "status": "passed" },
    { "name": "Provider A", "price": "$0.001", "latency": "850ms", "score": 14, "status": "passed" }
  ],
  "payments": {
    "agent_to_router": { "tx": "0x7a3f...9b1c", "amount": "$0.005", "status": "confirmed" },
    "router_to_provider": { "tx": "0x4e2d...1a8f", "amount": "$0.005", "status": "confirmed" }
  }
}
```

---

### 2. Admin & Dashboard Endpoints

#### Get Live Provider Statuses
```bash
curl http://localhost:3000/providers
```

#### Kill a Provider (Disable for Fallback Demo)
```bash
curl -X POST http://localhost:3000/kill/provider-b
```

#### Revive a Provider
```bash
curl -X POST http://localhost:3000/revive/provider-b
```

#### View Audit Decision History Logs
```bash
curl http://localhost:3000/log
```

#### Toggle Random Provider Failure Simulation (Off/On)
```bash
curl -X POST http://localhost:3000/toggle-failures \
  -H "Content-Type: application/json" \
  -d "{\"disable\": true}"
```

#### Health Check
```bash
curl http://localhost:3000/health
```

---

## 🛠 Testing Failover in a Live Demo

1. Call `/route` with `"optimize": "fastest"`. **Provider B** will win and respond in ~120ms.
2. Execute `POST /kill/provider-b` to simulate Provider B crashing.
3. Call `/route` with `"optimize": "fastest"` again. NexRoute will automatically route to **Provider C** (the next best choice), flag `"fallback_triggered": true`, and adjust reputations seamlessly!
4. Execute `POST /revive/provider-b` to bring Provider B back online.
