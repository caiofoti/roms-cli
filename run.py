#!/usr/bin/env python
import logging
from pathlib import Path

from dotenv import load_dotenv

env_path = Path(".env")
if not env_path.exists():
    env_path = Path(__file__).parent / ".env"

load_dotenv(env_path)

from src.cli import main

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
    )
    main()
