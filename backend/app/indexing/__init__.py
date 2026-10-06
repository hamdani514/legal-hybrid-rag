"""
Index builders that are derived from MongoDB and can be rebuilt at any time.

The vector index lives in app.vectorstore / app.ingestion; this package holds
the lexical (SQLite FTS5) index and the helpers that turn MongoDB nodes into
contextual-header chunks, which both the lexical index and the contextual dense
collection are built from — so the two can never chunk a judgment differently.
"""
