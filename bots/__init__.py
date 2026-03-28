from contextlib import suppress

from .base import BaseBot, api_process

with suppress(Exception):
    from .fastapi import FastAPI
with suppress(Exception):
    from .napcat import NapCat
