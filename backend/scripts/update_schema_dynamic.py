#!/usr/bin/env python3
"""Update database schema based on configured embedding model."""

import sys
import os
from pathlib import Path

# Add core directory to Python path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root / 'backend' / 'core'))

from sqlalchemy import create_engine, text
from config import Config
from utils.logger import get_logger

logger = get_logger(__name__)


def get_embedding_dimension(model_name: str) -> int:
    """Get embedding dimension for a model."""
    # Qwen models
    if 'Qwen3-Embedding-8B' in model_name:
        return 8192
    elif 'Qwen' in model_name:
        return 1024  # Default for older Qwen models
    
    # Sentence Transformers models
    model_dims = {
        'all-MiniLM-L6-v2': 384,
        'all-MiniLM-L12-v2': 384,
        'all-mpnet-base-v2': 768,
        'multi-qa-MiniLM-L6-cos-v1': 384,
        'paraphrase-MiniLM-L6-v2': 384,
    }
    
    for key, dim in model_dims.items():
        if key in model_name:
            return dim
    
    # Default for unknown models
    logger.warning(f"Unknown model {model_name}, assuming 384 dimensions")
    return 384


def update_schema():
    """Update database schema for current embedding model."""
    logger.info("=" * 80)
    logger.info("DATABASE SCHEMA UPDATE - Dynamic Embedding Dimensions")
    logger.info("=" * 80)
    
    # Get embedding dimension
    embedding_dim = get_embedding_dimension(Config.EMBEDDING_MODEL)
    logger.info(f"Model: {Config.EMBEDDING_MODEL}")
    logger.info(f"Embedding dimension: {embedding_dim}")
    logger.info("")
    
    # Connect to database
    engine = create_engine(Config.DATABASE_URL)
    
    # Check if pgvector is available (separate transaction to avoid abort)
    has_pgvector = False
    try:
        with engine.begin() as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            has_pgvector = True
            logger.info("✓ pgvector extension available")
    except Exception as e:
        logger.warning(
            "pgvector extension not available - will use JSON storage for embeddings. "
            "For better performance, install pgvector: brew install pgvector"
        )
        has_pgvector = False
    
    # Now run schema updates in separate transaction
    with engine.begin() as conn:
        try:
            # =================================================================
            # UPDATE MESSAGES TABLE
            # =================================================================
            logger.info("Updating 'messages' table...")
            
            # Check if column exists
            result = conn.execute(text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'messages' 
                AND column_name = 'embedding'
            """))
            
            has_old = conn.execute(text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'messages' 
                AND column_name = 'embedding_old'
            """)).fetchone()
            
            if result.fetchone() and not has_old:
                logger.info("  Renaming old 'embedding' column...")
                conn.execute(text("ALTER TABLE messages RENAME COLUMN embedding TO embedding_old"))
            elif has_old:
                logger.info("  Dropping old 'embedding' column if exists...")
                conn.execute(text("ALTER TABLE messages DROP COLUMN IF EXISTS embedding"))
            
            # Add new embedding column
            if has_pgvector:
                logger.info(f"  Adding embedding column as vector({embedding_dim})...")
                conn.execute(text(f"""
                    ALTER TABLE messages 
                    ADD COLUMN IF NOT EXISTS embedding vector({embedding_dim})
                """))
            else:
                logger.info(f"  Adding embedding column as JSON (pgvector unavailable)...")
                conn.execute(text("""
                    ALTER TABLE messages 
                    ADD COLUMN IF NOT EXISTS embedding JSON
                """))
            
            # Drop old indexes
            logger.info("  Dropping old indexes...")
            conn.execute(text("DROP INDEX IF EXISTS messages_qwen_embedding_idx"))
            conn.execute(text("DROP INDEX IF EXISTS messages_embedding_idx"))
            
            # Create index (HNSW if pgvector, GIN if JSON)
            if has_pgvector:
                logger.info("  Creating HNSW vector index...")
                try:
                    conn.execute(text(f"""
                        CREATE INDEX IF NOT EXISTS messages_embedding_idx 
                        ON messages 
                        USING hnsw (embedding vector_cosine_ops)
                        WITH (m = 16, ef_construction = 64)
                    """))
                except Exception as e:
                    logger.warning(f"  Could not create HNSW index (may already exist): {e}")
            else:
                logger.info("  Skipping vector index (JSON storage doesn't support HNSW)")
            
            logger.info("  ✓ Messages table updated")
            
            # =================================================================
            # UPDATE GMAIL_MESSAGES TABLE
            # =================================================================
            logger.info("")
            logger.info("Updating 'gmail_messages' table...")
            
            # Check if column exists
            result = conn.execute(text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'gmail_messages' 
                AND column_name = 'embedding'
            """))
            
            has_old = conn.execute(text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'gmail_messages' 
                AND column_name = 'embedding_old'
            """)).fetchone()
            
            if result.fetchone() and not has_old:
                logger.info("  Renaming old 'embedding' column...")
                conn.execute(text("ALTER TABLE gmail_messages RENAME COLUMN embedding TO embedding_old"))
            elif has_old:
                logger.info("  Dropping old 'embedding' column if exists...")
                conn.execute(text("ALTER TABLE gmail_messages DROP COLUMN IF EXISTS embedding"))
            
            # Add new embedding column
            if has_pgvector:
                logger.info(f"  Adding embedding column as vector({embedding_dim})...")
                conn.execute(text(f"""
                    ALTER TABLE gmail_messages 
                    ADD COLUMN IF NOT EXISTS embedding vector({embedding_dim})
                """))
            else:
                logger.info(f"  Adding embedding column as JSON (pgvector unavailable)...")
                conn.execute(text("""
                    ALTER TABLE gmail_messages 
                    ADD COLUMN IF NOT EXISTS embedding JSON
                """))
            
            # Drop old indexes
            logger.info("  Dropping old indexes...")
            conn.execute(text("DROP INDEX IF EXISTS gmail_messages_qwen_embedding_idx"))
            conn.execute(text("DROP INDEX IF EXISTS gmail_messages_embedding_idx"))
            
            # Create index (HNSW if pgvector, GIN if JSON)
            if has_pgvector:
                logger.info("  Creating HNSW vector index...")
                try:
                    conn.execute(text(f"""
                        CREATE INDEX IF NOT EXISTS gmail_messages_embedding_idx 
                        ON gmail_messages 
                        USING hnsw (embedding vector_cosine_ops)
                        WITH (m = 16, ef_construction = 64)
                    """))
                except Exception as e:
                    logger.warning(f"  Could not create HNSW index (may already exist): {e}")
            else:
                logger.info("  Skipping vector index (JSON storage doesn't support HNSW)")
            
            logger.info("  ✓ Gmail messages table updated")
            
            # Transaction will auto-commit on context exit
            logger.info("")
            logger.info("=" * 80)
            logger.info("✓ DATABASE SCHEMA UPDATE COMPLETE")
            logger.info("=" * 80)
            logger.info("")
            logger.info("Next steps:")
            logger.info("1. Run: python backend/scripts/generate_embeddings.py")
            logger.info("2. Start the API server")
            
        except Exception as e:
            logger.error(f"✗ Schema update failed: {e}")
            raise


if __name__ == '__main__':
    update_schema()
