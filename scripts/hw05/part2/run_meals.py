"""Launch the Meals STDIO server from any working directory."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))


if __name__ == "__main__":
    from src.mcp_servers.meals import main

    main()
