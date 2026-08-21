"""Bootstrap de configuración inicial: lectura de un ``hostfile.txt``
compartido y selección de peers seed para el JOIN.

Importante: esto es exclusivamente ayuda de arranque/configuración. La
propagación de membership entre peers sigue ocurriendo por red, vía
Gossip (:mod:`civicmesh.gossip.gossip`) — este módulo nunca sustituye eso;
solo entrega la lista inicial de endpoints y ayuda a elegir con cuáles
intentar el primer contacto (JOIN).
"""

from __future__ import annotations

import random
from collections.abc import Iterable
from pathlib import Path

from civicmesh.gossip.peer import PeerInfo

_EXPECTED_FIELDS = 3


def parse_hostfile(lines: Iterable[str]) -> list[PeerInfo]:
    """Parsea líneas con formato ``peer_id host port`` (una entrada por
    línea, separadas por espacios).

    Líneas vacías o que comienzan con ``#`` se ignoran. No realiza ningún
    I/O: recibe las líneas ya leídas, para ser fácilmente testeable sin
    filesystem.
    """
    peers: list[PeerInfo] = []
    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) != _EXPECTED_FIELDS:
            raise ValueError(f"línea de hostfile inválida (se esperaba 'peer_id host port'): {raw_line!r}")
        peer_id, host, port_str = parts
        try:
            port = int(port_str)
        except ValueError as exc:
            raise ValueError(f"puerto inválido en línea de hostfile: {raw_line!r}") from exc
        peers.append(PeerInfo(peer_id=peer_id, host=host, port=port))
    return peers


def load_hostfile(path: str | Path) -> list[PeerInfo]:
    """Lee un ``hostfile.txt`` desde disco y devuelve los peers definidos.

    Uso exclusivo de bootstrap: el archivo compartido (filesystem del
    clúster/Docker Compose) informa qué endpoints existen al arrancar,
    pero no participa en la propagación de membership en régimen, que es
    responsabilidad exclusiva de las rondas de Gossip por red.
    """
    text = Path(path).read_text(encoding="utf-8")
    return parse_hostfile(text.splitlines())


def select_seeds(
    peers: list[PeerInfo],
    self_id: str,
    max_seeds: int = 2,
    rng: random.Random | None = None,
) -> list[PeerInfo]:
    """Elige hasta ``max_seeds`` peers del hostfile para usar como seeds
    iniciales de JOIN, excluyendo al propio peer.

    ``rng`` permite determinismo en tests; por defecto no está sembrado.
    """
    if max_seeds <= 0:
        raise ValueError("max_seeds debe ser mayor a 0")
    candidates = [p for p in peers if p.peer_id != self_id]
    if len(candidates) <= max_seeds:
        return candidates
    rng = rng if rng is not None else random.Random()
    return rng.sample(candidates, max_seeds)
