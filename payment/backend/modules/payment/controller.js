const mongoose = require('mongoose');
const stripe = require('./stripeClient');
const User = require('../../shared/User');

// ============================================================
// Idempotency — prevents duplicate webhook processing
// ============================================================
const processedEventSchema = new mongoose.Schema({
  eventId: { type: String, unique: true, index: true },
  processedAt: { type: Date, default: Date.now, expires: 86400 * 30 },
});
const ProcessedEvent =
  mongoose.models.ProcessedEvent ||
  mongoose.model('ProcessedEvent', processedEventSchema);

// ============================================================
// CREATE CHECKOUT SESSION
// POST /api/payments/create-checkout-session  (protected)
// ============================================================
exports.createCheckoutSession = async (req, res) => {
  try {
    const userId = req.user.id;
    const user = await User.findById(userId);

    if (!user) {
      return res.status(404).json({ message: 'User not found.' });
    }

    if (user.plan === 'standard') {
      return res.status(400).json({ message: 'You are already on the Standard plan.' });
    }

    const sessionParams = {
      mode: 'subscription',
      payment_method_types: ['card'],
      line_items: [{ price: process.env.STRIPE_PRICE_ID, quantity: 1 }],
      client_reference_id: userId,
      success_url: `${process.env.FRONTEND_URL}/payment/success?session_id={CHECKOUT_SESSION_ID}`,
      cancel_url: `${process.env.FRONTEND_URL}/payment/cancel`,
      metadata: { userId },
    };

    // Reuse existing Stripe customer if available
    if (user.stripeCustomerId) {
      sessionParams.customer = user.stripeCustomerId;
    } else {
      sessionParams.customer_email = user.email;
    }

    const session = await stripe.checkout.sessions.create(sessionParams);

    return res.status(200).json({ url: session.url, sessionId: session.id });
  } catch (err) {
    console.error('createCheckoutSession error:', err);
    return res.status(500).json({ message: 'Failed to create checkout session.' });
  }
};

// ============================================================
// GET SUBSCRIPTION STATUS
// GET /api/payments/status  (protected)
// ============================================================
exports.getStatus = async (req, res) => {
  try {
    const user = await User.findById(req.user.id);
    if (!user) return res.status(404).json({ message: 'User not found.' });

    const today = new Date();
    today.setHours(0, 0, 0, 0);
    const isNewDay =
      !user.dailyQueries?.date || new Date(user.dailyQueries.date) < today;

    return res.status(200).json({
      plan: user.plan || 'free',
      planActivatedAt: user.planActivatedAt,
      planCancelsAt: user.planCancelsAt,
      hasStripeCustomer: !!user.stripeCustomerId,
      dailyQueriesUsed:
        user.plan === 'free'
          ? isNewDay
            ? 0
            : user.dailyQueries?.count || 0
          : null,
      dailyQueriesLimit: user.plan === 'free' ? 10 : null,
    });
  } catch (err) {
    console.error('getStatus error:', err);
    return res.status(500).json({ message: 'Server error.' });
  }
};

// ============================================================
// STRIPE WEBHOOK
// POST /api/payments/webhook  (public, raw body, mounted in server.js)
// ============================================================
exports.stripeWebhook = async (req, res) => {
  const sig = req.headers['stripe-signature'];
  const endpointSecret = process.env.STRIPE_WEBHOOK_SECRET;

  // Defensive check — must be a Buffer
  if (!Buffer.isBuffer(req.body)) {
    console.error('Webhook body is not a Buffer. Check server.js mount order.');
    return res.status(500).send('Server configuration error');
  }

  // Verify signature
  let event;
  try {
    event = stripe.webhooks.constructEvent(req.body, sig, endpointSecret);
  } catch (err) {
    console.error('Webhook signature verification failed:', err.message);
    return res.status(400).send(`Webhook Error: ${err.message}`);
  }

  // Idempotency — fail hard on non-duplicate errors
  try {
    const existing = await ProcessedEvent.findOne({ eventId: event.id });
    if (existing) {
      console.log(`Event ${event.id} already processed — skipping`);
      return res.json({ received: true, duplicate: true });
    }
    await ProcessedEvent.create({ eventId: event.id });
  } catch (err) {
    if (err.code === 11000) {
      // Concurrent duplicate — treat as already processed
      return res.json({ received: true, duplicate: true });
    }
    console.error('Idempotency check failed:', err);
    // Fail hard so Stripe retries
    return res.status(500).json({ message: 'Idempotency check failed.' });
  }

  console.log(`[Stripe Webhook] Received: ${event.type}`);

  try {
    switch (event.type) {
      case 'checkout.session.completed': {
        const session = event.data.object;
        const userId = session.client_reference_id;

        if (!userId) {
          console.warn('No client_reference_id in session');
          break;
        }

        await User.findByIdAndUpdate(userId, {
          plan: 'standard',
          stripeCustomerId: session.customer,
          stripeSubscriptionId: session.subscription,
          planActivatedAt: new Date(),
          planCancelsAt: null,
        });
        console.log(`✅ Activated Standard plan for user ${userId}`);
        break;
      }

      case 'customer.subscription.updated': {
        const subscription = event.data.object;
        const user = await User.findOne({ stripeCustomerId: subscription.customer });
        if (user && subscription.status === 'active') {
          user.plan = 'standard';
          user.planCancelsAt = subscription.cancel_at
            ? new Date(subscription.cancel_at * 1000)
            : null;
          await user.save();
          console.log(`🔄 Updated subscription for ${user.email}`);
        }
        break;
      }

      case 'customer.subscription.deleted': {
        const subscription = event.data.object;
        const user = await User.findOne({ stripeCustomerId: subscription.customer });
        if (user) {
          user.plan = 'free';
          user.stripeSubscriptionId = null;
          user.planCancelsAt = null;
          await user.save();
          console.log(`⬇️ Downgraded to Free: ${user.email}`);
        }
        break;
      }

      case 'invoice.payment_failed': {
        const invoice = event.data.object;
        const user = await User.findOne({ stripeCustomerId: invoice.customer });
        if (user) {
          console.warn(`⚠️ Payment failed for ${user.email}`);
        }
        break;
      }

      default:
        console.log(`Unhandled event type: ${event.type}`);
    }
  } catch (err) {
    console.error('Webhook handling error:', err);
  }

  return res.json({ received: true });
};
