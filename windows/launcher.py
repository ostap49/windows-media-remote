"""Entry script for the PyInstaller executable (it cannot run a package's __main__ directly)."""
from winmediaremote.__main__ import cli

cli()
