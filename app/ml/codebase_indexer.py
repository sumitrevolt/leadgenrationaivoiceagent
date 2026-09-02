"""
Codebase Indexer - Embed Project Files for Agent RAG
Indexes the codebase into vector store for context-aware agent suggestions

Features:
- Incremental indexing (only changed files)
- Multi-language support (Python, TypeScript, Terraform, Markdown)
- Chunking for large files
- Metadata extraction (imports, functions, classes)
- Scheduled re-indexing
"""

import asyncio
import hashlib
import json
import os
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from app.ml.agent_brain import AGENT_KNOWLEDGE_MAP
from app.ml.vector_store import VectorStore
from app.utils.logger import setup_logger

logger = setup_logger(__name__)


@dataclass
class FileChunk:
    """A chunk of a file for embedding"""

    file_path: str
    chunk_index: int
    content: str
    start_line: int
    end_line: int

    # Metadata
    language: str = "text"
    file_type: str = "unknown"
    agent_domain: str = ""

    # Extracted info
    functions: list[str] = field(default_factory=list)
    classes: list[str] = field(default_factory=list)
    imports: list[str] = field(default_factory=list)


@dataclass
class IndexingStats:
    """Statistics from an indexing run"""

    files_processed: int = 0
    files_skipped: int = 0
    chunks_created: int = 0
    errors: int = 0
    duration_seconds: float = 0.0


# File patterns to index
INCLUDE_PATTERNS = [
    "**/*.py",
    "**/*.ts",
    "**/*.tsx",
    "**/*.js",
    "**/*.jsx",
    "**/*.tf",
    "**/*.yaml",
    "**/*.yml",
    "**/*.md",
    "**/*.json",
    "**/*.toml",
]

# Directories to exclude
EXCLUDE_DIRS = {
    "__pycache__",
    "node_modules",
    ".git",
    ".venv",
    "venv",
    ".pytest_cache",
    ".mypy_cache",
    "dist",
    "build",
    ".next",
    "coverage",
}

# File extensions to language mapping
LANGUAGE_MAP = {
    ".py": "python",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".js": "javascript",
    ".jsx": "javascript",
    ".tf": "terraform",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".md": "markdown",
    ".json": "json",
    ".toml": "toml",
}

# Parses the per-chunk locator stored in user_message ("Code from <file> lines A-B").
_LOC_RE = re.compile(r"Code from (.+?) lines (\d+)-(\d+)")


class QdrantCodeIndex:
    """Qdrant + fastembed code index — project ke PROD vector-stack ko reuse karta
    (`app.voice_agent.knowledge_base` ka embedder + client). Alag collection
    `code_index` (business KB `kb_main` ko KABHI touch nahi). e5 prefixes
    (`passage:`/`query:`), deterministic point-ids (re-index = overwrite, dupes nahi).
    never-raise.

    Kyun: `VectorStore` (ChromaDB + sentence-transformers) prod container me INSTALLED
    NAHI → mock-store → code_search hamesha []. fastembed (241M baked) + Qdrant
    (127.0.0.1:6333) prod me LIVE hain — yeh unpe chalta, isliye code-search prod me
    actually kaam karta.
    """

    _COLLECTION = "code_index"
    _UUID_NS = uuid.UUID("c0de1dec-0000-4000-8000-000000000001")

    def __init__(self) -> None:
        self._client = None
        self._embedder = None
        self._dim = 0
        self._ready = False

    def _setup(self):
        """Lazy: embedder + client + collection ensure. Qdrant/embedder unavailable
        ho to raise karta (caller fallback pe chala jaata)."""
        if self._ready:
            return
        from app.voice_agent import knowledge_base as kb

        embedder = (
            kb._get_qdrant_embedder()
        )  # daemon-thread load + hard timeout; raises if disabled
        client = kb._get_qdrant_client()
        dim = int(getattr(kb, "_QDRANT_VECTOR_SIZE", 0) or 0)
        if dim <= 0:
            dim = len(list(embedder.embed(["x"]))[0])
        from qdrant_client import models as qmodels

        try:
            if not client.collection_exists(self._COLLECTION):
                client.create_collection(
                    collection_name=self._COLLECTION,
                    vectors_config=qmodels.VectorParams(size=dim, distance=qmodels.Distance.COSINE),
                )
                for f in ("agent_domain", "language"):
                    try:
                        client.create_payload_index(
                            collection_name=self._COLLECTION,
                            field_name=f,
                            field_schema=qmodels.PayloadSchemaType.KEYWORD,
                        )
                    except Exception:
                        pass
        except Exception as e:  # collection race / transient — search still works
            logger.debug(f"code_index collection ensure: {e}")
        self._client, self._embedder, self._dim, self._ready = client, embedder, dim, True

    def _embed(self, text: str) -> list[float]:
        return [float(x) for x in next(iter(self._embedder.embed([text])))]

    def add_chunks(self, chunks) -> int:
        """SYNC bulk upsert (caller `asyncio.to_thread` me wrap kare). never-raise.
        Idempotent ids → re-index overwrite karta, duplicate nahi."""
        try:
            self._setup()
            from qdrant_client import models as qmodels

            pts = []
            for c in chunks:
                cid = f"{c.file_path}:{c.chunk_index}"
                pts.append(
                    qmodels.PointStruct(
                        id=str(uuid.uuid5(self._UUID_NS, cid)),
                        vector=self._embed(f"passage: {c.content}"),
                        payload={
                            "file_path": c.file_path,
                            "chunk_index": c.chunk_index,
                            "start_line": c.start_line,
                            "end_line": c.end_line,
                            "language": c.language,
                            "agent_domain": c.agent_domain,
                            "content": c.content[:5000],
                        },
                    )
                )
            if pts:
                self._client.upsert(collection_name=self._COLLECTION, points=pts)
            return len(pts)
        except Exception as e:
            logger.debug(f"QdrantCodeIndex.add_chunks failed: {e}")
            return 0

    def search_sync(
        self, query: str, agent_domain=None, language=None, limit: int = 10
    ) -> list[dict]:
        """SYNC search (caller `to_thread` + timeout me wrap kare). never-raise."""
        try:
            self._setup()
            from qdrant_client import models as qmodels

            must = []
            if agent_domain:
                must.append(
                    qmodels.FieldCondition(
                        key="agent_domain", match=qmodels.MatchValue(value=agent_domain)
                    )
                )
            if language:
                must.append(
                    qmodels.FieldCondition(key="language", match=qmodels.MatchValue(value=language))
                )
            res = self._client.query_points(
                collection_name=self._COLLECTION,
                query=self._embed(f"query: {query}"),
                query_filter=qmodels.Filter(must=must) if must else None,
                limit=max(1, int(limit or 10)),
                with_payload=True,
            )
            out: list[dict] = []
            for p in getattr(res, "points", None) or []:
                pl = getattr(p, "payload", None) or {}
                fp = str(pl.get("file_path", "") or "")
                if not fp:
                    continue
                out.append(
                    {
                        "file": fp,
                        "start_line": int(pl.get("start_line", 0) or 0),
                        "end_line": int(pl.get("end_line", 0) or 0),
                        "score": round(float(getattr(p, "score", 0.0) or 0.0), 4),
                        "snippet": str(pl.get("content", "") or "")[:1200],
                        "language": str(pl.get("language", "") or ""),
                        "domain": str(pl.get("agent_domain", "") or ""),
                    }
                )
            return out
        except Exception as e:
            logger.debug(f"QdrantCodeIndex.search failed: {e}")
            return []


class CodebaseIndexer:
    """
    Indexes the project codebase for agent RAG

    Enables agents to:
    1. Find similar code patterns
    2. Understand project conventions
    3. Learn from existing implementations
    4. Reference documentation
    """

    def __init__(
        self,
        project_root: str = ".",
        vector_store: VectorStore = None,
        chunk_size: int = 100,  # lines per chunk
        chunk_overlap: int = 10,  # overlapping lines
    ):
        self.project_root = Path(project_root).resolve()
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

        self._vector_store = vector_store
        self._qdrant_index = None  # prod stack (fastembed+Qdrant); None → ChromaDB fallback

        # Track indexed files (path -> hash)
        self.index_cache: dict[str, str] = {}
        self.cache_file = self.project_root / "data" / "agent_brain" / "index_cache.json"
        self._load_cache()

        logger.info(f"📂 Codebase indexer initialized for: {self.project_root}")

    @property
    def vector_store(self) -> VectorStore:
        """Lazy load vector store (ChromaDB — local-dev / fallback)."""
        if self._vector_store is None:
            self._vector_store = VectorStore(
                persist_directory="data/agent_vectorstore", collection_name="code_patterns"
            )
        return self._vector_store

    def _qdrant(self):
        """Prod code-index (fastembed+Qdrant) jab QDRANT_URL set ho; warna None
        (ChromaDB fallback). Cached. never-raise."""
        if self._qdrant_index is None:
            try:
                from app.config import settings

                if (getattr(settings, "qdrant_url", "") or "").strip():
                    self._qdrant_index = QdrantCodeIndex()
            except Exception:
                self._qdrant_index = None
        return self._qdrant_index

    def _load_cache(self):
        """Load index cache from disk"""
        if self.cache_file.exists():
            try:
                with open(self.cache_file) as f:
                    self.index_cache = json.load(f)
                logger.info(f"📚 Loaded index cache: {len(self.index_cache)} files")
            except Exception as e:
                logger.warning(f"Failed to load cache: {e}")

    def _save_cache(self):
        """Save index cache to disk"""
        try:
            self.cache_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.cache_file, "w") as f:
                json.dump(self.index_cache, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save cache: {e}")

    def _get_file_hash(self, file_path: Path) -> str:
        """Get MD5 hash of file content"""
        try:
            content = file_path.read_bytes()
            return hashlib.md5(content).hexdigest()
        except Exception:
            return ""

    def _should_skip_dir(self, dir_name: str) -> bool:
        """Check if directory should be skipped"""
        return dir_name in EXCLUDE_DIRS or dir_name.startswith(".")

    def _detect_agent_domain(self, file_path: str) -> str:
        """Detect which agent domain a file belongs to"""
        file_path_lower = file_path.lower().replace("\\", "/")

        for role, config in AGENT_KNOWLEDGE_MAP.items():
            for pattern in config["file_patterns"]:
                pattern_clean = pattern.replace("**", "").replace("*", "").lower()
                if pattern_clean in file_path_lower:
                    return role.value

        return "general"

    def _extract_python_metadata(self, content: str) -> dict:
        """Extract metadata from Python file"""
        imports = []
        functions = []
        classes = []

        for line in content.split("\n"):
            line_stripped = line.strip()

            # Imports
            if line_stripped.startswith("import ") or line_stripped.startswith("from "):
                imports.append(line_stripped)

            # Function definitions
            if line_stripped.startswith("def "):
                func_name = line_stripped[4:].split("(")[0]
                functions.append(func_name)

            # Class definitions
            if line_stripped.startswith("class "):
                class_name = line_stripped[6:].split("(")[0].split(":")[0]
                classes.append(class_name)

        return {
            "imports": imports[:20],  # Limit
            "functions": functions[:50],
            "classes": classes[:20],
        }

    def _extract_typescript_metadata(self, content: str) -> dict:
        """Extract metadata from TypeScript/JavaScript file"""
        imports = []
        functions = []
        classes = []

        for line in content.split("\n"):
            line_stripped = line.strip()

            # Imports
            if line_stripped.startswith("import "):
                imports.append(line_stripped)

            # Function definitions
            if (
                "function " in line_stripped
                or line_stripped.startswith("const ")
                or line_stripped.startswith("export ")
            ):
                if "=>" in line_stripped or "function" in line_stripped:
                    # Extract function name
                    parts = line_stripped.split()
                    for i, part in enumerate(parts):
                        if part in ["function", "const", "let", "var"] and i + 1 < len(parts):
                            func_name = parts[i + 1].split("(")[0].split("=")[0].strip()
                            if func_name and func_name.isidentifier():
                                functions.append(func_name)
                            break

            # Class/interface definitions
            if line_stripped.startswith("class ") or line_stripped.startswith("interface "):
                parts = line_stripped.split()
                if len(parts) >= 2:
                    classes.append(parts[1].split("{")[0])

        return {
            "imports": imports[:20],
            "functions": functions[:50],
            "classes": classes[:20],
        }

    def _chunk_file(self, file_path: Path, content: str) -> list[FileChunk]:
        """Split file into chunks for embedding"""
        lines = content.split("\n")
        chunks = []

        # Get language and metadata
        ext = file_path.suffix.lower()
        language = LANGUAGE_MAP.get(ext, "text")
        agent_domain = self._detect_agent_domain(str(file_path))

        # Extract metadata based on language
        if language == "python":
            metadata = self._extract_python_metadata(content)
        elif language in ["typescript", "javascript"]:
            metadata = self._extract_typescript_metadata(content)
        else:
            metadata = {"imports": [], "functions": [], "classes": []}

        # Create chunks
        start = 0
        chunk_index = 0

        while start < len(lines):
            end = min(start + self.chunk_size, len(lines))
            chunk_content = "\n".join(lines[start:end])

            # Skip empty chunks
            if chunk_content.strip():
                chunk = FileChunk(
                    file_path=str(file_path.relative_to(self.project_root)),
                    chunk_index=chunk_index,
                    content=chunk_content,
                    start_line=start + 1,
                    end_line=end,
                    language=language,
                    file_type=ext,
                    agent_domain=agent_domain,
                    functions=metadata["functions"],
                    classes=metadata["classes"],
                    imports=metadata["imports"],
                )
                chunks.append(chunk)
                chunk_index += 1

            start = end - self.chunk_overlap
            if start >= len(lines) - self.chunk_overlap:
                break

        return chunks

    def get_files_to_index(self) -> list[Path]:
        """Get list of files that need indexing"""
        files_to_index = []

        for root, dirs, files in os.walk(self.project_root):
            # Filter directories
            dirs[:] = [d for d in dirs if not self._should_skip_dir(d)]

            for file in files:
                file_path = Path(root) / file
                ext = file_path.suffix.lower()

                # Check if file type should be indexed
                if ext not in LANGUAGE_MAP:
                    continue

                # Check if file has changed
                rel_path = str(file_path.relative_to(self.project_root))
                file_hash = self._get_file_hash(file_path)

                if rel_path not in self.index_cache or self.index_cache[rel_path] != file_hash:
                    files_to_index.append(file_path)

        return files_to_index

    async def index_file(self, file_path: Path) -> int:
        """
        Index a single file

        Returns:
            Number of chunks indexed
        """
        try:
            content = file_path.read_text(encoding="utf-8", errors="ignore")
            chunks = self._chunk_file(file_path, content)

            # PROD path: fastembed+Qdrant (off-loop). Embedding CPU-bound hai isliye
            # to_thread — event loop block na ho.
            qi = self._qdrant()
            indexed_q = 0
            if qi is not None and chunks:
                indexed_q = await asyncio.to_thread(qi.add_chunks, chunks)

            # ChromaDB fallback (local-dev) — Qdrant unset YA Qdrant add fail hua to.
            if qi is None or (chunks and indexed_q == 0):
                for chunk in chunks:
                    chunk_id = f"{chunk.file_path}:{chunk.chunk_index}"
                    await self.vector_store.add_conversation(
                        conversation_id=chunk_id,
                        user_message=f"Code from {chunk.file_path} lines {chunk.start_line}-{chunk.end_line}",
                        agent_response=chunk.content,
                        outcome="indexed",
                        industry=chunk.agent_domain,
                        language=chunk.language,
                        tenant_id="codebase",
                        intent="code_pattern",
                        metadata={
                            "file_path": chunk.file_path,
                            "chunk_index": chunk.chunk_index,
                            "start_line": chunk.start_line,
                            "end_line": chunk.end_line,
                            "functions": chunk.functions[:10],
                            "classes": chunk.classes[:5],
                            "file_type": chunk.file_type,
                        },
                    )

            # Update cache
            rel_path = str(file_path.relative_to(self.project_root))
            self.index_cache[rel_path] = self._get_file_hash(file_path)

            return len(chunks)

        except Exception as e:
            logger.error(f"Failed to index {file_path}: {e}")
            return 0

    async def index_codebase(
        self, force_reindex: bool = False, max_files: int = None
    ) -> IndexingStats:
        """
        Index the entire codebase

        Args:
            force_reindex: If True, reindex all files regardless of cache
            max_files: Maximum files to index (for testing)

        Returns:
            Indexing statistics
        """
        start_time = datetime.now()
        stats = IndexingStats()

        if force_reindex:
            self.index_cache = {}

        files = self.get_files_to_index()
        if max_files:
            files = files[:max_files]

        logger.info(f"📚 Indexing {len(files)} files...")

        for file_path in files:
            try:
                chunks = await self.index_file(file_path)
                if chunks > 0:
                    stats.files_processed += 1
                    stats.chunks_created += chunks
                else:
                    stats.files_skipped += 1
            except Exception as e:
                logger.error(f"Error indexing {file_path}: {e}")
                stats.errors += 1

        # Save cache
        self._save_cache()

        stats.duration_seconds = (datetime.now() - start_time).total_seconds()

        logger.info(
            f"✅ Indexing complete: {stats.files_processed} files, "
            f"{stats.chunks_created} chunks in {stats.duration_seconds:.1f}s"
        )

        return stats

    async def search_code(
        self, query: str, agent_domain: str = None, language: str = None, limit: int = 10
    ) -> list[dict]:
        """
        Search indexed code (semantic) → normalized hits for agents.

        Args:
            query: Search query
            agent_domain: Filter by agent domain (stored as `industry` on chunks)
            language: Filter by language (e.g., "python", "typescript")
            limit: Max results

        Returns:
            List of {file, start_line, end_line, score, snippet, language, domain}.
            Empty list on any error / empty index (never raises).
        """
        # PROD path first: fastembed+Qdrant (off-loop + bounded). Hits mile → return;
        # warna ChromaDB fallback (local-dev). Prod me ChromaDB mock → [] anyway.
        qi = self._qdrant()
        if qi is not None:
            try:
                hits = await asyncio.wait_for(
                    asyncio.to_thread(
                        qi.search_sync, query, agent_domain, language, max(1, int(limit or 10))
                    ),
                    timeout=12,
                )
                if hits:
                    return hits
            except Exception as e:  # qdrant down / slow → graceful fallback
                logger.debug(f"qdrant code search fallback: {e}")
        try:
            # Chunks are stored via VectorStore.add_conversation with
            # industry=agent_domain, language=<lang>, user_message="Code from <file>
            # lines A-B", agent_response=<code>. Use the real search_similar() API
            # (earlier code called a non-existent .search() → orphan/never-wired).
            raw = await self.vector_store.search_similar(
                query=query,
                industry=agent_domain or None,
                language=language or None,
                top_k=max(1, int(limit or 10)),
            )
        except Exception as e:
            logger.error(f"Code search failed: {e}")
            return []

        hits: list[dict] = []
        for r in raw or []:
            cid = str(r.get("conversation_id", "") or "")
            msg = str(r.get("user_message", "") or "")
            snippet = str(r.get("agent_response", "") or "")

            file_path, start_line, end_line = "", 0, 0
            m = _LOC_RE.search(msg)
            if m:
                file_path = m.group(1)
                try:
                    start_line, end_line = int(m.group(2)), int(m.group(3))
                except Exception:
                    pass
            elif ":" in cid:
                # id == "<file>:<chunk_index>"
                file_path = cid.rsplit(":", 1)[0]

            if not file_path:
                continue

            hits.append(
                {
                    "file": file_path,
                    "start_line": start_line,
                    "end_line": end_line,
                    "score": round(float(r.get("score") or 0.0), 4),
                    "snippet": snippet[:1200],
                    "language": r.get("language", ""),
                    "domain": r.get("industry", ""),
                }
            )
        return hits

    def get_index_stats(self) -> dict:
        """Get statistics about the index"""
        return {
            "indexed_files": len(self.index_cache),
            "project_root": str(self.project_root),
            "cache_file": str(self.cache_file),
        }


# Singleton instance
_indexer_instance = None


def get_codebase_indexer() -> CodebaseIndexer:
    """Get or create the singleton CodebaseIndexer instance"""
    global _indexer_instance
    if _indexer_instance is None:
        _indexer_instance = CodebaseIndexer()
    return _indexer_instance


async def run_indexing():
    """CLI entry point for indexing"""
    indexer = get_codebase_indexer()
    stats = await indexer.index_codebase()
    print(f"Indexing complete: {stats}")


if __name__ == "__main__":
    asyncio.run(run_indexing())
