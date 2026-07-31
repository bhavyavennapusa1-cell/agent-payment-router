/**
 * NexRoute - Admin & Management Controls
 * Endpoints for provider toggling (kill/revive), live metrics monitoring, audit history, and health checks.
 */

const express = require('express');
const router = express.Router();
const state = require('../data/state');

// POST /kill/:providerId — Force disable provider
router.post('/kill/:providerId', (req, res) => {
  try {
    const { providerId } = req.params;
    const updated = state.setProviderStatus(providerId, false);

    if (!updated) {
      return res.status(404).json({
        status: "error",
        message: `Provider '${providerId}' not found`
      });
    }

    console.log(`[ADMIN] Provider '${providerId}' has been KILLED (isAlive = false)`);
    return res.status(200).json({
      status: "success",
      message: `Provider ${providerId} disabled`,
      provider: updated
    });
  } catch (err) {
    res.status(500).json({ status: "error", message: err.message });
  }
});

// POST /revive/:providerId — Re-enable provider
router.post('/revive/:providerId', (req, res) => {
  try {
    const { providerId } = req.params;
    const updated = state.setProviderStatus(providerId, true);

    if (!updated) {
      return res.status(404).json({
        status: "error",
        message: `Provider '${providerId}' not found`
      });
    }

    console.log(`[ADMIN] Provider '${providerId}' has been REVIVED (isAlive = true)`);
    return res.status(200).json({
      status: "success",
      message: `Provider ${providerId} revived`,
      provider: updated
    });
  } catch (err) {
    res.status(500).json({ status: "error", message: err.message });
  }
});

// GET /providers — Live provider metrics & status dashboard endpoint
router.get('/providers', (req, res) => {
  try {
    const allProviders = state.getAllProviders();
    return res.status(200).json({
      status: "success",
      providers: allProviders,
      disableFailures: state.getDisableFailures()
    });
  } catch (err) {
    res.status(500).json({ status: "error", message: err.message });
  }
});

// GET /log — Audit history log of all past routing decisions (most recent first)
router.get('/log', (req, res) => {
  try {
    const logs = state.getLogs();
    return res.status(200).json({
      status: "success",
      total_logs: logs.length,
      logs: logs
    });
  } catch (err) {
    res.status(500).json({ status: "error", message: err.message });
  }
});

// GET /health — Basic service sanity check & uptime indicator
router.get('/health', (req, res) => {
  try {
    return res.status(200).json({
      status: "ok",
      uptime: Math.floor(process.uptime()),
      timestamp: Date.now()
    });
  } catch (err) {
    res.status(500).json({ status: "error", message: err.message });
  }
});

// POST /toggle-failures — Optional toggle for live demo random failure simulation
router.post('/toggle-failures', (req, res) => {
  try {
    const { disable } = req.body || {};
    const newState = state.setDisableFailures(disable !== undefined ? disable : !state.getDisableFailures());
    console.log(`[ADMIN] Provider random failures disabled = ${newState}`);
    return res.status(200).json({
      status: "success",
      disableFailures: newState,
      message: newState ? "Random provider failures disabled" : "Random provider failures enabled"
    });
  } catch (err) {
    res.status(500).json({ status: "error", message: err.message });
  }
});

module.exports = router;
