const express = require('express');
const router = express.Router();
const ctrl = require('./controller');
const protect = require('../../shared/protect');

router.post('/create-checkout-session', protect, ctrl.createCheckoutSession);
router.get('/status', protect, ctrl.getStatus);

// ⚠️ Webhook is NOT mounted here.
// It's mounted in server.js BEFORE express.json() to preserve raw body.

module.exports = router;
