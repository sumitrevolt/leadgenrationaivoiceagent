"""
Vector Store for Semantic Search
Uses ChromaDB for storing and retrieving conversation embeddings

Features:
- Store conversation embeddings with metadata
- Semantic search for similar conversations
- Filter by industry, outcome, language
- Retrieve successful response patterns
- Support for RAG (Retrieval Augmented Generation)
"""
import json
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Any
from dataclasses import dataclass, field

from app.utils.logger import setup_logger

logger = setup_logger(__name__)


@dataclass
class SimilarConversation:
    """A similar conversation retrieved from vector store"""
    conversation_id: str
    similarity_score: float
    
    # Conversation details
    industry: str
    outcome: str
    language: str
    
    # Content
    user_message: str
    agent_response: str
    
    # Metadata
    created_at: datetime = None
    tenant_id: str = ""


class VectorStore:
    """
    ChromaDB-based vector store for conversation embeddings
    
    Enables:
    1. Store conversation turns with embeddings
    2. Semantic search for similar situations
    3. Filter by outcome (find successful patterns)
    4. RAG context retrieval
    """
    
    def __init__(
        self,
        persist_directory: str = "data/vectorstore",
        collection_name: str = "conversations"
    ):
        self.persist_directory = Path(persist_directory)
        self.persist_directory.mkdir(parents=True, exist_ok=True)
        
        self.collection_name = collection_name
        
        # Lazy load ChromaDB
        self._client = None
        self._collection = None
        self._embedder = None
        
        logger.info(f"📦 Vector store initialized: {persist_directory}")
    
    @property
    def client(self):
        """Lazy load ChromaDB client"""
        if self._client is None:
            try:
                import chromadb
                from chromadb.config import Settings
                
                self._client = chromadb.Client(Settings(
                    chroma_db_impl="duckdb+parquet",
                    persist_directory=str(self.persist_directory),
                    anonymized_telemetry=False
                ))
                
                logger.info("✅ ChromaDB client initialized")
            except ImportError:
                logger.warning("ChromaDB not installed, using mock store")
                self._client = MockChromaClient()
            except Exception as e:
                logger.warning(f"ChromaDB init failed: {e}, using mock store")
                self._client = MockChromaClient()
        
        return self._client
    
    @property
    def collection(self):
        """Get or create the conversations collection"""
        if self._collection is None:
            try:
                self._collection = self.client.get_or_create_collection(
                    name=self.collection_name,
                    metadata={"description": "Voice agent conversation embeddings"}
                )
            except Exception as e:
                logger.error(f"Failed to get collection: {e}")
                self._collection = MockCollection()
        
        return self._collection
    
    @property
    def embedder(self):
        """Lazy load embedding model"""
        if self._embedder is None:
            try:
                from sentence_transformers import SentenceTransformer
                # Multilingual model for Hindi/English
                self._embedder = SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')
                logger.info("🧠 Embedding model loaded")
            except ImportError:
                logger.warning("sentence-transformers not installed")
                self._embedder = MockEmbedder()
        
        return self._embedder
    
    def _generate_embedding(self, text: str) -> List[float]:
        """Generate embedding for text"""
        try:
            embedding = self.embedder.encode(text)
            return embedding.tolist()
        except Exception as e:
            logger.error(f"Embedding generation failed: {e}")
            return [0.0] * 384  # Default dimension
    
    async def add_conversation(
        self,
        conversation_id: str,
        user_message: str,
        agent_response: str,
        outcome: str,
        industry: str,
        language: str = "hinglish",
        tenant_id: str = "",
        intent: str = "",
        metadata: Dict = None
    ):
        """
        Add a conversation turn to the vector store
        
        Args:
            conversation_id: Unique identifier
            user_message: What the user said
            agent_response: How the agent responded
            outcome: Call outcome (appointment_booked, not_interested, etc.)
            industry: Lead's industry
            language: Conversation language
            tenant_id: Tenant identifier
            intent: Detected user intent
            metadata: Additional metadata
        """
        
        # Create combined text for embedding
        combined_text = f"User: {user_message}\nAgent: {agent_response}"
        
        # Generate embedding
        embedding = self._generate_embedding(combined_text)
        
        # Prepare metadata
        doc_metadata = {
            "user_message": user_message[:500],  # Truncate for storage
            "agent_response": agent_response[:500],
            "outcome": outcome,
            "industry": industry,
            "language": language,
            "tenant_id": tenant_id,
            "intent": intent,
            "created_at": datetime.now().isoformat(),
            **(metadata or {})
        }
        
        # Add to collection
        try:
            self.collection.add(
                ids=[conversation_id],
                embeddings=[embedding],
                metadatas=[doc_metadata],
                documents=[combined_text]
            )
            
            logger.debug(f"Added conversation to vector store: {conversation_id}")
            
        except Exception as e:
            logger.error(f"Failed to add to vector store: {e}")
    
    async def add_batch(
        self,
        conversations: List[Dict]
    ):
        """
        Add multiple conversations at once
        
        Args:
            conversations: List of conversation dicts with keys:
                - conversation_id, user_message, agent_response,
                - outcome, industry, language, tenant_id
        """
        
        ids = []
        embeddings = []
        metadatas = []
        documents = []
        
        for conv in conversations:
            conv_id = conv.get("conversation_id", "")
            user_msg = conv.get("user_message", "")
            agent_resp = conv.get("agent_response", "")
            
            combined = f"User: {user_msg}\nAgent: {agent_resp}"
            embedding = self._generate_embedding(combined)
            
            ids.append(conv_id)
            embeddings.append(embedding)
            documents.append(combined)
            metadatas.append({
                "user_message": user_msg[:500],
                "agent_response": agent_resp[:500],
                "outcome": conv.get("outcome", "unknown"),
                "industry": conv.get("industry", "general"),
                "language": conv.get("language", "hinglish"),
                "tenant_id": conv.get("tenant_id", ""),
                "created_at": datetime.now().isoformat()
            })
        
        try:
            self.collection.add(
                ids=ids,
                embeddings=embeddings,
                metadatas=metadatas,
                documents=documents
            )
            
            logger.info(f"Added {len(conversations)} conversations to vector store")
            
        except Exception as e:
            logger.error(f"Batch add failed: {e}")
    
    async def search_similar(
        self,
        query: str,
        industry: Optional[str] = None,
        outcome_filter: Optional[str] = None,  # "successful", "failed", or specific outcome
        language: Optional[str] = None,
        top_k: int = 5
    ) -> List[Dict]:
        """
        Search for similar conversations
        
        Args:
            query: Text to search for (user message or context)
            industry: Filter by industry (optional)
            outcome_filter: Filter by outcome type (optional)
            language: Filter by language (optional)
            top_k: Number of results to return
        
        Returns:
            List of similar conversations with scores
        """
        
        # Generate query embedding
        query_embedding = self._generate_embedding(query)
        
        # Build where filter
        where_filter = {}
        
        if industry:
            where_filter["industry"] = industry
        
        if outcome_filter:
            if outcome_filter == "successful":
                where_filter["outcome"] = {
                    "$in": ["appointment_booked", "callback_scheduled", "interested"]
                }
            elif outcome_filter == "failed":
                where_filter["outcome"] = {
                    "$in": ["not_interested", "dnd", "wrong_number"]
                }
            else:
                where_filter["outcome"] = outcome_filter
        
        if language:
            where_filter["language"] = language
        
        try:
            results = self.collection.query(
                query_embeddings=[query_embedding],
                n_results=top_k,
                where=where_filter if where_filter else None
            )
            
            # Format results
            similar = []
            
            if results and results.get("ids"):
                for i, conv_id in enumerate(results["ids"][0]):
                    metadata = results["metadatas"][0][i] if results.get("metadatas") else {}
                    distance = results["distances"][0][i] if results.get("distances") else 0
                    
                    # Convert distance to similarity score (1 = identical)
                    similarity = 1 / (1 + distance)
                    
                    similar.append({
                        "conversation_id": conv_id,
                        "score": similarity,
                        "user_message": metadata.get("user_message", ""),
                        "agent_response": metadata.get("agent_response", ""),
                        "outcome": metadata.get("outcome", ""),
                        "industry": metadata.get("industry", ""),
                        "language": metadata.get("language", "")
                    })
            
            return similar
            
        except Exception as e:
            logger.error(f"Vector search failed: {e}")
            return []
    
    async def find_best_response(
        self,
        user_message: str,
        industry: str,
        top_k: int = 3
    ) -> Optional[str]:
        """
        Find the best response for a user message based on successful outcomes
        
        Returns the most similar successful agent response
        """
        
        results = await self.search_similar(
            query=user_message,
            industry=industry,
            outcome_filter="successful",
            top_k=top_k
        )
        
        if results and results[0].get("score", 0) > 0.7:
            return results[0].get("agent_response")
        
        return None
    
    async def find_objection_responses(
        self,
        objection: str,
        industry: str = None,
        top_k: int = 5
    ) -> List[Dict]:
        """
        Find successful responses to similar objections
        """
        
        # Search specifically for objection patterns
        results = await self.search_similar(
            query=objection,
            industry=industry,
            outcome_filter="successful",
            top_k=top_k
        )
        
        # Filter for high similarity
        return [r for r in results if r.get("score", 0) > 0.5]
    
    def get_collection_stats(self) -> Dict:
        """Get vector store statistics"""
        
        try:
            count = self.collection.count()
            
            return {
                "total_documents": count,
                "collection_name": self.collection_name,
                "persist_directory": str(self.persist_directory)
            }
        except Exception as e:
            return {"error": str(e)}
    
    async def delete_old_entries(self, days_old: int = 90):
        """Delete entries older than specified days"""
        
        # This would require date-based filtering
        # ChromaDB doesn't have great support for this
        # Would need to implement with document iteration
        
        logger.info(f"Cleanup requested for entries > {days_old} days old")


# Mock classes for when dependencies aren't installed

class MockEmbedder:
    """Mock embedder when sentence-transformers not available"""
    
    def encode(self, text: str) -> List[float]:
        # Return a simple hash-based embedding
        import hashlib
        h = hashlib.md5(text.encode()).hexdigest()
        # Convert hex to floats
        embedding = []
        for i in range(0, len(h), 2):
            val = int(h[i:i+2], 16) / 255.0
            embedding.append(val)
        # Pad to 384 dimensions
        while len(embedding) < 384:
            embedding.append(0.0)
        return embedding[:384]


class MockCollection:
    """Mock ChromaDB collection"""
    
    def __init__(self):
        self.data = {
            "ids": [],
            "embeddings": [],
            "metadatas": [],
            "documents": []
        }
    
    def add(self, ids, embeddings, metadatas, documents):
        self.data["ids"].extend(ids)
        self.data["embeddings"].extend(embeddings)
        self.data["metadatas"].extend(metadatas)
        self.data["documents"].extend(documents)
    
    def query(self, query_embeddings, n_results, where=None):
        # Return empty results
        return {
            "ids": [[]],
            "embeddings": [[]],
            "metadatas": [[]],
            "distances": [[]]
        }
    
    def count(self):
        return len(self.data["ids"])


class MockChromaClient:
    """Mock ChromaDB client"""
    
    def __init__(self):
        self.collections = {}
    
    def get_or_create_collection(self, name, metadata=None):
        if name not in self.collections:
            self.collections[name] = MockCollection()
        return self.collections[name]


# Singleton instance
vector_store = VectorStore()
