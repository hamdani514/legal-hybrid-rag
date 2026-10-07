const User = require('../../shared/User');

const FREE_DAILY_LIMIT = 10;

module.exports = async (req, res, next) => {
  try {
    const user = await User.findById(req.user.id);
    if (!user) return res.status(404).json({ message: 'User not found.' });

    // Standard plan → unlimited
    if (user.plan === 'standard') return next();

    const today = new Date();
    today.setHours(0, 0, 0, 0);

    const isNewDay =
      !user.dailyQueries?.date || new Date(user.dailyQueries.date) < today;

    // New day → reset and allow
    if (isNewDay) {
      await User.updateOne(
        { _id: user._id },
        { $set: { 'dailyQueries.count': 1, 'dailyQueries.date': today } }
      );
      return next();
    }

    // Check limit
    if ((user.dailyQueries?.count || 0) >= FREE_DAILY_LIMIT) {
      return res.status(403).json({
        message: `Free plan limit reached (${FREE_DAILY_LIMIT}/day). Upgrade to Standard for unlimited queries.`,
        requiresUpgrade: true,
      });
    }

    // ✅ Atomic increment — no race condition
    await User.updateOne({ _id: user._id }, { $inc: { 'dailyQueries.count': 1 } });

    return next();
  } catch (err) {
    console.error('planGuard error:', err);
    return res.status(500).json({ message: 'Server error.' });
  }
};
