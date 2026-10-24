"""Configuration consumed by the production application."""
import os

DEBUG = bool(os.getenv("DEBUG", "false"))
