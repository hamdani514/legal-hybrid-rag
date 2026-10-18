from app.database import db
from loguru import logger

async def init_mongodb_indexes():
    if db.database is None:
        logger.error("MongoDB connection not initialized - cannot build indexes")
        return
        
    try:
        logger.info("Initializing MongoDB indexes...")
        
        # 1. Unique index on node_id to prevent duplicates, other structural lookups
        await db.database.nodes.create_index("node_id", unique=True)
        await db.database.nodes.create_index("pdf_id")
        await db.database.nodes.create_index("parent_node_id")
        
        # 2. Relational bridge indexing for embedding mapping table
        await db.database.embedding_mappings.create_index("node_id", unique=True)
        await db.database.embedding_mappings.create_index("file_id")
        await db.database.embedding_mappings.create_index("parent_node_id")

        # 3. Idempotency and 30-day TTL index for Stripe webhook events
        await db.database.processed_events.create_index("eventId", unique=True)
        await db.database.processed_events.create_index("processedAt", expireAfterSeconds=86400 * 30)

        # 4. User subscription indexes
        await db.database.users.create_index("stripeCustomerId")
        await db.database.users.create_index("plan")
        
        logger.info("MongoDB unique, relational, and subscription indexes initialized successfully.")
    except Exception as e:
        logger.error(f"Error during database index creation: {e}")
