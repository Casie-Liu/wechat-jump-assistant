"""Separate immutable bundled resources from persistent user data."""
import os
from pathlib import Path
import sys


def resource_path(relative):
    # PyInstaller sets module __file__ inside its extraction directory.
    return Path(__file__).resolve().parent / relative


def data_dir():
    if getattr(sys, 'frozen', False):
        local = os.environ.get('LOCALAPPDATA')
        return (Path(local) if local else Path.home()/'AppData'/'Local')/'WeChatJumpAssistant'
    return Path(__file__).resolve().parent
