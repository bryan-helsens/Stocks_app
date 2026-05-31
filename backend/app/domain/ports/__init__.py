"""Domain ports — abstract interfaces (Protocols) for outside-world adapters.

The domain and application layers depend only on these Protocols, never on
concrete implementations. Adapters in ``app.infrastructure`` implement them.
This is the dependency-inversion boundary that keeps brokers, market-data and
AI providers swappable (architecture principle #2).
"""
