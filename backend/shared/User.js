/**
 * MongoDB / Mongoose User Model Schema
 * 
 * Fields for subscription state, Stripe references, display card info,
 * cancellation & auto-renewal tracking, and daily query rate limit quotas.
 */

const mongoose = require('mongoose');
const { Schema } = mongoose;

const userSchema = new Schema({
  name: { type: String, required: true },
  email: { type: String, required: true, unique: true, index: true },
  password_hash: { type: String },
  role: { type: String, enum: ['user', 'admin', 'superadmin'], default: 'user' },
  status: { type: String, default: 'active' },

  // Subscription state (owned by payment module)
  plan: {
    type: String,
    enum: ['free', 'standard'],
    default: 'free',
    index: true
  },
  stripeCustomerId: { type: String, default: null, index: true },
  stripeSubscriptionId: { type: String, default: null },
  stripePaymentMethodId: { type: String, default: null },

  // Display info (for "Visa •••• 4242" UI)
  cardLast4: { type: String, default: null },
  cardBrand: { type: String, default: null },

  // Cancellation tracking
  cancelAtPeriodEnd: { type: Boolean, default: false },
  cancellationRequestedAt: { type: Date, default: null },
  subscriptionEndsAt: { type: Date, default: null },  // = current_period_end
  autoRenew: { type: Boolean, default: true },

  // Query quota (daily reset)
  dailyQueries: {
    count: { type: Number, default: 0 },
    date: { type: Date, default: Date.now }  // last reset timestamp
  },

  createdAt: { type: Date, default: Date.now },
  updatedAt: { type: Date, default: Date.now }
});

module.exports = mongoose.models.User || mongoose.model('User', userSchema);
