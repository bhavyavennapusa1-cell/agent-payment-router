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
# ---------------------------------------------------------------------------
AVM_ADDRESS: str = os.getenv("AVM_ADDRESS", "").strip()
FACILITATOR_URL: str = os.getenv("FACILITATOR_URL", "https://x402.org/facilitator").strip()

if not AVM_ADDRESS:
    raise EnvironmentError(
        "AVM_ADDRESS is not set or is empty.\n"
        f"Searched .env at: {_root_env}\n"
        "Please ensure AVM_ADDRESS=<your_algorand_address> is present in the .env file."
    )

print(f"[config] AVM_ADDRESS  = {AVM_ADDRESS}")
print(f"[config] FACILITATOR_URL = {FACILITATOR_URL}")

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
facilitator_client = HTTPFacilitatorClient(
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
# Route configuration: POST /pay requires $0.01 on Algorand TestNet
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
}

# ---------------------------------------------------------------------------
# FastAPI application
# ---------------------------------------------------------------------------
app = FastAPI(
    title="Nexus-Route Payment Gateway",
    description=(
        "A FastAPI service that gates POST /pay behind an x402 "
        "micro-payment of $0.01 on Algorand TestNet."
    ),
    version="0.1.0",
)

# ---------------------------------------------------------------------------
# Attach x402 ASGI middleware — only /pay is gated
# ---------------------------------------------------------------------------
app.add_middleware(
    PaymentMiddlewareASGI,
    routes=routes,
    server=resource_server,
)

# ---------------------------------------------------------------------------
# Global exception handler — surfaces real errors instead of silent 500s
# ---------------------------------------------------------------------------

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Return a JSON error body for any unhandled exception."""
    return JSONResponse(
        status_code=500,
        content={"error": type(exc).__name__, "detail": str(exc)},
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/health", summary="Health Check")
async def health() -> dict:
    """
    Returns a simple health-check response.
    No payment is required to access this endpoint.
    """
    return {"status": "ok"}


@app.post("/pay", summary="Protected Payment Endpoint")
async def pay(request: Request) -> JSONResponse:
    """
    Protected endpoint behind x402 payment middleware.

    The PaymentMiddlewareASGI intercepts the request and validates the
    X-Payment header against the Algorand TestNet facilitator before this
    handler is ever invoked.  If the payment is missing or invalid, the
    middleware returns HTTP 402 automatically.

    On successful payment verification, this handler returns confirmation.
    """
    return JSONResponse(
        status_code=200,
        content={
            "status": "success",
            "message": "Payment verified on Algorand TestNet!",
            "amount": "$0.01",
        },
    )


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
