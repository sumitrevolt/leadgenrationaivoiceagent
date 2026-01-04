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
import os
import hashlib
import json
import asyncio
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set
from dataclasses import dataclass, field

from app.utils.logger import setup_logger
from app.ml.vector_store import VectorStore
from app.ml.agent_brain import AgentRole, AGENT_KNOWLEDGE_MAP

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
    functions: List[str] = field(default_factory=list)
    classes: List[str] = field(default_factory=list)
    imports: List[str] = field(default_factory=list)


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
        
        # Track indexed files (path -> hash)
        self.index_cache: Dict[str, str] = {}
        self.cache_file = self.project_root / "data" / "agent_brain" / "index_cache.json"
        self._load_cache()
        
        logger.info(f"📂 Codebase indexer initialized for: {self.project_root}")
    
    @property
    def vector_store(self) -> VectorStore:
        """Lazy load vector store"""
        if self._vector_store is None:
            self._vector_store = VectorStore(
                persist_directory="data/agent_vectorstore",
                collection_name="code_patterns"
            )
        return self._vector_store
    
    def _load_cache(self):
        """Load index cache from disk"""
        if self.cache_file.exists():
            try:
                with open(self.cache_file, "r") as f:
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
    
    def _extract_python_metadata(self, content: str) -> Dict:
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
    
    def _extract_typescript_metadata(self, content: str) -> Dict:
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
            if "function " in line_stripped or line_stripped.startswith("const ") or line_stripped.startswith("export "):
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
    
    def _chunk_file(self, file_path: Path, content: str) -> List[FileChunk]:
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
    
    def get_files_to_index(self) -> List[Path]:
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
            
            for chunk in chunks:
                # Create unique ID for chunk
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
                    }
                )
            
            # Update cache
            rel_path = str(file_path.relative_to(self.project_root))
            self.index_cache[rel_path] = self._get_file_hash(file_path)
            
            return len(chunks)
            
        except Exception as e:
            logger.error(f"Failed to index {file_path}: {e}")
            return 0
    
    async def index_codebase(
        self,
        force_reindex: bool = False,
        max_files: int = None
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
        self,
        query: str,
        agent_domain: str = None,
        language: str = None,
        limit: int = 10
    ) -> List[Dict]:
        """
        Search indexed code
        
        Args:
            query: Search query
            agent_domain: Filter by agent domain (e.g., "voice_ai", "billing")
            language: Filter by language (e.g., "python", "typescript")
            limit: Max results
        
        Returns:
            List of matching code chunks with metadata
        """
        try:
            # Build filter
            filter_metadata = {}
            if agent_domain:
                filter_metadata["industry"] = agent_domain
            if language:
                filter_metadata["language"] = language
            
            results = await self.vector_store.search(
                query=query,
                limit=limit,
                filter_metadata=filter_metadata if filter_metadata else None
            )
            
            return results
            
        except Exception as e:
            logger.error(f"Code search failed: {e}")
            return []
    
    def get_index_stats(self) -> Dict:
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
