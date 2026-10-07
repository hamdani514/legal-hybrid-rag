require('dotenv').config();
const express = require('express');
const mongoose = require('mongoose');
const cors = require('cors');

const app = express();
app.set('trust proxy', 1);

app.use(
  cors({
    origin: process.env.FRONTEND_URL || 'http://localhost:5173',
    credentials: true,
  })
);

// ============================================================
// ✅ 1. WEBHOOK FIRST — needs raw Buffer body + 1mb limit
// ============================================================
app.use(
  '/api/payments/webhook',
  express.raw({ type: 'application/json', limit: '1mb' }),
  require('./modules/payment/controller').stripeWebhook
);

// ============================================================
// ✅ 2. JSON PARSER SECOND
// ============================================================
app.use(express.json({ limit: '10mb' }));

// ============================================================
// ✅ 3. ALL OTHER ROUTES THIRD
// ============================================================
app.use('/api/auth', require('./modules/authRouter'));
app.use('/api/contact', require('./modules/contact/routes'));
app.use('/api/payments', require('./modules/payment/routes'));
app.use('/api/retrieval', require('./modules/retrieval/routes'));

// Health check
app.get('/health', (req, res) => res.json({ status: 'ok' }));

// Global error handler
app.use((err, req, res, next) => {
  if (err && err.type === 'entity.parse.failed') {
    return res.status(400).json({ message: 'Invalid JSON body.' });
  }
  console.error('Unhandled error:', err);
  res.status(500).json({ message: 'Server error.' });
});

const PORT = process.env.PORT || 5000;
const MONGO_URL = process.env.MONGO_URL || 'mongodb://127.0.0.1:27017/rag_payment_db';

mongoose
  .connect(MONGO_URL, { serverSelectionTimeoutMS: 5000 })
  .then(() => {
    console.log('✅ MongoDB connected');
    app.listen(PORT, () => console.log(`🚀 Server on port ${PORT}`));
  })
  .catch((e) => {
    console.error('MongoDB connection error:', e.message);
    console.log('Starting server in fallback mode without MongoDB connection...');
    app.listen(PORT, () => console.log(`🚀 Server on port ${PORT} (fallback mode)`));
  });
