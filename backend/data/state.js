/**
 * NexRoute - In-Memory State Management Store
 * Stores active AI service providers, reputation scores, routing history logs,
 * and global demo configurations.
 */

const PORT = process.env.PORT || 3000;

// Initial provider profiles
const providers = [
  {
    id: "provider-a",
    name: "Provider A",
    displayName: "Provider A (Budget)",
    url: `http://localhost:${PORT}/provider-a/service`,
    basePrice: 0.001,
    avgLatencyMs: 850,
    reputation: 0.80,
    isAlive: true,
    totalCalls: 0,
    successfulCalls: 0,
    failedCalls: 0
  },
  {
    id: "provider-b",
    name: "Provider B",
    displayName: "Provider B (Fast & Premium)",
    url: `http://localhost:${PORT}/provider-b/service`,
    basePrice: 0.005,
    avgLatencyMs: 120,
    reputation: 0.80,
    isAlive: true,
    totalCalls: 0,
    successfulCalls: 0,
    failedCalls: 0
  },
  {
    id: "provider-c",
    name: "Provider C",
    displayName: "Provider C (Balanced)",
    url: `http://localhost:${PORT}/provider-c/service`,
    basePrice: 0.003,
    avgLatencyMs: 400,
    reputation: 0.80,
    isAlive: true,
    totalCalls: 0,
    successfulCalls: 0,
    failedCalls: 0
  }
];

// Audit trail for past routing decisions
const logs = [];

// Admin toggle to force-disable 5% random failure rate during controlled demo
let disableFailures = false;

/**
 * Returns copy of all provider states (dynamic port resolution)
 */
function getAllProviders() {
  const currentPort = process.env.PORT || 3000;
  return providers.map(p => ({
    ...p,
    url: `http://localhost:${currentPort}/${p.id}/service`
  }));
}

/**
 * Returns array of currently alive providers
 */
function getAliveProviders() {
  return getAllProviders().filter(p => p.isAlive);
}

/**
 * Find provider by ID
 */
function getProviderById(id) {
  const currentPort = process.env.PORT || 3000;
  const p = providers.find(item => item.id === id);
  if (!p) return null;
  return {
    ...p,
    url: `http://localhost:${currentPort}/${p.id}/service`
  };
}

/**
 * Update provider reputation & stats on successful routing execution
 */
function recordSuccess(providerId) {
  const p = providers.find(item => item.id === providerId);
  if (!p) return;

  p.totalCalls++;
  p.successfulCalls++;
  p.reputation = parseFloat(Math.min(1.0, p.reputation + 0.02).toFixed(4));
  return p;
}

/**
 * Update provider reputation & stats on failed routing execution
 */
function recordFailure(providerId) {
  const p = providers.find(item => item.id === providerId);
  if (!p) return;

  p.totalCalls++;
  p.failedCalls++;
  p.reputation = parseFloat(Math.max(0.1, p.reputation - 0.05).toFixed(4));
  return p;
}

/**
 * Toggle provider status (kill/revive)
 */
function setProviderStatus(providerId, isAlive) {
  const p = providers.find(item => item.id === providerId);
  if (!p) return null;

  p.isAlive = isAlive;
  return p;
}

/**
 * Store a routing decision log (most recent first)
 */
function addLog(entry) {
  logs.unshift(entry);
  // Keep up to 100 log entries to prevent unbounded memory growth
  if (logs.length > 100) {
    logs.pop();
  }
}

/**
 * Retrieve routing logs
 */
function getLogs() {
  return logs;
}

/**
 * Toggle random failure setting
 */
function setDisableFailures(state) {
  disableFailures = Boolean(state);
  return disableFailures;
}

function getDisableFailures() {
  return disableFailures;
}

module.exports = {
  getAllProviders,
  getAliveProviders,
  getProviderById,
  recordSuccess,
  recordFailure,
  setProviderStatus,
  addLog,
  getLogs,
  setDisableFailures,
  getDisableFailures
};
