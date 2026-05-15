"""
KiRouter — local web app autorouter for KiCad.

Companion to the KiBridge plugin (https://github.com/IgmarMelis/kibridge).
Runs a local HTTP server on localhost:8765 by default. Browser UI for
visualizing the board, running an autorouter, and sending the result
back to KiCad.

Local-only by design: binds to 127.0.0.1, never to 0.0.0.0.
"""
__version__ = "1.0.6"
__product__ = "KiRouter"
__company__ = "PSS Tools"
