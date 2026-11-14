"""Compatibility entry point; prefer python -m src.run --stage improve."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.improvement import main

if __name__ == "__main__":
    main()
