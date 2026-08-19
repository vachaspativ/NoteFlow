/**
 * NoteFlow Node.js UI Server
 * Serves static web dashboard and proxies API / WebSocket traffic to NoteFlow Python backend
 */

const express = require('express');
const path = require('path');
const { createProxyMiddleware } = require('http-proxy-middleware');

const app = express();
const PORT = process.env.NODE_PORT || 3000;
const PYTHON_API_URL = process.env.PYTHON_API_URL || 'http://127.0.0.1:5000';

// Serve static frontend assets from noteflow/web
const staticDir = path.join(__dirname, '..', 'noteflow', 'web');
app.use('/static', express.static(staticDir));

// Proxy API requests to NoteFlow backend
app.use(
  '/api',
  createProxyMiddleware({
    target: PYTHON_API_URL,
    changeOrigin: true,
  })
);

// Proxy WebSockets
const wsProxy = createProxyMiddleware({
  target: PYTHON_API_URL,
  ws: true,
  changeOrigin: true,
});
app.use('/ws', wsProxy);

// Serve single-page web app for root
app.get('*', (req, res) => {
  res.sendFile(path.join(staticDir, 'index.html'));
});

const server = app.listen(PORT, () => {
  console.log(`\n======================================================`);
  console.log(`🎙️  NoteFlow Node.js UI running at: http://localhost:${PORT}`);
  console.log(`🔄 Proxying requests to Python API: ${PYTHON_API_URL}`);
  console.log(`======================================================\n`);
});

// Manually subscribe to upgrade event to support WebSockets proxying
server.on('upgrade', wsProxy.upgrade);
