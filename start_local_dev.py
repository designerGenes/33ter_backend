#!/usr/bin/env python3

import sys
import os

# Add the app directory to Python path to allow imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.terminal_hub import main

if __name__ == "__main__":
    main()
