# Capa de Red / Gossip / Membership

Este documento describe la implementación de la capa de red y membership de
CivicMesh (`civicmesh.gossip`), responsable de que los peers se descubran,
mantengan una vista de la red y detecten fallos, de forma independiente de
Pub/Sub, datos o analítica. Está escrito para que el Rol 1 pueda explicar
esta capa (informe/defensa) apoyándose directamente en archivos y tests
concretos, sin tener que reconstruir decisiones de memoria.

## Objetivo

Construir la base sobre la que evoluciona el resto del sistema:

```
Peer básico
    → JOIN mediante peer(s) seed
    → registro/membership
    → vista parcial de peers
    → rondas Gossip
    → fanout
    → actualización de heartbeat / last_seen
    → timeout
    → detección de peers caídos
    → interfaz utilizable por Pub/Sub
```

Esta iteración implementa toda la lógica de dominio de esa cadena, en
ambos lados de cada interacción (quien inicia el JOIN y quien lo recibe;
quien emite un gossip y quien lo recibe). El transporte de red real
(sockets/HTTP/UDP) **no** está implementado todavía (ver
[Transporte](#transporte-no-implementado)).

## Módulos

| Módulo | Responsabilidad |
| --- | --- |
| [`civicmesh/gossip/peer.py`](../civicmesh/gossip/peer.py) | `PeerInfo` (identidad + estado, serializable) y `PeerStatus` (ALIVE/DEAD). |
| [`civicmesh/gossip/membership.py`](../civicmesh/gossip/membership.py) | `MembershipTable`: registro de peers, heartbeat, timeout, vista parcial, merge, métricas. |
| [`civicmesh/gossip/gossip.py`](../civicmesh/gossip/gossip.py) | `GossipService`: selección de vecinos (fanout), construcción de payload, rondas de gossip, métricas. |
| [`civicmesh/gossip/messages.py`](../civicmesh/gossip/messages.py) | `GossipPayload`: mensaje intercambiado entre peers (serializable). |
| [`civicmesh/gossip/interfaces.py`](../civicmesh/gossip/interfaces.py) | `PeerDirectory` (contrato para Pub/Sub) y `GossipTransport` (punto de extensión de transporte). |
| [`civicmesh/gossip/node.py`](../civicmesh/gossip/node.py) | `Node`: integra identidad + membership + gossip, expone JOIN (ambos lados) y la interfaz `PeerDirectory`. |
| [`civicmesh/gossip/config.py`](../civicmesh/gossip/config.py) | `GossipConfig`: parámetros reproducibles (fanout, vista parcial, timeout, intervalo, seed). |
| [`civicmesh/gossip/bootstrap.py`](../civicmesh/gossip/bootstrap.py) | Lectura de `hostfile.txt` y selección de seeds — solo bootstrap, no reemplaza al Gossip. |
| [`civicmesh/gossip/metrics.py`](../civicmesh/gossip/metrics.py) | `MembershipMetrics`/`GossipMetrics`: contadores de solo lectura para Rol 4. |

## 1. Qué información mantiene un peer

`PeerInfo` (`peer.py`) es un `dataclass` inmutable con:

- `peer_id`: identificador único.
- `host`, `port`: datos de contacto.
- `status`: `PeerStatus.ALIVE` o `PeerStatus.DEAD`.
- `last_seen`: marca temporal (`float`) de la última afirmación conocida
  sobre ese peer (heartbeat directo, JOIN, o gossip aceptado por merge).

Las actualizaciones (`touched`, `with_status`, `marked_dead`) devuelven una
copia nueva en vez de mutar en sitio, evitando estado compartido implícito.
`PeerInfo` no conoce nada de topics, suscripciones ni mensajes de Pub/Sub:
eso es responsabilidad exclusiva del Rol 2.

**Serialización**: `PeerInfo.to_dict()`/`PeerInfo.from_dict()` y
`GossipPayload.to_dict()`/`from_dict()` dan una representación JSON-friendly
(`dict` con tipos primitivos) sin acoplarse a ningún transporte ni a
Pub/Sub — quien implemente el transporte real solo tiene que serializar ese
`dict` (JSON, msgpack, lo que corresponda).

## 2. Cómo entra un peer a la malla (JOIN)

El flujo de JOIN está modelado **en ambos lados**, sin transporte real:

```python
newcomer.join(seed.self_info, now=t)                      # lado newcomer: registra al/los seed(s)
response = seed.handle_join_request(newcomer.self_info, t)  # lado seed: registra al newcomer, responde su vista
newcomer.handle_join_response(response, now=t)              # lado newcomer: adopta la vista del seed
```

- `Node.join(seeds, now)` acepta un único `PeerInfo` o una colección (para
  ser compatible con 1–2 seeds leídos de un `hostfile.txt`). Rechaza una
  lista vacía y rechaza usarse a sí mismo como seed.
- `Node.handle_join_request(new_peer, now)` es el lado que **recibe** la
  solicitud: registra directamente al peer entrante (así el seed también
  lo conoce, no solo al revés) y le devuelve su vista actual de membership.
- `Node.handle_join_response(payload, now)` aplica esa respuesta con la
  misma lógica de merge que usan las rondas de gossip normales — no hay una
  ruta especial de "primer contacto" distinta del merge general.

Ver tests: `tests/gossip/test_node.py::JoinHandshakeBetweenTwoNodesTests` y
el escenario de 3 peers en `tests/gossip/test_multi_peer_integration.py`.

**Bootstrap compatible con `hostfile.txt`**: `civicmesh/gossip/bootstrap.py`
ofrece `parse_hostfile`/`load_hostfile` (formato `peer_id host port`, una
entrada por línea, líneas vacías o `#...` ignoradas) y `select_seeds`
(elige hasta *N* seeds al azar, excluyendo al propio peer, con `rng`
inyectable). Esto es **solo bootstrap/configuración**: el archivo
compartido le dice a un peer con quién intentar el primer contacto; la
propagación de membership en régimen sigue ocurriendo exclusivamente por
red, vía las rondas de Gossip. `bootstrap.py` no participa en absoluto en
el merge ni en la detección de fallos.

Pendiente (fuera de esta iteración): el envío/recepción real de la
solicitud de JOIN por red — hoy `handle_join_request`/`handle_join_response`
son invocaciones directas en el mismo proceso (o en tests); alguien debe
invocarlas desde ambos lados de una conexión real cuando exista transporte.

## 3. Vista parcial: qué significa y qué política tiene

`MembershipTable.get_partial_view(rng=None)` (`membership.py`):

- **Inclusión**: solo peers con `status == ALIVE`. Un peer marcado `DEAD`
  por `detect_timeouts` deja de aparecer de inmediato.
- **Tamaño**: acotado a `partial_view_size` (configurable, ver
  [Configuración](#6-configuración-reproducible)). Si hay menos peers vivos
  que el límite, se devuelven todos (vista "no llena").
- **Reemplazo al llenarse**: la vista **no** es una estructura persistente
  con inserciones/evicciones — cada llamada resamplea uniformemente al azar,
  sin reemplazo, sobre el conjunto de peers vivos conocidos en ese momento
  (estilo *peer sampling service*). No existe un evento explícito de
  "descartar un vecino": un peer que no sale sorteado en una llamada puede
  volver a salir en la siguiente. Esta elección evita tener que diseñar una
  política de expulsión aparte, y sigue siendo determinista si se inyecta
  `rng`.
- **Duplicados**: imposibles — la tabla interna indexa por `peer_id`.
- **Peer local**: nunca aparece, porque nunca se registra a sí mismo (ver
  `register_peer`/`touch`/`merge`, todos con guard explícito de auto-exclusión).

Tests (`tests/gossip/test_membership.py::PartialViewTests`): vista menor al
máximo, vista exactamente al máximo, ingreso de peers adicionales (la vista
crece cuando se registran más peers), exclusión propia, ausencia de
duplicados, exclusión de peers marcados caídos. Todos corren sin sockets,
pasando `rng=random.Random(seed)`.

## 4. Cómo funciona una ronda Gossip

`GossipService.run_round(now, transport=None, rng=None)` (`gossip.py`):

1. Consulta los peers activos de la vista (`select_gossip_targets`, que a
   su vez parte de `MembershipTable.get_alive_peers()`).
2. Selecciona hasta `fanout` destinos (ver [fanout](#5-fanout-elegido-y-por-qué)).
3. Si hay `transport` (ver [Transporte](#transporte-no-implementado)),
   arma el payload actual (`build_payload`) y lo envía a cada destino.
4. El receptor procesa el payload con `merge_incoming(payload, now)`
   (directamente, o vía `Node.handle_gossip_message`), que:
   5. registra al remitente directamente (descubrimiento vía gossip, no
      solo vía JOIN — ver más abajo), y
   6. fusiona (`MembershipTable.merge`) el resto de la vista que trae el
      payload con la tabla local.

`run_round` devuelve siempre los destinatarios seleccionados, incluso sin
`transport` — permite testear la lógica de la ronda sin red real.

**Descubrimiento transitivo vía gossip**: el `sender` de un `GossipPayload`
es la identidad completa del emisor (`PeerInfo`, con host/port), no solo un
id. Esto es necesario: si solo viajara un `sender_id: str`, un peer que
recibe gossip de alguien que nunca vio antes no podría registrarlo (no
tendría su host/port), y el descubrimiento solo funcionaría a través de
terceros que ya lo conocieran. Con `sender: PeerInfo`, cualquier peer que
te hable directamente queda registrado, con o sin JOIN previo. Test que fija
este contrato: `test_gossip.py::MergeIncomingTests::test_merge_incoming_registers_a_previously_unknown_sender`
y `test_node.py::GossipMessageHandlingTests::test_handle_gossip_message_registers_previously_unknown_sender`.

## 5. Fanout: elegido y por qué

**Política elegida**: selección aleatoria uniforme sin reemplazo entre los
peers vivos conocidos (`GossipService.select_gossip_targets`, usa
`random.sample`). Con menos peers vivos que `fanout`, se contactan todos los
disponibles; con `fanout == 0`, la ronda no tiene destinos (configuración
válida, no error).

**Por qué**: es la política estándar en protocolos epidémicos de gossip
(sin sesgo hacia ningún subconjunto de peers, fácil de razonar, fácil de
testear de forma determinista inyectando `random.Random(seed)`). No hay
todavía ninguna razón arquitectónica del laboratorio (p. ej. topología
geográfica real entre hosts DIINF) que justifique una política sesgada o
híbrida; agregar esa complejidad ahora sería sofisticación prematura.

**Trade-off fanout ↔ tráfico ↔ velocidad de propagación** (documentado como
expectativa teórica; **no hay resultados experimentales todavía**):

- Mayor `fanout` → cada ronda contacta más vecinos → la información
  (nuevos peers, caídas) tiende a converger en menos rondas, a costa de
  más mensajes/tráfico de red por ronda.
- Menor `fanout` → menos tráfico por ronda, a costa de una convergencia
  potencialmente más lenta (más rondas hasta que toda la malla se entere
  de un cambio).

`fanout` es configurable (ver `GossipConfig.fanout` /
`GossipService(fanout=...)`) y es **distinto** del fanout que use Pub/Sub
para reenviar mensajes de aplicación — cada uno se configura por separado
y esta capa no impone nada sobre el del Rol 2.

Tests (`tests/gossip/test_gossip.py::FanoutSelectionTests`): `fanout=0`,
`fanout=1`, menor al disponible, igual al disponible, mayor al disponible,
sin duplicados, peer local nunca seleccionado (incluso si se intenta
"colar" vía merge), peers caídos nunca seleccionados, selección
determinista con `rng` fijo.

## Heartbeat y `last_seen`

`MembershipTable` (`membership.py`):

- `register_peer(peer, now)` / `touch(peer_id, now)`: refrescan
  `last_seen` a `now` (hora local del receptor) y fuerzan `status=ALIVE`.
  `touch` es no-op sobre un peer desconocido (para eso está
  `register_peer`, que si el peer es nuevo lo da de alta).
- `time_since_last_seen(peer_id, now)`: antigüedad (`now - last_seen`) de
  un peer conocido; `None` si no existe. Pensado para observabilidad
  (Rol 4) o para decisiones externas al ciclo periódico normal.

Todas las operaciones sensibles al tiempo reciben `now` explícito (nunca
`time.time()` interno), por lo que los tests pasan tiempos arbitrarios sin
`sleep`.

## 7. Cómo se detecta una caída / 8. Qué ocurre después

Modelo de estados: **binario, `ALIVE` / `DEAD`** (sin estado `SUSPECT`
intermedio). Se eligió el modelo más simple que cumple el requisito del
enunciado; un `SUSPECT` al estilo SWIM queda identificado como extensión
futura si el laboratorio lo pide explícitamente, no se agregó ahora por no
sumar estados sin necesidad concreta.

- `MembershipTable.detect_timeouts(now, timeout_seconds)`: para cada peer
  `ALIVE` cuyo `now - last_seen > timeout_seconds` (estrictamente mayor:
  exactamente en el borde el peer **sigue vivo**, comportamiento fijado por
  test), lo marca `DEAD` **y avanza su `last_seen` a `now`**. Devuelve los
  `peer_id` recién marcados.
- Ese avance de `last_seen` al morir no es cosmético: es lo que permite que
  el veredicto de caída **gane** el merge last-writer-wins frente al último
  `ALIVE` que otros peers todavía tengan para ese mismo `peer_id` (ver
  `PeerInfo.marked_dead`). Sin él, una caída con el mismo `last_seen` que el
  último heartbeat nunca podría propagarse vía gossip.
- **Después de detectar una caída**: el peer deja de ser candidato en
  `select_gossip_targets` (parte de `get_alive_peers()`), desaparece de
  `get_partial_view()`, y su nuevo estado (`DEAD`, `last_seen=now`) queda
  disponible para propagarse la próxima vez que este nodo le haga gossip a
  otro (vía `merge`).
- **Recuperación**: si después llega un `touch`/`register_peer`/gossip más
  reciente para ese `peer_id`, vuelve a `ALIVE` de forma consistente
  (`PeerInfo.touched` siempre fuerza `ALIVE`).

Tests (`tests/gossip/test_membership.py::TimeoutTests`): recién visto →
activo, dentro del timeout → activo, exactamente en el borde → activo
(comportamiento definido), excede el timeout → caído (y con `last_seen`
avanzado), caído no se repite en detecciones sucesivas, recuperación vía
`touch`. Selección de gossip excluyendo caídos:
`test_gossip.py::FanoutSelectionTests::test_only_alive_peers_are_selected`
y `test_dead_peers_are_excluded_even_when_alive_peers_remain`.

## Merge de información Gossip

`MembershipTable.merge(incoming)`: para cada `PeerInfo` entrante, si el
peer era desconocido o su `last_seen` es estrictamente mayor al que ya
teníamos, se adopta tal cual (incluyendo su `status`, para poder propagar
también caídas). Si es igual o más viejo, se descarta. El propio peer nunca
se sobreescribe con información entrante.

Tests (`tests/gossip/test_membership.py::MergeTests`): peer desconocido se
incorpora, información más nueva actualiza, información más antigua no pisa
estado nuevo, merge repetido es idempotente, el propio peer recibido nunca
termina almacenado como vecino, propagación de estado `DEAD`.

## Tolerancia a fallas

La caída de un peer no debe destruir la malla. Demostrado por lógica y
tests (no por el experimento completo de partición del laboratorio, que
queda para cuando exista transporte real):

- Un peer detectado como fallido deja de ser destino de gossip
  (`select_gossip_targets` parte de `get_alive_peers()`).
- Los demás peers vivos siguen disponibles: `get_alive_peers()` y
  `get_partial_view()` siguen entregando vecinos utilizables.
- El estado fallido se propaga de forma coherente vía `merge` (ver arriba).

Ver el escenario completo de 3 peers en
[Preparación para integración multi-peer](#9-preparación-para-integración-multi-peer)
más abajo, donde un peer "cae" y los otros dos se lo comunican entre sí sin
perder contacto mutuo.

Cómo se podrá provocar/observar más adelante (una vez exista transporte y
ejecución real, a cargo de Rol 5/experimentación conjunta):

- *kill* de un proceso peer real.
- expiración de su `timeout_seconds` en los peers vivos restantes.
- próxima ronda de gossip que actualiza el membership con el nuevo estado.
- observación externa mediante las métricas de la sección siguiente.

## Interfaz con Pub/Sub

Pub/Sub (Rol 2) debe depender de `civicmesh.gossip.interfaces.PeerDirectory`,
no de `GossipService`/`MembershipTable`/`Node` directamente:

```python
class PeerDirectory(Protocol):
    def get_known_peers(self) -> list[PeerInfo]: ...
    def get_alive_peers(self) -> list[PeerInfo]: ...
    def get_partial_view(self) -> list[PeerInfo]: ...
```

`Node` implementa este protocolo estructuralmente (no requiere herencia
explícita; verificado con `isinstance(node, PeerDirectory)` en tests).

**Lo que Gossip le entrega a Pub/Sub:**

- Peers actualmente utilizables (`get_alive_peers()` / `get_partial_view()`).
- Identidad/endpoint (`peer_id`, `host`, `port`) necesarios para que Pub/Sub
  les envíe mensajes de aplicación.
- Una vista local (parcial o completa) sobre la que Pub/Sub puede decidir a
  quién reenviar, con qué fanout propio, etc.

**Lo que Gossip explícitamente NO controla ni implementa** (responsabilidad
del Rol 2, no tocada por esta capa):

- Topics, subscribe/unsubscribe.
- Publicación/recepción de eventos de aplicación.
- Reglas de forwarding (`should_forward`).
- TTL de mensajes Pub/Sub.
- Prioridad de mensajes.
- Fanout de Pub/Sub (es un parámetro distinto del fanout de Gossip; ambos
  se configuran por separado).
- Semántica de dominio de la aplicación (p. ej. percepción de inseguridad,
  calidad del aire, datasets, interpolación espacial).

Con esto, el Rol 2 puede empezar su trabajo consumiendo `PeerDirectory` sin
tener que leer el interior de `gossip.py`/`membership.py`.

## 6. Configuración reproducible

`civicmesh/gossip/config.py` define `GossipConfig`, que agrupa los
parámetros que antes estaban dispersos como argumentos sueltos:

| Campo | Default | Rol |
| --- | --- | --- |
| `fanout` | 3 | vecinos contactados por ronda |
| `partial_view_size` | 5 | tamaño máximo de la vista parcial |
| `failure_timeout_seconds` | 30.0 | antigüedad de `last_seen` para marcar `DEAD` |
| `gossip_interval_seconds` | 5.0 | intervalo esperado entre rondas (documentado; sin scheduler real todavía) |
| `rng_seed` | `None` | semilla para fanout/vista parcial; `None` = no determinista |

Valida sus propios campos (`fanout < 0`, `partial_view_size <= 0`, etc. son
rechazados) y expone `build_rng()` para obtener un `random.Random`
consistente con `rng_seed`. `Node.from_config(self_info, config)` construye
un nodo a partir de esta configuración.

El proyecto todavía no tiene un `config.yaml` compartido entre roles. Si se
introduce uno más adelante, la sección correspondiente a Gossip debería
usar estas mismas claves (incluir un experimento nuevo o cambiar el
`rng_seed` no debería requerir tocar código).

## 9. Preparación para integración multi-peer

El laboratorio exige, más adelante, un escenario con ≥3 peers reales (varios
procesos/contenedores). Esta iteración **no** monta ese escenario (no hay
transporte real todavía), pero sí incluye un test de integración pequeño,
puramente en memoria, con 3 `Node` en el mismo proceso
(`tests/gossip/test_multi_peer_integration.py`), donde "enviar" un mensaje
es invocar directamente `handle_gossip_message`/`handle_join_request` en el
destinatario. Demuestra, de forma rápida (milisegundos), determinista y sin
infraestructura externa:

- JOIN bidireccional entre pares de peers.
- Descubrimiento transitivo: un peer C aprende de un peer A que nunca
  contactó directamente, solo porque un tercero (B) se lo gossipeó.
- Vista "eventualmente estable": los tres peers terminan conociéndose entre
  sí, con vistas parciales sin duplicados y sin autorreferencia.
- Caída de un peer (A) detectada por B, propagada a C vía gossip, sin que
  B y C pierdan contacto mutuo.

Qué falta para el escenario real de laboratorio (≥3 procesos/contenedores):
implementar `GossipTransport` sobre un mecanismo real (sockets/HTTP/lo que
decida el equipo), y un bucle/scheduler que dispare `run_round` y
`detect_timeouts` periódicamente en cada proceso — ninguno de los dos existe
todavía (ver [Transporte](#transporte-no-implementado)). La interfaz de
dominio (`Node`, `GossipService`, `MembershipTable`) ya está lista para que,
una vez exista ese transporte, el mismo código de esta capa funcione sin
cambios entre procesos/hosts distintos.

## 10. Preparación para Docker y Slurm multi-host

Nada en esta capa depende de:

- `localhost` fijo — `host`/`port` son campos obligatorios de `PeerInfo`,
  provistos por quien construye cada peer (o leídos de un `hostfile.txt`
  vía `bootstrap.py`), nunca hardcodeados en el dominio.
- Puertos globales fijos — cada `PeerInfo` lleva su propio `port`.
- Rutas de filesystem exclusivas de una máquina — el único punto que toca
  filesystem es `bootstrap.load_hostfile`, y es opcional (existe la
  alternativa pura `parse_hostfile(lines)` sin I/O).
- Estado global en memoria compartida entre procesos — `MembershipTable`,
  `GossipService` y `Node` son todas clases con estado de instancia; no hay
  variables de módulo mutables en ningún archivo de `civicmesh/gossip/`.

Esto deja el diseño compatible, en principio, con:

- **Local / Docker Compose**: ≥3 contenedores, cada uno un proceso peer con
  su propio `host`/`port` (el de Compose o el mapeado), usando `bootstrap.py`
  para leer un `hostfile.txt` compartido por volumen y elegir seeds.
- **DIINF / Slurm**: peers distribuidos entre 2+ hosts CPU, mismo mecanismo
  de `hostfile.txt` en el FS compartido para bootstrap; el tráfico de Gossip
  en sí seguiría yendo por red real una vez exista `GossipTransport`, nunca
  por el FS compartido.

Lo que falta para que esto sea real (no responsabilidad de Rol 1, se deja
documentado como dependencia): imagen(es) Docker, `docker-compose.yml`,
scripts/plantillas de Slurm, y el propio `GossipTransport` concreto — todo
a cargo del Rol 5 (o coordinado con él).

## Métricas que esta capa puede exponer

`civicmesh/gossip/metrics.py` define dos estructuras de solo lectura,
pensadas para que el Rol 4 las consuma sin leer el estado interno:

- `MembershipTable.metrics() -> MembershipMetrics`: `known_peers`,
  `alive_peers`, `dead_peers`, `partial_view_size_limit`.
- `GossipService.metrics() -> GossipMetrics`: `rounds_run`,
  `messages_sent`, `messages_received` (contadores acumulados desde la
  creación del servicio).
- `Node.get_membership_metrics()` / `Node.get_gossip_metrics()` exponen
  ambas desde el punto de integración.

No implementado (no es responsabilidad de esta capa): tiempo de detección
de fallo como métrica agregada/histórico — es derivable externamente
comparando el `now` pasado a `detect_timeouts` con el `last_seen` previo del
peer recién marcado `DEAD`; no se agregó un cálculo dedicado para no
adelantarse a lo que Rol 4 realmente necesite. Tampoco hay exportación
(Prometheus, logs estructurados, etc.): estos objetos son el punto de
partida para que quien construya esa exportación lo haga sin tocar
`MembershipTable`/`GossipService`.

## Transporte (no implementado)

`civicmesh.gossip.interfaces.GossipTransport` define el punto de extensión
(`send(target, payload)`) para el envío real de mensajes de gossip. Esta
iteración **no** implementa sockets/HTTP/UDP: toda la lógica de dominio
(selección de vecinos, merge, JOIN en ambos lados) funciona y se testea sin
transporte real, pasando `transport=None` en `run_round` o invocando los
métodos de recepción (`handle_gossip_message`, `handle_join_request`)
directamente.

Queda documentado como dependencia pendiente: cuando el rol de
integración/red (Rol 5, o quien corresponda) defina el mecanismo de
transporte del laboratorio, debe implementar `GossipTransport` —y, del lado
receptor, invocar `Node.handle_gossip_message`/`handle_join_request` al
recibir bytes de la red— sin necesidad de tocar la lógica de
`MembershipTable` ni `GossipService`. `PeerInfo.to_dict()`/`from_dict()` y
`GossipPayload.to_dict()`/`from_dict()` ya dejan lista la serialización que
ese transporte va a necesitar.

## 11. Cómo se probaron vista parcial y timeout (y el resto)

Ubicados en [`tests/gossip/`](../tests/gossip/), usan `unittest` (librería
estándar, sin dependencias externas), no usan `sleep`, y toda la lógica
sensible al tiempo recibe `now`/`timeout_seconds`/`rng` explícitos:

- `test_peer.py`: validación de `PeerInfo`, transiciones (`touched`,
  `with_status`, `marked_dead`), round-trip de serialización.
- `test_membership.py`: registro/duplicados/exclusión de sí mismo,
  `touch`/`last_seen`, peers vivos, **vista parcial** (menor al máximo,
  exactamente al máximo, crece con nuevos registros, excluye caídos, sin
  duplicados, determinista con seed), **timeout** (dentro/en el
  borde/fuera de la ventana, no se repite la detección, recuperación vía
  `touch`, `last_seen` avanza al morir), merge (nuevo/viejo/propio
  peer/propagación de `DEAD`/idempotencia), `time_since_last_seen`,
  métricas.
- `test_gossip.py`: validación del constructor, **fanout** (`0`, `1`,
  menor/igual/mayor al disponible, sin duplicados, exclusión propia y de
  caídos, determinismo con `rng`), `run_round` con y sin transporte,
  `merge_incoming` (incluye descubrimiento de un sender desconocido),
  métricas de gossip.
- `test_node.py`: JOIN (uno o varios seeds, rechazo de auto-seed, rechazo
  de lista vacía, merge de la respuesta del seed), handshake de JOIN de
  punta a punta entre dos `Node`, `from_config`, cumplimiento estructural
  de `PeerDirectory`, reflejo de timeouts en `get_alive_peers`, manejo de
  mensajes de gossip (incluye descubrir a un sender desconocido), métricas.
- `test_config.py`: validación de `GossipConfig`, determinismo de
  `build_rng`.
- `test_bootstrap.py`: parseo de hostfile (líneas válidas, comentarios,
  líneas en blanco, líneas/puertos inválidos), lectura desde archivo real
  (`tempfile`), selección de seeds (excluye self, respeta el máximo,
  determinista con `rng`).
- `test_multi_peer_integration.py`: escenario de 3 peers en memoria (JOIN,
  descubrimiento transitivo, convergencia, caída propagada sin romper la
  malla) — ver [sección 9](#9-preparación-para-integración-multi-peer).

Ejecutar toda la suite:

```bash
python -m unittest discover -s tests -v
```

## Qué falta (fuera del alcance de esta iteración)

- Transporte real (sockets/HTTP/UDP) que implemente `GossipTransport`.
- Bucle/scheduler que dispare `run_round` y `detect_timeouts`
  periódicamente en un proceso real, usando `GossipConfig.gossip_interval_seconds`
  (hoy son llamadas explícitas).
- Escenario de integración con procesos/contenedores reales (≥3), una vez
  exista transporte — el test en memoria de la sección 9 cubre la lógica de
  dominio, no la red real.
- Estado `SUSPECT` intermedio, si el laboratorio lo requiere más adelante.
- Exportación de métricas (Prometheus, logs estructurados, etc.) — hoy solo
  están los contadores/objetos de solo lectura.
- Imagen Docker, `docker-compose.yml` y scripts/plantillas de Slurm
  (responsabilidad de Rol 5).
