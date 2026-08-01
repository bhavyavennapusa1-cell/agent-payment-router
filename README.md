# RELAY — Algorand x402 Agent Payment Router

[![Live Demo](https://img.shields.io/badge/Live_Demo-Relay_x402-brightgreen?style=for-the-badge&logo=render)](https://relay-x402.onrender.com)
[![Algorand](https://img.shields.io/badge/Algorand-TestNet-blue?style=for-the-badge&logo=algorand)](https://testnet.algoexplorer.io/)
[![Protocol](https://img.shields.io/badge/Protocol-x402_HTTP_402-purple?style=for-the-badge)](https://x402.org)

**RELAY** is an autonomous, zero-trust micro-payment routing protocol designed for AI agents. Built natively for the **Algorand TestNet**, RELAY intercepts API requests, manages dynamic node bidding, enforces cryptographic payment flows via the **x402 protocol**, and secures transactions using **Atomic Group Transfers** with automated escrow refunds.

🌐 **Deployed Web Service:** [https://relay-x402.onrender.com](https://relay-x402.onrender.com)

---

## 🚀 Key Features

* **Algorand x402 Micro-Payments:** Implements the `HTTP 402 Payment Required` standard, enforcing cryptographic payment handshakes before AI inference outputs are dispatched.
* **Real-Time Bidding Market:** Decentralized providers dynamically bid on tasks based on real-time server load, margin, price, and latency matrices.
* **Atomic Group Transfers:** Bundles network fees and provider execution costs into a single atomic transaction group on Algorand for absolute security.
* **Escrow + Auto-Refund Mechanism:** Automatically triggers on-chain rollback and refunds the agent's wallet if a provider node times out or fails post-payment.
* **Cumulative Reputation System:** Tracks long-term provider reliability, dynamically incrementing score metrics on success and penalizing offline nodes.
* **Interactive Crypto Inspector:** Real-time terminal tracing raw HTTP headers, Ed25519 signatures, and Base32 transaction proofs.

---

## 📂 System Architecture

```text
projects/nexus-route/
├── frontend/
│   └── index.html             # High-octane cyber dashboard, live canvas, terminal inspector
└── backend/
    ├── server.js              # Express core application & middleware
    ├── data/
    │   └── state.js           # In-memory store for node statuses & reputation history
    ├── routes/
    │   ├── router.js          # Core POST /route endpoint logic
    │   ├── admin.js           # Node failure simulation (/kill, /revive)
    │   └── providers.js       # Active AI node registry
    └── services/
        ├── payment.js         # Atomic transfers & escrow auto-refund protocols
        └── scoring.js         # Dynamic bidding and cumulative reputation algorithms
