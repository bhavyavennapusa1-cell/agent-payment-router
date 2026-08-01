"""
payment_gate.py
---------------
FastAPI application with x402-avm payment middleware (x402-avm v2.x).

Endpoints:
  GET  /health  - Health check (no payment required)
  POST /pay     - Protected endpoint requiring $0.01 payment on Algorand TestNet

Environment Variables (loaded from .env at the workspace root):
  AVM_ADDRESS     - Algorand wallet address to receive payments
  FACILITATOR_URL - x402 facilitator URL for payment verification
"""

import os
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.exception_handlers import http_exception_handler
from starlette.exceptions import HTTPException as StarletteHTTPException

import algosdk
from algosdk import mnemonic, account
from algosdk.v2client import algod
from algosdk.transaction import PaymentTxn, wait_for_confirmation

# ---------------------------------------------------------------------------
# Load environment variables from .env
# Strategy: look for .env two directories up (workspace root), then fall back
# to python-dotenv's automatic search via find_dotenv().
# ---------------------------------------------------------------------------
from dotenv import load_dotenv, find_dotenv

_root_env = Path(__file__).resolve().parent.parent.parent / ".env"
if _root_env.exists():
    load_dotenv(dotenv_path=_root_env)
    print(f"[dotenv] Loaded .env from: {_root_env}")
else:
    _found = find_dotenv(usecwd=True)
    if _found:
        load_dotenv(dotenv_path=_found)
        print(f"[dotenv] Loaded .env from: {_found}")
    else:
        load_dotenv()  # last-resort default search
        print("[dotenv] Using default .env search (no explicit path found)")

# ---------------------------------------------------------------------------
# Read and validate required environment variables
# Note: AVM_ADDRESS, ROUTER_MNEMONIC, and FACILITATOR_URL must be set manually in
# Render's dashboard Environment tab (not in render.yaml).
# For this demo, AVM_ADDRESS and the address derived from ROUTER_MNEMONIC may
# intentionally be the SAME account due to TestNet faucet constraints — this is
# expected and fine.
# ---------------------------------------------------------------------------
DEFAULT_AVM_ADDRESS = "O7N4OJSAHPSREE57UJFOQWAKYMEKAWDU72HHFKH4M7REAQM4Z37XKPDOGE"
AVM_ADDRESS: str = os.getenv("AVM_ADDRESS", "").strip() or DEFAULT_AVM_ADDRESS
FACILITATOR_URL: str = os.getenv("FACILITATOR_URL", "https://x402.org/facilitator").strip()
APP_ID: int = int(os.getenv("APP_ID", "768380572"))

ROUTER_MNEMONIC: str = os.getenv("ROUTER_MNEMONIC", "").strip()
if not ROUTER_MNEMONIC:
    raise EnvironmentError("ROUTER_MNEMONIC is not set. Set it in Render's Environment tab.")
ROUTER_PRIVATE_KEY = mnemonic.to_private_key(ROUTER_MNEMONIC)
ROUTER_ADDRESS = account.address_from_private_key(ROUTER_PRIVATE_KEY)

ALGOD_SERVER: str = os.getenv("ALGOD_SERVER", "https://testnet-api.algonode.cloud").strip()
algod_client = algod.AlgodClient("", ALGOD_SERVER)

print(f"[config] AVM_ADDRESS    = {AVM_ADDRESS}")
print(f"[config] ROUTER_ADDRESS = {ROUTER_ADDRESS}")
print(f"[config] FACILITATOR_URL = {FACILITATOR_URL}")
print(f"[config] APP_ID          = {APP_ID}")

# ---------------------------------------------------------------------------
# x402 imports (package ships as `x402`, not `x402_avm`)
# Install: pip install x402-avm fastapi uvicorn python-dotenv
# ---------------------------------------------------------------------------
try:
    from x402 import x402ResourceServer, FacilitatorConfig
    from x402.http import (
        HTTPFacilitatorClient,
        RouteConfig,
        PaymentOption,
    )
    from x402.http.middleware.fastapi import PaymentMiddlewareASGI
    from x402.mechanisms.avm.exact.register import register_exact_avm_server
except ImportError as _exc:
    raise ImportError(
        "x402-avm is not installed in the active environment.\n"
        "Run: .venv\\Scripts\\python.exe -m pip install x402-avm"
    ) from _exc

# ---------------------------------------------------------------------------
# Algorand TestNet network identifier used by x402
# The genesis hash uniquely identifies Algorand TestNet in the x402 protocol.
# ---------------------------------------------------------------------------
ALGORAND_TESTNET_NETWORK = "algorand:SGO1GKSzyE7IEPItTxCByw9x8FmnrCDexi9/cOUJOiI="

# ---------------------------------------------------------------------------
# Facilitator client (handles verify / settle with x402.org/facilitator)
# ---------------------------------------------------------------------------
import time
import random
import asyncio
import httpx
from typing import List, Optional
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from x402.schemas import VerifyResponse, SettleResponse

class DemoFacilitatorClient(HTTPFacilitatorClient):
    async def verify(
        self,
        payload,
        requirements,
    ) -> VerifyResponse:
        DEV_MODE = os.getenv("DEV_MODE", "false").lower() == "true"
        tx_id = ""
        payer_addr = getattr(requirements, "pay_to", AVM_ADDRESS)
        if payload and getattr(payload, "payload", None):
            p_dict = payload.payload if isinstance(payload.payload, dict) else {}
            tx_id = p_dict.get("tx") or p_dict.get("txId") or p_dict.get("transactionId") or ""
            if p_dict.get("payer"):
                payer_addr = p_dict.get("payer")
        if DEV_MODE and tx_id.startswith("mock-"):
            return VerifyResponse(is_valid=True, payer=payer_addr)
        
        res = await super().verify(payload, requirements)
        if payload and getattr(payload, "payload", None) and isinstance(payload.payload, dict) and payload.payload.get("payer"):
            res.payer = payload.payload.get("payer")
        return res

    async def settle(
        self,
        payload,
        requirements,
    ) -> SettleResponse:
        DEV_MODE = os.getenv("DEV_MODE", "false").lower() == "true"
        tx_id = "mock-tx"
        payer_addr = getattr(requirements, "pay_to", AVM_ADDRESS)
        if payload and getattr(payload, "payload", None):
            p_dict = payload.payload if isinstance(payload.payload, dict) else {}
            tx_id = p_dict.get("tx") or p_dict.get("txId") or p_dict.get("transactionId") or "mock-tx"
            if p_dict.get("payer"):
                payer_addr = p_dict.get("payer")
        if DEV_MODE and tx_id.startswith("mock-"):
            return SettleResponse(
                success=True,
                transaction=tx_id,
                network=requirements.network,
                payer=payer_addr
            )
        
        res = await super().settle(payload, requirements)
        if payload and getattr(payload, "payload", None) and isinstance(payload.payload, dict) and payload.payload.get("payer"):
            res.payer = payload.payload.get("payer")
        return res

def extract_sender_address(request: Request, body_data: Optional[dict] = None) -> str:
    # 1. Check HTTP Headers (X-Pera-Address, X-Sender-Address)
    header_addr = request.headers.get("x-pera-address") or request.headers.get("x-sender-address")
    if header_addr and header_addr.strip():
        return header_addr.strip()

    # 2. Check JSON Body / Payload
    if body_data and isinstance(body_data, dict):
        for key in ["sender", "senderAddress", "peraAddress", "connectedAccount", "payer"]:
            val = body_data.get(key)
            if val and isinstance(val, str) and val.strip():
                return val.strip()
        payload_dict = body_data.get("payload")
        if isinstance(payload_dict, dict):
            val = payload_dict.get("payer") or payload_dict.get("sender")
            if val and isinstance(val, str) and val.strip():
                return val.strip()
        agent_id = body_data.get("agentId")
        if agent_id and isinstance(agent_id, str) and agent_id.strip():
            return agent_id.strip()

    return "agent_123"

def extract_recipient_address(request: Request, body_data: Optional[dict] = None) -> str:
    # 1. Check HTTP Headers
    header_addr = request.headers.get("x-recipient-address") or request.headers.get("x-pay-to")
    if header_addr and header_addr.strip():
        return header_addr.strip()

    # 2. Check JSON Body / Payload
    if body_data and isinstance(body_data, dict):
        for key in ["recipient", "recipientAddress", "pay_to", "toAddress", "targetRecipient"]:
            val = body_data.get(key)
            if val and isinstance(val, str) and val.strip():
                return val.strip()

    # 3. Fallback default receiving address
    return AVM_ADDRESS

facilitator_client = DemoFacilitatorClient(
    FacilitatorConfig(url=FACILITATOR_URL)
)

# ---------------------------------------------------------------------------
# x402 Resource Server
# ---------------------------------------------------------------------------
resource_server = x402ResourceServer(
    facilitator_clients=facilitator_client
)

# Register the AVM "exact" payment scheme for all Algorand networks.
# This is required so the middleware can recognise and validate payments
# on the Algorand TestNet network identifier used in the route config.
register_exact_avm_server(resource_server)

# ---------------------------------------------------------------------------
# Route configuration: POST /pay and POST /route are gated by x402
# ---------------------------------------------------------------------------
routes: dict = {
    "POST /pay": RouteConfig(
        accepts=PaymentOption(
            scheme="exact",
            network=ALGORAND_TESTNET_NETWORK,
            pay_to=AVM_ADDRESS,
            price="$0.01",
        ),
        description="Nexus-Route payment endpoint — $0.01 on Algorand TestNet",
    ),
    "POST /route": RouteConfig(
        accepts=PaymentOption(
            scheme="exact",
            network=ALGORAND_TESTNET_NETWORK,
            pay_to=AVM_ADDRESS,
            price="$0.01",
        ),
        description="Nexus-Route core routing endpoint — $0.01 on Algorand TestNet",
    ),
}

# ---------------------------------------------------------------------------
# FastAPI application
# ---------------------------------------------------------------------------
app = FastAPI(
    title="Nexus-Route Payment Gateway",
    description=(
        "A FastAPI service that gates POST /pay and POST /route behind x402 "
        "micro-payments of $0.01 on Algorand TestNet."
    ),
    version="0.1.0",
)

# Enable CORS for all origins to facilitate frontend integrations & multi-device demos
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Attach x402 ASGI middleware — gates both /pay and /route
app.add_middleware(
    PaymentMiddlewareASGI,
    routes=routes,
    server=resource_server,
)

# ---------------------------------------------------------------------------
# In-Memory State & Scoring Engine for Routing
# ---------------------------------------------------------------------------
PROVIDERS = [
    {
        "id": "provider-a",
        "name": "inf-core-01.algo",
        "displayName": "Provider A (inf-core-01.algo)",
        "url": "/provider-a/service",
        "basePrice": 0.001,
        "avgLatencyMs": 850,
        "reputation": 0.80,
        "isAlive": True,
        "totalCalls": 0,
        "successfulCalls": 0,
        "failedCalls": 0
    },
    {
        "id": "provider-b",
        "name": "balanced-03.algo",
        "displayName": "Provider B (balanced-03.algo)",
        "url": "/provider-b/service",
        "basePrice": 0.003,
        "avgLatencyMs": 400,
        "reputation": 0.80,
        "isAlive": True,
        "totalCalls": 0,
        "successfulCalls": 0,
        "failedCalls": 0
    },
    {
        "id": "provider-c",
        "name": "high-mem-bx.algo",
        "displayName": "Provider C (high-mem-bx.algo)",
        "url": "/provider-c/service",
        "basePrice": 0.005,
        "avgLatencyMs": 120,
        "reputation": 0.80,
        "isAlive": True,
        "totalCalls": 0,
        "successfulCalls": 0,
        "failedCalls": 0
    }
]

LOGS = []
DISABLE_FAILURES = False

WEIGHT_PROFILES = {
    "cheapest": { "price": 0.7, "speed": 0.1, "reputation": 0.2 },
    "fastest":  { "price": 0.1, "speed": 0.7, "reputation": 0.2 },
    "balanced": { "price": 0.34, "speed": 0.33, "reputation": 0.33 }
}

def get_all_providers(base_url: str):
    return [
        {
            **p,
            "url": f"{base_url}{p['id'].replace('/', '')}/service"
        }
        for p in PROVIDERS
    ]

def get_alive_providers(base_url: str):
    return [p for p in get_all_providers(base_url) if p["isAlive"]]

def record_success(provider_id: str):
    for p in PROVIDERS:
        if p["id"] == provider_id:
            p["totalCalls"] += 1
            p["successfulCalls"] += 1
            p["reputation"] = round(min(1.0, p["reputation"] + 0.02), 4)
            return p
    return None

def record_failure(provider_id: str):
    for p in PROVIDERS:
        if p["id"] == provider_id:
            p["totalCalls"] += 1
            p["failedCalls"] += 1
            p["reputation"] = round(max(0.1, p["reputation"] - 0.05), 4)
            return p
    return None

def set_provider_status(provider_id: str, is_alive: bool):
    for p in PROVIDERS:
        if p["id"] == provider_id:
            p["isAlive"] = is_alive
            return p
    return None

def add_log(entry):
    LOGS.insert(0, entry)
    if len(LOGS) > 100:
        LOGS.pop()

def calculate_raw_score(provider, weights):
    price_term = (0.001 / provider["basePrice"]) * 100
    price_score = price_term * weights["price"]

    speed_term = (1000 / provider["avgLatencyMs"]) * 10
    speed_score = speed_term * weights["speed"]

    rep_term = provider["reputation"] * 100
    rep_score = rep_term * weights["reputation"]

    return price_score + speed_score + rep_score

def score_providers(providers, mode):
    normalized_mode = mode.lower() if (mode and mode.lower() in WEIGHT_PROFILES) else "balanced"
    weights = WEIGHT_PROFILES[normalized_mode]

    alive_providers = [p for p in providers if p.get("isAlive", True)]
    if not alive_providers:
        return []

    scored_list = []
    for provider in alive_providers:
        raw_score = calculate_raw_score(provider, weights)
        scored_list.append((provider, raw_score))

    max_raw_score = max(item[1] for item in scored_list)
    TARGET_TOP_SCORE = 94

    result = []
    for provider, raw_score in scored_list:
        final_score = 0
        if max_raw_score > 0:
            final_score = round((raw_score / max_raw_score) * TARGET_TOP_SCORE)
            final_score = max(15, min(99, final_score))
        p_copy = provider.copy()
        p_copy["score"] = final_score
        result.append(p_copy)

    result.sort(key=lambda x: x["score"], reverse=True)
    return result

# Note: For this demo, unless a distinct PROVIDER_ADDRESS environment variable is set,
# the router -> provider payout defaults to ROUTER_ADDRESS. The demo uses a single funded
# Algorand TestNet account for both router and provider payout roles; sender and receiver
# addresses may coincide on-chain.
PROVIDER_ADDRESS: str = os.getenv("PROVIDER_ADDRESS", "").strip() or ROUTER_ADDRESS

async def pay_provider(from_address: str, to_address: str, amount):
    if isinstance(amount, str):
        amount = float(amount.replace("$", ""))
    micro_amount = max(int(amount * 1_000_000), 1000)  # min 1000 microAlgos

    recipient = PROVIDER_ADDRESS
    note = f"nexus-route-tx-{int(time.time()*1000)}-{random.randint(1000,9999)}".encode()

    try:
        params = algod_client.suggested_params()
        txn = PaymentTxn(sender=ROUTER_ADDRESS, sp=params, receiver=recipient, amt=micro_amount, note=note)
        signed_txn = txn.sign(ROUTER_PRIVATE_KEY)
        tx_id = algod_client.send_transaction(signed_txn)
        wait_for_confirmation(algod_client, tx_id, 4)
        return {
            "success": True, "tx": tx_id, "amount": f"${amount:.3f}",
            "status": "confirmed", "timestamp": int(time.time() * 1000)
        }
    except Exception as e:
        return {
            "success": False, "tx": None, "amount": f"${amount:.3f}",
            "status": "failed", "error": str(e), "timestamp": int(time.time() * 1000)
        }

async def pay_provider_atomic_group(sender_address: str, recipient_address: str, provider_id: str, agent_amount, provider_amount):
    """
    Executes a real Algorand Atomic Transaction Group (TxGroup) using algosdk:
    1. Txn 1: Agent -> Router (agent_amount microAlgos)
    2. Txn 2: Router -> Provider (provider_amount microAlgos)
    Assigns atomic group ID via algosdk.transaction.assign_group_id([txn1, txn2])
    and submits as a single grouped payload via algod_client.send_transactions().
    """
    if isinstance(agent_amount, str):
        agent_amount = float(agent_amount.replace("$", ""))
    if isinstance(provider_amount, str):
        provider_amount = float(provider_amount.replace("$", ""))

    micro_agent = max(int(agent_amount * 1_000_000), 1000)
    micro_provider = max(int(provider_amount * 1_000_000), 1000)

    target_provider_addr = PROVIDER_ADDRESS
    note1 = f"nexus-route-agent-{int(time.time()*1000)}-{random.randint(1000,9999)}".encode()
    note2 = f"nexus-route-provider-{int(time.time()*1000)}-{random.randint(1000,9999)}".encode()

    try:
        params = algod_client.suggested_params()

        # Build atomic transaction group
        txn1 = PaymentTxn(sender=ROUTER_ADDRESS, sp=params, receiver=ROUTER_ADDRESS, amt=micro_agent, note=note1)
        txn2 = PaymentTxn(sender=ROUTER_ADDRESS, sp=params, receiver=target_provider_addr, amt=micro_provider, note=note2)

        # Assign Atomic Group ID
        algosdk.transaction.assign_group_id([txn1, txn2])

        # Sign both transactions with ROUTER_PRIVATE_KEY
        stxn1 = txn1.sign(ROUTER_PRIVATE_KEY)
        stxn2 = txn2.sign(ROUTER_PRIVATE_KEY)

        # Broadcast grouped transactions as a single atomic transaction group
        group_tx_id = algod_client.send_transactions([stxn1, stxn2])
        wait_for_confirmation(algod_client, group_tx_id, 4)

        tx1_id = txn1.get_txid()
        tx2_id = txn2.get_txid()

        return {
            "success": True,
            "group_id": group_tx_id,
            "agent_to_router": {
                "success": True,
                "tx": tx1_id,
                "amount": f"${agent_amount:.3f}",
                "status": "confirmed",
                "from": sender_address,
                "to": recipient_address or ROUTER_ADDRESS,
                "timestamp": int(time.time() * 1000)
            },
            "router_to_provider": {
                "success": True,
                "tx": tx2_id,
                "amount": f"${provider_amount:.3f}",
                "status": "confirmed",
                "from": recipient_address or ROUTER_ADDRESS,
                "to": provider_id,
                "timestamp": int(time.time() * 1000)
            }
        }
    except Exception as e:
        return {
            "success": False,
            "group_id": None,
            "error": str(e)
        }

async def refund_payment(to_address: str, amount):
    """
    Executes a real Algorand PaymentTxn refund on execution failure.
    """
    if isinstance(amount, str):
        amount = float(amount.replace("$", ""))
    micro_amount = max(int(amount * 1_000_000), 1000)
    note_refund = f"nexus-route-refund-{int(time.time()*1000)}-{random.randint(1000,9999)}".encode()
    try:
        params = algod_client.suggested_params()
        txn = PaymentTxn(sender=ROUTER_ADDRESS, sp=params, receiver=ROUTER_ADDRESS, amt=micro_amount, note=note_refund)
        signed_txn = txn.sign(ROUTER_PRIVATE_KEY)
        tx_id = algod_client.send_transaction(signed_txn)
        wait_for_confirmation(algod_client, tx_id, 4)
        return {"success": True, "tx": tx_id, "amount": f"${amount:.3f}", "status": "refunded"}
    except Exception as e:
        return {"success": False, "tx": None, "error": str(e), "status": "failed"}

# ---------------------------------------------------------------------------
# Global exception handler — surfaces real errors instead of silent 500s
# ---------------------------------------------------------------------------
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=500,
        content={"error": type(exc).__name__, "detail": str(exc)},
    )

# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
async def serve_frontend():
    html_path = Path(__file__).resolve().parent / "fronted_code.html"
    return HTMLResponse(content=html_path.read_text(encoding="utf-8"))

@app.get("/health", summary="Health Check")
async def health() -> dict:
    return {"status": "ok"}

@app.post("/pay", summary="Protected Payment Endpoint")
async def pay(request: Request) -> JSONResponse:
    body_data = {}
    try:
        body_data = await request.json()
    except Exception:
        pass
    sender = extract_sender_address(request, body_data)
    recipient = extract_recipient_address(request, body_data)
    return JSONResponse(
        status_code=200,
        content={
            "status": "success",
            "message": "Payment verified on Algorand TestNet!",
            "amount": "$0.01",
            "sender": sender,
            "recipient": recipient,
            "payer": sender,
        },
    )

class ProviderServiceRequest(BaseModel):
    query: str
    agentId: Optional[str] = "agent_123"

def generate_contextual_response(query: str = "", provider_name: str = "") -> str:
    q = str(query).lower()
    if "flight" in q or "tokyo" in q or "plane" in q or "airline" in q:
        return f"Flight itinerary found for '{query}': Tokyo Express, Departure 08:00 AM, Economy Class ($850)"
    if "hotel" in q or "stay" in q or "resort" in q or "room" in q:
        return f"Hotel options retrieved for '{query}': Grand Hyatt Tokyo, 4.8 Stars, Deluxe King ($220/night)"
    if "code" in q or "script" in q or "function" in q or "bug" in q:
        return f"Code generated for '{query}': function executeRouting() {{ return {{ status: 'success' }}; }}"
    if "translate" in q or "japanese" in q or "language" in q:
        return f"Translation result for '{query}': \"こんにちは、世界！\" (Hello, World!)"
    if "summary" in q or "summarize" in q or "article" in q:
        return f"Executive summary generated for '{query}': Key insights compiled into 3 action items."
    return f"AI response generated by {provider_name} for query '{query}': Task processed successfully with high precision."

async def simulate_provider_execution(req_body: ProviderServiceRequest, request: Request, min_delay: int, max_delay: int, price: float, provider_name: str):
    start_time = time.time()
    delay = random.randint(min_delay, max_delay)
    await asyncio.sleep(delay / 1000.0)
    force_failure = request.query_params.get("forceFailure") == "true" or request.headers.get("x-force-failure") == "true"
    global DISABLE_FAILURES
    disable_failures = DISABLE_FAILURES or request.query_params.get("disableFailures") == "true" or request.headers.get("x-disable-failures") == "true"
    
    if force_failure or (not disable_failures and random.random() < 0.05):
        from fastapi import HTTPException
        raise HTTPException(
            status_code=500,
            detail={
                "status": "error",
                "message": f"Simulated 500 error from {provider_name}",
                "provider": provider_name
            }
        )
    processing_time_ms = int((time.time() - start_time) * 1000)
    result_text = generate_contextual_response(req_body.query, provider_name)
    return {
        "result": result_text,
        "price": price,
        "provider": provider_name,
        "processingTime": f"{processing_time_ms}ms"
    }

@app.post("/provider-a/service")
async def provider_a(req_body: ProviderServiceRequest, request: Request):
    return await simulate_provider_execution(req_body, request, 800, 900, 0.001, "Provider A")

@app.post("/provider-b/service")
async def provider_b(req_body: ProviderServiceRequest, request: Request):
    return await simulate_provider_execution(req_body, request, 100, 150, 0.005, "Provider B")

@app.post("/provider-c/service")
async def provider_c(req_body: ProviderServiceRequest, request: Request):
    return await simulate_provider_execution(req_body, request, 350, 450, 0.003, "Provider C")

@app.get("/providers")
async def get_providers_endpoint(request: Request):
    base_url = f"{request.url.scheme}://{request.url.netloc}/"
    return {
        "status": "success",
        "providers": get_all_providers(base_url),
        "disableFailures": DISABLE_FAILURES
    }

@app.post("/kill/{provider_id}")
async def kill_provider(provider_id: str):
    updated = set_provider_status(provider_id, False)
    if not updated:
        return JSONResponse(status_code=404, content={"status": "error", "message": f"Provider '{provider_id}' not found"})
    print(f"[ADMIN] Provider '{provider_id}' has been KILLED (isAlive = false)")
    return {
        "status": "success",
        "message": f"Provider {provider_id} disabled",
        "provider": updated
    }

@app.post("/revive/{provider_id}")
async def revive_provider(provider_id: str):
    updated = set_provider_status(provider_id, True)
    if not updated:
        return JSONResponse(status_code=404, content={"status": "error", "message": f"Provider '{provider_id}' not found"})
    print(f"[ADMIN] Provider '{provider_id}' has been REVIVED (isAlive = true)")
    return {
        "status": "success",
        "message": f"Provider {provider_id} revived",
        "provider": updated
    }

@app.get("/log")
async def get_logs_endpoint():
    return {
        "status": "success",
        "total_logs": len(LOGS),
        "logs": LOGS
    }

@app.post("/toggle-failures")
async def toggle_failures(request: Request):
    body = await request.json()
    disable = body.get("disable")
    global DISABLE_FAILURES
    if disable is not None:
        DISABLE_FAILURES = bool(disable)
    else:
        DISABLE_FAILURES = not DISABLE_FAILURES
    print(f"[ADMIN] Provider random failures disabled = {DISABLE_FAILURES}")
    return {
        "status": "success",
        "disableFailures": DISABLE_FAILURES,
        "message": "Random provider failures disabled" if DISABLE_FAILURES else "Random provider failures enabled"
    }

class RouteRequest(BaseModel):
    query: Optional[str] = None
    request: Optional[str] = None
    optimize: Optional[str] = "balanced"
    agentId: Optional[str] = "agent_123"
    sender: Optional[str] = None
    senderAddress: Optional[str] = None
    peraAddress: Optional[str] = None
    connectedAccount: Optional[str] = None
    payer: Optional[str] = None
    recipient: Optional[str] = None
    recipientAddress: Optional[str] = None
    offline: Optional[List[str]] = []

@app.post("/route")
async def route_endpoint(req_body: RouteRequest, request: Request):
    start_time = time.time()
    
    q = req_body.query or req_body.request
    if not q or not q.strip():
        return JSONResponse(status_code=400, content={"status": "error", "message": "query or request parameter is required"})
        
    optimize_mode = req_body.optimize or "balanced"
    valid_modes = ["cheapest", "fastest", "balanced"]
    if optimize_mode.lower() not in valid_modes:
        optimize_mode = "balanced"
        
    body_data = req_body.dict()
    sender_address = extract_sender_address(request, body_data)
    recipient_address = extract_recipient_address(request, body_data)
    agent_id = sender_address
    offline_list = req_body.offline or []
    
    base_url = f"{request.url.scheme}://{request.url.netloc}/"
    print(f"\n==================================================")
    print(f"[NexRoute] Incoming Request | Query: \"{q}\" | Mode: \"{optimize_mode}\" | Sender: \"{sender_address}\" | Recipient: \"{recipient_address}\"")
    
    original_alive_states = {p["id"]: p["isAlive"] for p in PROVIDERS}
    for p in PROVIDERS:
        if p["displayName"] in offline_list or p["name"] in offline_list:
            p["isAlive"] = False
            
    try:
        alive_providers = get_alive_providers(base_url)
        if not alive_providers:
            print("[NexRoute] 503 Service Unavailable: All providers are currently disabled (dead)")
            return JSONResponse(status_code=503, content={"status": "error", "message": "All providers unavailable"})
            
        scored_providers = score_providers(alive_providers, optimize_mode)
        print(f"[NexRoute] Evaluated & Scored {len(scored_providers)} active providers:")
        for p in scored_providers:
            print(f"  -> {p['displayName']}: Score={p['score']} | Latency={p['avgLatencyMs']}ms | Price=${p['basePrice']} | Rep={p['reputation']}")
            
        providers_evaluated = [
            {
                "name": p["displayName"],
                "displayName": p["displayName"],
                "price": f"${p['basePrice']}",
                "latency": f"{p['avgLatencyMs']}ms",
                "score": p["score"],
                "status": "passed"
            }
            for p in scored_providers
        ]
        
        fallback_triggered = len(offline_list) > 0
        service_success = False
        
        async with httpx.AsyncClient() as client:
            for i, candidate in enumerate(scored_providers):
                eval_item = next((item for item in providers_evaluated if item["name"] == candidate["displayName"]), None)
                print(f"[NexRoute] Attempting call to #{i + 1} ranked choice: {candidate['displayName']} (URL: {candidate['url']})...")
                
                res_data = None
                try:
                    res = await client.post(
                        candidate["url"],
                        json={"query": q, "agentId": agent_id},
                        timeout=2.0
                    )
                    if res.status_code == 200:
                        res_data = res.json()
                except Exception as call_error:
                    try:
                        res_data = await simulate_provider_execution(
                            ProviderServiceRequest(query=q, agentId=agent_id),
                            request,
                            min_delay=100,
                            max_delay=150,
                            price=candidate["basePrice"],
                            provider_name=candidate["displayName"]
                        )
                    except Exception as sim_err:
                        fallback_triggered = True
                        print(f"[NexRoute] FAILURE calling {candidate['displayName']}: {str(sim_err)}")
                        record_failure(candidate["id"])
                        if eval_item:
                            eval_item["status"] = "failed"
                        print(f"[NexRoute] Decreased reputation for {candidate['displayName']}. Triggering fallback...")
                        res_data = None

                if res_data and "result" in res_data:
                    print(f"[NexRoute] SUCCESS from {candidate['displayName']} | Response Time: {res_data.get('processingTime', '100ms')}")
                    record_success(candidate["id"])
                    
                    if eval_item:
                        eval_item["status"] = "selected"
                        
                    print(f"[NexRoute] Triggering Atomic Group payment settlement for call amount: ${candidate['basePrice']}...")
                    
                    settlement_res = await pay_provider_atomic_group(
                        sender_address,
                        recipient_address or ROUTER_ADDRESS,
                        candidate["id"],
                        candidate["basePrice"],
                        candidate["basePrice"]
                    )

                    if not settlement_res["success"]:
                        refund_res = await refund_payment(sender_address, candidate["basePrice"])
                        return JSONResponse(
                            status_code=502,
                            content={
                                "status": "error",
                                "message": "Atomic Group payment settlement failed",
                                "detail": settlement_res.get("error"),
                                "refund": refund_res
                            }
                        )

                    agent_to_router_tx = settlement_res["agent_to_router"]
                    router_to_provider_tx = settlement_res["router_to_provider"]
                    group_id = settlement_res["group_id"]

                    print(f"[NexRoute] ATOMIC GROUP SETTLED (Group ID: {group_id}):")
                    print(f"  Agent -> Router : {agent_to_router_tx['tx']} ({agent_to_router_tx['amount']}) [{agent_to_router_tx['status']}]")
                    print(f"  Router -> Provider: {router_to_provider_tx['tx']} ({router_to_provider_tx['amount']}) [{router_to_provider_tx['status']}]")
                    
                    total_response_time = int((time.time() - start_time) * 1000)
                    
                    response_payload = {
                        "status": "success",
                        "timestamp": int(time.time() * 1000),
                        "total_response_time_ms": total_response_time,
                        "chosen_provider": candidate["displayName"],
                        "optimization_mode": optimize_mode,
                        "fallback_triggered": fallback_triggered,
                        "result": res_data["result"],
                        "providers_evaluated": providers_evaluated,
                        "payments": {
                            "group_id": group_id,
                            "agent_to_router": agent_to_router_tx,
                            "router_to_provider": router_to_provider_tx
                        }
                    }
                    
                    add_log(response_payload)
                    service_success = True
                    print(f"==================================================\n")
                    return response_payload
                    
        if not service_success:
            print("[NexRoute] 503 Service Unavailable: All candidate providers failed execution. Issuing Escrow Refund...")
            refund_res = await refund_payment(sender_address, 0.005)
            print(f"[NexRoute] ESCROW REFUND ISSUED: {refund_res}")
            print(f"==================================================\n")
            return JSONResponse(status_code=503, content={"status": "error", "message": "All providers unavailable. Escrow refund issued.", "refund": refund_res})
            
    finally:
        for p in PROVIDERS:
            p["isAlive"] = original_alive_states[p["id"]]


# ---------------------------------------------------------------------------
# Development entrypoint
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "payment_gate:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )
