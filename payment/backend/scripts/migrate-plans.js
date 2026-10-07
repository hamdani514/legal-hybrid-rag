require('dotenv').config();
const mongoose = require('mongoose');
const User = require('../shared/User');

(async () => {
  try {
    const mongoUrl = process.env.MONGO_URL || 'mongodb://127.0.0.1:27017/rag_payment_db';
    await mongoose.connect(mongoUrl, { serverSelectionTimeoutMS: 3000 });
    console.log('✅ Connected to MongoDB');

    const result = await User.updateMany(
      { plan: { $exists: false } },
      { $set: { plan: 'free' } }
    );

    console.log(`✅ Migrated ${result.modifiedCount} users to 'free' plan`);
    await mongoose.disconnect();
    process.exit(0);
  } catch (err) {
    console.error('❌ Migration failed:', err);
    process.exit(1);
  }
})();
