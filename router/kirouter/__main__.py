"""
Entry point so users can run:

    python -m kirouter

This starts the KiRouter HTTP server on localhost:8765 and (optionally)
opens a browser to it.
"""
from .server import main

if __name__ == "__main__":
    main()
