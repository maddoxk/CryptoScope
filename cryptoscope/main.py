"""CryptoScope Terminal — entry point."""

from __future__ import annotations

import asyncio
import sys


def main() -> None:
    """CLI entry point."""
    try:
        from cryptoscope.app import CryptoScopeApp

        app = CryptoScopeApp()
        asyncio.run(app.run())
    except KeyboardInterrupt:
        print("\nGoodbye.")
        sys.exit(0)


if __name__ == "__main__":
    main()
