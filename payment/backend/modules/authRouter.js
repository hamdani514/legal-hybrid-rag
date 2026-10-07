const express = require('express');
const router = express.Router();
const jwt = require('jsonwebtoken');
const User = require('../shared/User');

router.post('/login', async (req, res) => {
  try {
    const { email, password } = req.body;
    let user = await User.findOne({ email });
    if (!user) {
      user = await User.create({
        name: email ? email.split('@')[0] : 'Demo User',
        email: email || 'demo@example.com',
        password: password || 'password123',
        plan: 'free',
      });
    }

    const token = jwt.sign(
      { id: user._id, email: user.email },
      process.env.JWT_SECRET || 'supersecretjwtkey123',
      { expiresIn: '7d' }
    );

    res.json({ token, user: { id: user._id, email: user.email, plan: user.plan } });
  } catch (err) {
    console.error('Login error:', err);
    res.status(500).json({ message: 'Login failed' });
  }
});

module.exports = router;
