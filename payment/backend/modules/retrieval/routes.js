const express = require('express');
const router = express.Router();
const protect = require('../../shared/protect');
const planGuard = require('../payment/planGuard');

// Mock Retrieval Controllers
const retrieve = (req, res) => {
  res.json({ success: true, message: 'Retrieval query executed successfully.' });
};
const search = (req, res) => {
  res.json({ success: true, message: 'Search executed successfully.' });
};
const ask = (req, res) => {
  res.json({ success: true, message: 'RAG question answered successfully.' });
};

router.post('/retrieve', protect, planGuard, retrieve);
router.post('/search', protect, planGuard, search);
router.post('/ask', protect, planGuard, ask);

module.exports = router;
