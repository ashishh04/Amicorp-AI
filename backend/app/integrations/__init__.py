"""Adapters for outside systems, one package per system. Modules depend on their own ports, never on
these packages; the worker and the app factory choose an adapter from settings.

INTEGRATIONS=fake (local and test only) selects synthetic stand-ins, so every workflow runs on a laptop.
"""
