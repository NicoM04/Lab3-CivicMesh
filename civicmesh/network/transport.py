"""Transporte TCP/JSON mínimo para Gossip y Pub/Sub."""

from __future__ import annotations

import json
import socket
import threading
import time

from collections.abc import Callable
from typing import Any

from civicmesh.gossip.messages import GossipPayload
from civicmesh.gossip.peer import PeerInfo
from civicmesh.pubsub.models import Message


EnvelopeHandler = Callable[
    [dict[str, Any]],
    dict[str, Any] | None,
]


class TCPTransport:
    """Servidor/cliente TCP sencillo para CivicMesh."""

    def __init__(
        self,
        host: str,
        port: int,
        *,
        peer_id: str | None = None,
        timeout: float = 2.0,
        high_priority_threshold: int = 10,
        simulate_first_send_failure: bool = False,
    ) -> None:

        self.host = host
        self.port = int(port)
        self.peer_id = peer_id

        self.timeout = float(
            timeout
        )

        self.high_priority_threshold = int(
            high_priority_threshold
        )

        self._handler: (
            EnvelopeHandler | None
        ) = None

        self._server_socket: (
            socket.socket | None
        ) = None

        self._server_thread: (
            threading.Thread | None
        ) = None

        self._stop_event = (
            threading.Event()
        )

        # Opción usada únicamente en el experimento
        # controlado de prioridad.
        self.simulate_first_send_failure = (
            simulate_first_send_failure
        )

        # Registra qué combinación mensaje-destino
        # ya sufrió su falla simulada.
        self._simulated_failures: set[
            tuple[str, str]
        ] = set()

        self._simulated_failures_lock = (
            threading.Lock()
        )

    def start(
        self,
        handler: EnvelopeHandler,
    ) -> None:

        if (
            self._server_thread
            and
            self._server_thread.is_alive()
        ):
            return

        self._handler = handler

        self._stop_event.clear()

        self._server_thread = (
            threading.Thread(
                target=self._serve,
                name=(
                    f"civicmesh-tcp-"
                    f"{self.port}"
                ),
                daemon=True,
            )
        )

        self._server_thread.start()

        deadline = (
            time.time()
            + self.timeout
        )

        while (
            self._server_socket is None
            and time.time() < deadline
        ):
            time.sleep(0.01)

    def stop(self) -> None:

        self._stop_event.set()

        if self._server_socket is not None:

            try:
                self._server_socket.close()

            except OSError:
                pass

        if self._server_thread is not None:

            self._server_thread.join(
                timeout=1.0
            )

    def _serve(self) -> None:

        server = socket.socket(
            socket.AF_INET,
            socket.SOCK_STREAM,
        )

        server.setsockopt(
            socket.SOL_SOCKET,
            socket.SO_REUSEADDR,
            1,
        )

        server.bind(
            (
                self.host,
                self.port,
            )
        )

        server.listen()

        server.settimeout(
            0.2
        )

        self._server_socket = server

        try:

            while not self._stop_event.is_set():

                try:

                    conn, _ = (
                        server.accept()
                    )

                except socket.timeout:
                    continue

                except OSError:
                    break

                threading.Thread(
                    target=self._handle_client,
                    args=(conn,),
                    daemon=True,
                ).start()

        finally:

            try:
                server.close()

            except OSError:
                pass

            self._server_socket = None

    def _handle_client(
        self,
        conn: socket.socket,
    ) -> None:

        with conn:

            conn.settimeout(
                self.timeout
            )

            try:

                file = conn.makefile(
                    "rwb"
                )

                raw = file.readline()

                if not raw:
                    return

                envelope = json.loads(
                    raw.decode("utf-8")
                )

                response = (
                    self._handler(envelope)
                    if self._handler
                    else None
                )

                if response is not None:

                    data = (
                        json.dumps(
                            response,
                            ensure_ascii=False,
                        )
                        + "\n"
                    ).encode("utf-8")

                    file.write(data)

                    file.flush()

            except (
                OSError,
                json.JSONDecodeError,
                ValueError,
            ):
                return

    def _exchange(
        self,
        target: PeerInfo,
        envelope: dict[str, Any],
        *,
        expect_response: bool = False,
    ) -> dict[str, Any] | None:

        with socket.create_connection(
            target.address,
            timeout=self.timeout,
        ) as sock:

            sock.settimeout(
                self.timeout
            )

            file = sock.makefile(
                "rwb"
            )

            data = (
                json.dumps(
                    envelope,
                    ensure_ascii=False,
                )
                + "\n"
            ).encode("utf-8")

            file.write(data)

            file.flush()

            if not expect_response:
                return None

            raw = file.readline()

            if not raw:

                raise ConnectionError(
                    "el peer remoto "
                    "no devolvió respuesta"
                )

            return json.loads(
                raw.decode("utf-8")
            )

    def send(
        self,
        target: PeerInfo,
        payload: GossipPayload,
    ) -> None:
        """Envía Gossip por TCP."""

        try:

            self._exchange(
                target,
                {
                    "type": "gossip",
                    "payload":
                        payload.to_dict(),
                },
            )

        except (
            OSError,
            ConnectionError,
            TimeoutError,
            json.JSONDecodeError,
        ):
            # Gossip detectará después el timeout.
            return

    def request_join(
        self,
        target: PeerInfo,
        self_info: PeerInfo,
    ) -> GossipPayload:
        """JOIN real con un seed."""

        response = self._exchange(
            target,
            {
                "type": "join_request",
                "peer":
                    self_info.to_dict(),
            },
            expect_response=True,
        )

        if (
            not response
            or
            response.get("type")
            != "join_response"
        ):

            raise ConnectionError(
                "respuesta JOIN inválida"
            )

        return GossipPayload.from_dict(
            response["payload"]
        )

    def attempts_for_priority(
        self,
        priority: int,
    ) -> int:
        """
        Define la cantidad de intentos de envío
        según la prioridad del mensaje.

        Los mensajes con prioridad igual o superior
        al umbral tienen dos intentos. Los demás
        tienen un solo intento.
        """

        if (
            int(priority)
            >= self.high_priority_threshold
        ):
            return 2

        return 1

    def send_pubsub(
        self,
        target: PeerInfo,
        msg: Message,
    ) -> bool:
        """
        Envía un mensaje Pub/Sub.

        Los mensajes de prioridad alta tienen
        más intentos de entrega.

        Durante el experimento de prioridad se
        puede simular una falla en el primer
        intento de cada mensaje hacia cada peer.
        """

        attempts = self.attempts_for_priority(
            msg.priority
        )

        envelope = {
            "type": "pubsub",
            "from_peer": (
                self.peer_id
                or msg.origin
            ),
            "message": msg.to_dict(),
        }

        failure_key = (
            msg.msg_id,
            target.peer_id,
        )

        for attempt in range(attempts):

            # Experimento Fase 15:
            # el primer intento de cada mensaje
            # hacia cada destino falla.
            if (
                self.simulate_first_send_failure
                and attempt == 0
            ):

                with self._simulated_failures_lock:

                    if (
                        failure_key
                        not in self._simulated_failures
                    ):
                        self._simulated_failures.add(
                            failure_key
                        )

                        continue

            try:

                self._exchange(
                    target,
                    envelope,
                )

                return True

            except (
                OSError,
                ConnectionError,
                TimeoutError,
                json.JSONDecodeError,
            ):

                if (
                    attempt + 1
                    < attempts
                ):
                    time.sleep(0.05)

        return False