import os
import chromadb
from pathlib import Path
from app.config import settings
from loguru import logger

class ChromaStore:
    def __init__(self):
        # Configure local persistent storage path
        db_path = getattr(settings, "CHROMA_DB_PATH", None)
        if not db_path:
            db_path = str(Path(__file__).resolve().parents[2] / "chroma_db")
            
        logger.info(f"Initializing persistent ChromaDB client at: {db_path}")
        try:
            self.client = chromadb.PersistentClient(path=db_path)
            # A Chroma collection fixes its dimensionality at creation, so a
            # change of embedding model REQUIRES a new collection name. The
            # old one stays on disk, which makes rollback an env-var flip.
            name = settings.CHROMA_COLLECTION
            self.collection = self.client.get_or_create_collection(
                name=name,
                metadata={"hnsw:space": "cosine"}
            )
            logger.info(f"ChromaDB collection {name!r} initialized ({self.collection.count()} vectors).")
        except Exception as e:
            logger.error(f"Error initializing ChromaDB PersistentClient: {e}")
            raise e
            
    def add_node_embeddings(
        self,
        node_ids: list[str],
        embeddings: list[list[float]],
        metadatas: list[dict],
        documents: list[str]
    ):
        if not node_ids:
            return
            
        try:
            # Ensure metadatas contain only strings, numbers or booleans
            sanitized_metadatas = []
            for meta in metadatas:
                # `node_id` stays the MongoDB node id even when the vector is
                # one chunk of that node, so everything downstream keeps
                # resolving real nodes. `chunk_index` distinguishes siblings.
                #
                # `section_type` is carried here so retrieval can filter and
                # weight by division without a MongoDB round-trip; it used to
                # live only in Mongo, which is why node_searcher returned "".
                sanitized = {
                    "node_id": str(meta.get("node_id", "")),
                    "file_id": str(meta.get("file_id", "")),
                    "parent_node_id": str(meta.get("parent_node_id", "") or ""),
                    "level": int(meta.get("level", 0)),
                    "heading": str(meta.get("heading", "")),
                    "section_type": str(meta.get("section_type", "") or ""),
                    "chunk_index": int(meta.get("chunk_index", 0)),
                    "chunk_count": int(meta.get("chunk_count", 1)),
                }
                sanitized_metadatas.append(sanitized)
                
            self.collection.add(
                ids=node_ids,
                embeddings=embeddings,
                metadatas=sanitized_metadatas,
                documents=documents
            )
            logger.info(f"Successfully added {len(node_ids)} vectors to ChromaDB.")
        except Exception as e:
            logger.error(f"Error adding vectors to ChromaDB: {e}")
            raise e
            
    def similarity_search_by_vector(self, query_vector: list[float], limit: int = 5) -> list[dict]:
        try:
            results = self.collection.query(
                query_embeddings=[query_vector],
                n_results=limit
            )
            
            retrieved = []
            if not results or not results.get("ids") or len(results["ids"]) == 0:
                return retrieved
                
            ids = results["ids"][0]
            distances = results.get("distances", [[]])[0]
            metadatas = results.get("metadatas", [[]])[0]
            documents = results.get("documents", [[]])[0]
            
            for idx in range(len(ids)):
                # Chroma returns distance (e.g. L2 distance or 1 - cosine_similarity).
                # For cosine distance, similarity is 1.0 - distance.
                dist = distances[idx] if distances else 0.0
                score = 1.0 - dist
                
                retrieved.append({
                    "node_id": ids[idx],
                    "score": float(score),
                    "metadata": metadatas[idx] if metadatas else {},
                    "text": documents[idx] if documents else ""
                })
                
            return retrieved
        except Exception as e:
            logger.error(f"Error during similarity search in ChromaDB: {e}")
            raise e
            
    def delete_by_file_id(self, file_id: str):
        try:
            self.collection.delete(where={"file_id": file_id})
            logger.info(f"Deleted vector records in Chroma for file_id: {file_id}")
        except Exception as e:
            logger.warning(f"Notice during Chroma vector deletion for file_id {file_id}: {e}")

    def reset_collection(self):
        """Drop and recreate the collection, discarding every vector.

        `collection.delete()` with no filter is a no-op in Chroma, so a full
        reset has to go through the client. Recreating also re-fixes the
        dimensionality, which is what makes an embedding-model change work.
        """
        name = settings.CHROMA_COLLECTION
        try:
            self.client.delete_collection(name=name)
            logger.info(f"Dropped Chroma collection {name!r}")
        except Exception as e:
            logger.warning(f"Collection {name!r} could not be dropped (may not exist): {e}")

        self.collection = self.client.get_or_create_collection(
            name=name, metadata={"hnsw:space": "cosine"}
        )
        logger.info(f"Recreated empty Chroma collection {name!r}")

    def delete_by_node_id(self, node_id: str):
        try:
            self.collection.delete(ids=[node_id])
            logger.info(f"Deleted vector record in Chroma for node_id: {node_id}")
        except Exception as e:
            logger.warning(f"Notice during Chroma vector deletion for node_id {node_id}: {e}")

chroma_store = ChromaStore()
