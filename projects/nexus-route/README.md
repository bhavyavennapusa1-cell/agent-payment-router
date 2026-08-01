# RELAY — Algorand x402 Agent Payment Router (Nexus Route)

FastAPI application with `x402-avm` payment middleware and native Algorand TestNet atomic transaction group settlement.

## System Components
- **`payment_gate.py`**: Main FastAPI server, `PaymentMiddlewareASGI` integration, dynamic provider bidding engine, Algorand `PaymentTxn` atomic group settlement, and escrow refund handler.
- **`fronted_code.html`**: Single-page frontend dashboard with live pipeline visualizer, Pera Wallet integration, and real-time ledger inspector.
- **`render.yaml`**: Production deployment configuration for Render.

## Setup & Local Development

### 1. Environment Setup
Create a `.env` file at the repository root or set environment variables:
```env
AVM_ADDRESS=O7N4OJSAHPSREE57UJFOQWAKYMEKAWDU72HHFKH4M7REAQM4Z37XKPDOGE
ROUTER_MNEMONIC="your 25 word algorand testnet mnemonic phrase"
FACILITATOR_URL=https://facilitator.goplausible.xyz
ALGOD_SERVER=https://testnet-api.algonode.cloud
```

### 2. Install Dependencies & Run
```bash
python -m pip install x402-avm fastapi uvicorn python-dotenv pycryptodomex pyteal algosdk httpx
uvicorn payment_gate:app --reload --port 8000
```

### 3. Verify Endpoints
- `GET /health` -> `{"status": "ok"}`
- `POST /pay` -> `HTTP 402 Payment Required` (gated by x402)
- `POST /route` -> `HTTP 402 Payment Required` (gated by x402, executes atomic group settlement)
