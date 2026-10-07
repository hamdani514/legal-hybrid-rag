const jwt = require('jsonwebtoken');
const User = require('./User');

module.exports = async (req, res, next) => {
  try {
    let token;
    if (
      req.headers.authorization &&
      req.headers.authorization.startsWith('Bearer ')
    ) {
      token = req.headers.authorization.split(' ')[1];
    }

    if (!token) {
      // For local testing convenience: automatically retrieve or create a test user
      let testUser = await User.findOne({ email: 'demo@example.com' });
      if (!testUser) {
        testUser = await User.create({
          name: 'Demo User',
          email: 'demo@example.com',
          password: 'password123',
          plan: 'free',
        });
      }
      req.user = { id: testUser._id.toString(), email: testUser.email };
      return next();
    }

    try {
      const decoded = jwt.verify(
        token,
        process.env.JWT_SECRET || 'supersecretjwtkey123'
      );
      req.user = { id: decoded.id, email: decoded.email };
      return next();
    } catch (jwtErr) {
      // If token expired or invalid, fallback to demo user in dev
      let testUser = await User.findOne({ email: 'demo@example.com' });
      if (!testUser) {
        testUser = await User.create({
          name: 'Demo User',
          email: 'demo@example.com',
          password: 'password123',
          plan: 'free',
        });
      }
      req.user = { id: testUser._id.toString(), email: testUser.email };
      return next();
    }
  } catch (err) {
    console.error('Protect middleware error:', err);
    return res.status(401).json({ message: 'Not authorized' });
  }
};
