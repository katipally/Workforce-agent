"""Generate semantic embeddings for all existing data.

This script:
1. Loads the configured sentence-transformers embedding model
2. Generates embeddings for Slack messages
3. Generates embeddings for Gmail messages
4. Stores embeddings in database (generic embedding column)
"""

import sys
import os
from pathlib import Path
from tqdm import tqdm

# Add parent directory to path (backend/core for config + database)
PROJECT_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = PROJECT_ROOT / "backend"
CORE_ROOT = BACKEND_ROOT / "core"
for p in (BACKEND_ROOT, CORE_ROOT):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from agent.sentence_transformer_engine import SentenceTransformerEmbedding
from database.db_manager import DatabaseManager
from database.models import Message, GmailMessage
from utils.logger import get_logger
from config import Config

logger = get_logger(__name__)


def generate_slack_embeddings(embedding_model: SentenceTransformerEmbedding, db: DatabaseManager, batch_size: int = 32):
    """Generate embeddings for Slack messages.
    
    Args:
        embedding_model: Qwen3 embedding model
        db: Database manager
        batch_size: Number of messages to process at once
    """
    logger.info("Generating embeddings for Slack messages...")
    
    with db.get_session() as session:
        # Get messages without embeddings
        messages = session.query(Message)\
            .filter(Message.text.isnot(None))\
            .filter(Message.text != '')\
            .all()
        
        logger.info(f"Found {len(messages)} Slack messages")
        
        if len(messages) == 0:
            logger.info("No messages to process")
            return
        
        # Process in batches
        for i in tqdm(range(0, len(messages), batch_size), desc="Slack embeddings"):
            batch = messages[i:i+batch_size]
            
            # Extract texts
            texts = [msg.text for msg in batch]
            
            # Generate embeddings
            embeddings = embedding_model.encode(
                texts,
                batch_size=len(texts),
                is_query=False,  # These are documents, not queries
                show_progress=False
            )
            
            # Update database (generic embedding column)
            for msg, embedding in zip(batch, embeddings):
                # Store as list for PostgreSQL vector type
                msg.embedding = embedding.tolist()
            
            session.commit()
        
        logger.info(f"✓ Generated embeddings for {len(messages)} Slack messages")


def generate_gmail_embeddings(embedding_model: SentenceTransformerEmbedding, db: DatabaseManager, batch_size: int = 32):
    """Generate embeddings for Gmail messages.
    
    Args:
        embedding_model: Qwen3 embedding model
        db: Database manager
        batch_size: Number of messages to process at once
    """
    logger.info("Generating embeddings for Gmail messages...")
    
    with db.get_session() as session:
        # Get emails without embeddings
        emails = session.query(GmailMessage).all()
        
        logger.info(f"Found {len(emails)} Gmail messages")
        
        if len(emails) == 0:
            logger.info("No emails to process")
            return
        
        # Process in batches
        for i in tqdm(range(0, len(emails), batch_size), desc="Gmail embeddings"):
            batch = emails[i:i+batch_size]
            
            # Extract texts (combine subject and body)
            texts = []
            for email in batch:
                text = ""
                if email.subject:
                    text += email.subject + "\n\n"
                if email.body_text:
                    text += email.body_text[:1000]  # Limit to 1000 chars
                
                if not text.strip():
                    text = "Empty email"
                
                texts.append(text)
            
            # Generate embeddings
            embeddings = embedding_model.encode(
                texts,
                batch_size=len(texts),
                is_query=False,
                show_progress=False
            )
            
            # Update database (generic embedding column)
            for email, embedding in zip(batch, embeddings):
                email.embedding = embedding.tolist()
            
            session.commit()
        
        logger.info(f"✓ Generated embeddings for {len(emails)} Gmail messages")


def main():
    """Main function to generate all embeddings."""
    logger.info("=== Embedding Generation ===")
    logger.info("")
    
    # Initialize models
    logger.info(f"Loading {Config.EMBEDDING_MODEL} (GPU: {Config.USE_GPU})...")
    embedding_model = SentenceTransformerEmbedding(
        model_name=Config.EMBEDDING_MODEL,
        use_gpu=Config.USE_GPU,
    )
    
    # Initialize database
    db = DatabaseManager()
    
    # Generate embeddings
    logger.info("")
    generate_slack_embeddings(embedding_model, db, batch_size=Config.EMBEDDING_BATCH_SIZE)
    
    logger.info("")
    generate_gmail_embeddings(embedding_model, db, batch_size=Config.EMBEDDING_BATCH_SIZE)
    
    logger.info("")
    logger.info("=== Embedding Generation Complete ===")
    logger.info("")
    logger.info("Your data is now ready for AI agent queries!")
    logger.info("Start the API server: uvicorn backend.api.main:app --reload")


if __name__ == "__main__":
    main()
