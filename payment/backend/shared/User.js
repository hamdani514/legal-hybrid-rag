const mongoose = require('mongoose');

const userSchema = new mongoose.Schema(
  {
    name: { type: String, required: true },
    email: { type: String, required: true, unique: true, index: true },
    password: { type: String, required: true },

    // ============================================================
    // Fields owned by module: payment
    // ============================================================
    plan: {
      type: String,
      enum: ['free', 'standard'],
      default: 'free',
      index: true,
    },
    stripeCustomerId: { type: String, default: null, index: true },
    stripeSubscriptionId: { type: String, default: null },
    planActivatedAt: { type: Date, default: null },
    planCancelsAt: { type: Date, default: null },

    dailyQueries: {
      count: { type: Number, default: 0 },
      date: { type: Date, default: Date.now },
    },
  },
  { timestamps: true }
);

module.exports = mongoose.models.User || mongoose.model('User', userSchema);
