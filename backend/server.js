/**
 * NexRoute - Intelligent Agent Routing & Payment Orchestration Server
 * Main application entry point.
 */

require('dotenv').config();
const express = require('express');
const cors = require('cors');

const providerRoutes = require('./routes/providers');
const routerRoutes = require('./routes/router');
const adminRoutes = require('./routes/admin');

const app = express();
const PORT = process.env.PORT || 3000;

// Enable CORS for all origins to facilitate frontend integrations & multi-device demos
app.use(cors());

// Middleware to parse incoming JSON payloads
app.use(express.json());

// Request logger for quick terminal diagnostics
app.use((req, res, next) => {
  const timestamp = new Date().toISOString().split('T')[1].slice(0, 8);
  console.log(`[${timestamp}] ${req.method} ${req.url}`);
  next();
});

// Mount routes
app.use('/', providerRoutes);
app.use('/', routerRoutes);
app.use('/', adminRoutes);

// Catch-all 404 Handler
app.use((req, res) => {
  res.status(404).json({
    status: "error",
    message: `Endpoint ${req.method} ${req.url} not found`
  });
});

// Global Error Handler to prevent process crashes
app.use((err, req, res, next) => {
  console.error('[NexRoute Global Error Handler]:', err);
  res.status(500).json({
    status: "error",
    message: "Internal server exception",
    error: err.message
  });
});

// Start Server
app.listen(PORT, () => {
  console.log(`
============================================================
  🚀  NexRoute AI Routing & Payment Orchestration Service  🚀
============================================================
  Server running on: http://localhost:${PORT}
  Environment:      ${process.env.NODE_ENV || 'development'}
  
  Available Endpoints:
  ----------------------------------------------------------
  POST /route              Main intelligent routing endpoint
  GET  /providers          Get live provider statuses & reputation
  GET  /log                Get past routing decision history
  GET  /health             Health check & server uptime
  POST /kill/:providerId   Disable a specific provider (demo)
  POST /revive/:providerId Re-enable a specific provider (demo)
  POST /toggle-failures    Toggle random failure simulation
============================================================
  `);
});
