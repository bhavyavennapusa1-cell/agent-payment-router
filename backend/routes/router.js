/**
 * NexRoute - Core Intelligent Router Endpoint
 * Handles incoming agent requests, scores candidate providers, executes service calls,
 * manages fallback/failover scenarios, and triggers dual-sided payment settlement.
 */

const express = require('express');
const router = express.Router();
const axios = require('axios');
const state = require('../data/state');
const { scoreProviders } = require('../services/scoring');
const { payProvider } = require('../services/payment');

// POST /route - Main routing endpoint
router.post('/route', async (req, res) => {
  const startTime = Date.now();

  try {
    const { query, optimize, agentId, sender, senderAddress, peraAddress, connectedAccount, payer, recipient, recipientAddress } = req.body || {};

    // Input Validation: query is strictly required
    if (!query || typeof query !== 'string' || query.trim().length === 0) {
      console.log('[NexRoute] 400 Bad Request: Missing query parameter');
      return res.status(400).json({
        status: "error",
        message: "query parameter is required and must be a non-empty string"
      });
    }

    // Default optimize mode to "balanced" if missing or invalid
    const validModes = ["cheapest", "fastest", "balanced"];
    const mode = (optimize && validModes.includes(optimize.toLowerCase()))
      ? optimize.toLowerCase()
      : "balanced";

    const headerSender = req.headers['x-pera-address'] || req.headers['x-sender-address'];
    const headerRecipient = req.headers['x-recipient-address'] || req.headers['x-pay-to'];

    const defaultRecipient = process.env.AVM_ADDRESS || "O7N4OJSAHPSREE57UJFOQWAKYMEKAWDU72HHFKH4M7REAQM4Z37XKPDOGE";

    const effectiveSender = headerSender || sender || senderAddress || peraAddress || connectedAccount || payer || agentId || "agent_123";
    const effectiveRecipient = headerRecipient || recipient || recipientAddress || defaultRecipient;

    console.log(`\n==================================================`);
    console.log(`[NexRoute] Incoming Request | Query: "${query}" | Mode: "${mode}" | Sender: "${effectiveSender}" | Recipient: "${effectiveRecipient}"`);

    // Step 1: Filter to only alive providers
    const aliveProviders = state.getAliveProviders();
    if (aliveProviders.length === 0) {
      console.log('[NexRoute] 503 Service Unavailable: All providers are currently disabled (dead)');
      return res.status(503).json({
        status: "error",
        message: "All providers unavailable"
      });
    }

    // Step 2: Score all alive providers using the selected weight profile
    const scoredProviders = scoreProviders(aliveProviders, mode);

    console.log(`[NexRoute] Evaluated & Scored ${scoredProviders.length} active providers:`);
    scoredProviders.forEach(p => {
      console.log(`  -> ${p.displayName}: Score=${p.score} | Latency=${p.avgLatencyMs}ms | Price=$${p.basePrice} | Rep=${p.reputation}`);
    });

    // Build initial evaluated list for response shape
    const providersEvaluated = scoredProviders.map(p => ({
      name: p.name || p.displayName,
      price: `$${p.basePrice}`,
      latency: `${p.avgLatencyMs}ms`,
      score: p.score,
      status: "passed" // default, will be updated to "selected" or "failed"
    }));

    let fallbackTriggered = false;
    let serviceSuccess = false;

    // Step 3: Attempt to call providers in order of score (descending)
    for (let i = 0; i < scoredProviders.length; i++) {
      const candidate = scoredProviders[i];
      const evalItem = providersEvaluated.find(e => e.name === (candidate.name || candidate.displayName));

      console.log(`[NexRoute] Attempting call to #${i + 1} ranked choice: ${candidate.displayName} (URL: ${candidate.url})...`);

      try {
        // HTTP call to provider with 2000ms timeout
        const response = await axios.post(
          candidate.url,
          { query, agentId: effectiveSender },
          { timeout: 2000 }
        );

        if (response.status === 200 && response.data && response.data.result) {
          console.log(`[NexRoute] SUCCESS from ${candidate.displayName} | Response Time: ${response.data.processingTime}`);

          // Update reputation (+0.02) and statistics
          state.recordSuccess(candidate.id);

          // Update status in evaluated list
          if (evalItem) evalItem.status = "selected";

          // Step 4: Execute Dual Payment Settlement (Agent -> Router, Router -> Provider)
          console.log(`[NexRoute] Triggering payment settlement for call amount: $${candidate.basePrice}...`);

          const agentToRouterTx = await payProvider(
            effectiveSender,
            effectiveRecipient || "nexroute_router",
            candidate.basePrice
          );

          const routerToProviderTx = await payProvider(
            effectiveRecipient || "nexroute_router",
            candidate.id,
            candidate.basePrice
          );

          console.log(`[NexRoute] PAYMENT SETTLED:`);
          console.log(`  Agent -> Router : ${agentToRouterTx.tx} (${agentToRouterTx.amount}) [${agentToRouterTx.status}]`);
          console.log(`  Router -> Provider: ${routerToProviderTx.tx} (${routerToProviderTx.amount}) [${routerToProviderTx.status}]`);

          const totalResponseTime = Date.now() - startTime;

          // Standardized response payload
          const responsePayload = {
            status: "success",
            timestamp: Date.now(),
            total_response_time_ms: totalResponseTime,
            chosen_provider: candidate.displayName,
            optimization_mode: mode,
            fallback_triggered: fallbackTriggered,
            result: response.data.result,
            providers_evaluated: providersEvaluated,
            payments: {
              agent_to_router: {
                tx: agentToRouterTx.tx,
                amount: agentToRouterTx.amount,
                status: agentToRouterTx.status,
                from: agentToRouterTx.from || effectiveSender,
                to: agentToRouterTx.to || effectiveRecipient
              },
              router_to_provider: {
                tx: routerToProviderTx.tx,
                amount: routerToProviderTx.amount,
                status: routerToProviderTx.status,
                from: routerToProviderTx.from || effectiveRecipient,
                to: routerToProviderTx.to || candidate.id
              }
            }
          };

          // Store decision in audit log
          state.addLog(responsePayload);

          serviceSuccess = true;
          console.log(`==================================================\n`);
          return res.status(200).json(responsePayload);
        }
      } catch (callError) {
        // Provider failed (timeout, 500 error, or connection refusal)
        fallbackTriggered = true;
        console.log(`[NexRoute] FAILURE calling ${candidate.displayName}: ${callError.message}`);

        // Update reputation (-0.05) and stats
        state.recordFailure(candidate.id);

        if (evalItem) evalItem.status = "failed";
        console.log(`[NexRoute] Decreased reputation for ${candidate.displayName}. Triggering fallback to next provider...`);
      }
    }

    // Step 5: If all providers failed
    if (!serviceSuccess) {
      console.log('[NexRoute] 503 Service Unavailable: All candidate providers failed execution');
      console.log(`==================================================\n`);
      return res.status(503).json({
        status: "error",
        message: "All providers unavailable"
      });
    }

  } catch (globalError) {
    console.error('[NexRoute] Global router exception:', globalError);
    return res.status(500).json({
      status: "error",
      message: "Internal routing server error",
      details: globalError.message
    });
  }
});

module.exports = router;
