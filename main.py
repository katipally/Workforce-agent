"""Main entry point for Workforce Agent CLI.

A comprehensive agent for managing and extracting data from:
- Slack (messages, users, channels, files, reactions)
- Gmail (emails, threads, labels, attachments)
- Notion (exporting data for documentation and collaboration)

Usage:
    python main.py [command] [options]
    
Examples:
    python main.py stats              # Show Slack statistics
    python main.py gmail-stats        # Show Gmail statistics
    python main.py extract-all        # Extract all Slack data
    python main.py gmail-extract      # Extract Gmail data
    python main.py export-to-notion   # Export to Notion

For full command list:
    python main.py --help
"""
import sys
from pathlib import Path

# Add backend/core to path so imports resolve
core_path = Path(__file__).parent / 'backend' / 'core'
sys.path.insert(0, str(core_path))

from cli.main import cli

if __name__ == "__main__":
    sys.exit(cli())
