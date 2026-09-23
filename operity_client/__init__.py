"""Operity's Python client.

    from operity_client import Agent, Keypair, Principal

`Principal` registers and funds agents with an API key; `Agent` does
everything an agent does, signing each request with its own key. Seller output
comes back as typed data (`models.Delivery`), and this package contains no
helper that places it into a prompt — see models.py for why.
"""

from . import models
from .client import Agent, OperityError, Principal
from .signing import Keypair

__version__ = "0.1.0"
__all__ = ["Agent", "Keypair", "OperityError", "Principal", "models"]
