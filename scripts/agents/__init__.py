"""Agentes automatizados auxiliares de CivicMesh (documentador, revisor de
bugs, revisor de Pull Requests).

Ninguno de estos agentes aprueba ni fusiona Pull Requests, hace push
directo a ``main``, ni decide cambios de protocolo o semántica
distribuida (Gossip, membership, Pub/Sub, ``should_forward``, TTL,
prioridad). Esas decisiones quedan siempre para revisión humana. Ver
``scripts/agents/README.md`` para el detalle de cada agente.
"""
