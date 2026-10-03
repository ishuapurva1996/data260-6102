"""Launch the HW5 rental server; stdout is reserved for MCP protocol messages."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from src.mcp_servers.rentals import main


if __name__ == "__main__":
    main()
