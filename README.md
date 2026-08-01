# RELAY — Algorand x402 Agent Payment Router

[![Live Demo](https://img.shields.io/badge/Live_Demo-Relay_x402-brightgreen?style=for-the-badge&logo=render)](https://relay-x402.onrender.com)
[![Algorand](https://img.shields.io/badge/Algorand-TestNet-blue?style=for-the-badge&logo=algorand)](https://testnet.algoexplorer.io/)
[![Protocol](https://img.shields.io/badge/Protocol-x402_HTTP_402-purple?style=for-the-badge)](https://x402.org)

**RELAY** is an autonomous, zero-trust micro-payment routing protocol designed for AI agents. Built natively for the **Algorand TestNet**, RELAY intercepts API requests, manages dynamic node bidding, enforces cryptographic payment flows via the **x402 protocol** (`x402-avm`), and secures transactions using **Atomic Group Transfers** with on-chain escrow refunds.

🌐 **Deployed Web Service:** [https://relay-x402.onrender.com](https://relay-x402.onrender.com)

---

## 🚀 Key Features

* **Algorand x402 Micro-Payments:** Implements the `HTTP 402 Payment Required` standard via `x402-avm` middleware, enforcing cryptographic payment handshakes before AI inference outputs are dispatched for both `/pay` and `/route`.
* **Real-Time Bidding Market:** Decentralized providers dynamically bid on tasks based on real-time server load, margin, price, and latency matrices.
* **Real Algorand Atomic Group Transfers:** Bundles network fee and provider execution payments into a single atomic transaction group (`algosdk.transaction.assign_group_id`) on Algorand TestNet so both legs succeed or fail together.
* **On-Chain Escrow Refund Mechanism:** Automatically triggers a real on-chain refund transaction (`PaymentTxn`) if a provider node times out or fails during execution.
* **Cumulative Reputation System:** Tracks long-term provider reliability, dynamically incrementing score metrics on success and penalizing offline nodes.
* **Interactive Crypto Inspector:** Real-time terminal tracing raw HTTP headers, Base32 transaction proofs, and verified Algorand TestNet block confirmations.

---

## 📂 System Architecture

```text
projects/nexus-route/
├── payment_gate.py            # FastAPI app & x402-avm middleware, route scoring, & atomic Algorand settlement
├── fronted_code.html          # Cyberpunk dashboard, live pipeline visualizer, Pera Wallet integration, & ledger inspector
└── render.yaml                # Render deployment specification
```

### Protocol Flow
1. **x402 Auth (`POST /route`)**: Client sends request without payment header $\rightarrow$ Server returns `HTTP 402 Payment Required` with x402 challenge header.
2. **Pera Wallet / x402 Sign**: Client signs payment payload via Pera Wallet or x402 header $\rightarrow$ Resends `POST /route` with `payment-signature` header.
3. **Verification & Bidding**: `PaymentMiddlewareASGI` validates payment via facilitator $\rightarrow$ Router scores providers on price, latency, and reputation.
4. **Atomic Group Settlement**: Router constructs 2 PaymentTxns, assigns Atomic Group ID (`assign_group_id`), signs, and broadcasts to Algorand TestNet via `send_transactions()`.
5. **Execution & Refund Safety**: Result returned to client. If provider execution fails, on-chain escrow refund (`refund_payment`) is issued automatically.

> **Note on Demo Account Configuration**: For TestNet faucet constraints, the demo uses a single funded Algorand TestNet account (`ROUTER_MNEMONIC`) to sign and settle payments on-chain.

---
## 🛠️ Tech Stack & System Architecture

### ⚡ Blockchain & Payments
* **Algorand TestNet:** High-speed settlement layer leveraging **Atomic Group Transfers** for zero-trust payments and automated escrow rollbacks.
* **x402 Protocol:** The standard for machine-to-machine micro-payments, intercepting requests with `HTTP 402 Payment Required` challenges.

### 🧠 Backend & Infrastructure
* **Python 3.12 (FastAPI):** Core API gateway that parses and verifies x402 cryptographic transaction proofs.
* **Node.js (Express):** Routing middleware managing real-time node bidding matrices and provider reputation scoring.

### 🔌 Client & Deployment
* **Pera Wallet SDK:** Non-custodial authentication enabling seamless web/mobile wallet connections.
* **Docker + Render:** Containerized runtime environment ensuring native C-library cryptographic compatibility in production.

## ⚙️ Environment Configuration

Set the following environment variables in Render dashboard or `.env`:
* `AVM_ADDRESS` — Receiving Algorand wallet address for x402 payments.
* `ROUTER_MNEMONIC` — 25-word mnemonic phrase for signing Algorand Atomic Group settlements and refunds.
* `FACILITATOR_URL` — x402 facilitator URL (e.g. `https://facilitator.goplausible.xyz`).
* `ALGOD_SERVER` — Algorand node endpoint (defaults to `https://testnet-api.algonode.cloud`).
* `DEV_MODE` — Optional boolean (`false` by default). Set to `true` only for offline developer mock testing.
