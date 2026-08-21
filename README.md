# CivicMesh

## Descripción

CivicMesh es el proyecto del Laboratorio 3: una aplicación distribuida de
tipo peer-to-peer, desarrollada principalmente en Python, cuyo objetivo es
construir una red de peers capaces de:

- descubrirse entre sí y mantener una vista parcial de la red mediante un
  protocolo de Gossip/Membership;
- intercambiar información mediante un mecanismo de publicación/suscripción
  (Pub/Sub) sobre esa red;
- utilizar esa infraestructura para distribuir y procesar datos, y producir
  analítica/visualización sobre los resultados.

El trabajo está organizado en componentes modulares para que los distintos
roles del equipo puedan avanzar en paralelo.

## Arquitectura general

Flujo conceptual de dependencias entre capas:

```
Peers
 ↓
Gossip / Membership   (descubrimiento, vista parcial, detección de fallos)
 ↓
Pub/Sub                (topics, suscripciones, forwarding sobre la red de peers)
 ↓
Datos / procesamiento  (adquisición y preparación de la información distribuida)
 ↓
Analítica / resultados (métricas, visualización, experimentación)
```

Cada capa consume a la anterior a través de una interfaz reducida, no de sus
detalles internos. En particular, Pub/Sub no depende del algoritmo de Gossip:
consume una interfaz de solo lectura sobre la vista de peers (ver
[docs/gossip.md](docs/gossip.md#interfaz-para-pubsub)).

## Roles y responsabilidades

| Rol | Área | Responsabilidades principales |
| --- | --- | --- |
| Rol 1 | Capa de Red / Gossip | Representación de peers, JOIN, descubrimiento, vista parcial, rondas de Gossip, fanout, heartbeat/last_seen, detección de fallos por timeout, interfaz para Pub/Sub. |
| Rol 2 | Pub/Sub | Topics, suscripciones, publicación y recepción de eventos, forwarding, `should_forward`, uso de la vista de peers entregada por Gossip. |
| Rol 3 | Datos | Adquisición/carga de datasets o fuentes requeridas por CivicMesh, caché/procesamiento, preparación de los datos usados por los peers. |
| Rol 4 | Analítica / Visualización | Métricas, análisis de resultados, visualizaciones y componentes analíticos del laboratorio. |
| Rol 5 | Integración / CI / Ejecución | Infraestructura de integración, CI/CD, Docker, ejecución distribuida/cluster cuando corresponda, soporte a experimentos e integración del proyecto. |

Esta tabla describe áreas funcionales, no asignaciones personales; se
actualizará si el equipo define responsables específicos.

## Estructura del repositorio

```
Lab3-CivicMesh/
├── README.md
├── pyproject.toml
├── .gitignore
├── civicmesh/
│   ├── __init__.py
│   └── gossip/              # Capa de Red / Gossip / Membership (Rol 1)
│       ├── __init__.py
│       ├── peer.py          # PeerInfo, PeerStatus
│       ├── membership.py    # MembershipTable (registro, vista parcial, timeout, merge)
│       ├── gossip.py        # GossipService (fanout, rondas, merge)
│       ├── messages.py      # GossipPayload
│       ├── interfaces.py    # PeerDirectory (para Pub/Sub), GossipTransport
│       ├── node.py          # Node: integra identidad + membership + gossip, expone JOIN
│       ├── config.py        # GossipConfig: parámetros reproducibles
│       ├── bootstrap.py     # Lectura de hostfile.txt y selección de seeds (solo bootstrap)
│       └── metrics.py       # Contadores de solo lectura para analítica
├── tests/
│   └── gossip/               # Tests unitarios e integración en memoria de la capa de Gossip
├── docs/
│   └── gossip.md             # Documentación detallada de Gossip/Membership
```

Los subpaquetes `civicmesh.pubsub`, `civicmesh.data` y `civicmesh.analytics`,
así como infraestructura de CI/Docker, todavía no existen en el repositorio;
se agregarán a medida que cada rol avance (ver [Estado del proyecto](#estado-del-proyecto)).

## Flujo de ejecución

Estado actual, implementado como lógica de dominio (sin transporte de red
real todavía — ver [docs/gossip.md](docs/gossip.md#transporte-no-implementado)):

1. Un peer se inicializa con su identidad (`peer_id`, `host`, `port`).
2. Realiza JOIN contra un peer semilla (seed), que queda registrado en su
   tabla de membership.
3. Mantiene una vista parcial de la red mediante rondas de Gossip: en cada
   ronda selecciona vecinos (fanout configurable) e intercambia/mergea
   información de membership.
4. Actualiza `last_seen` de los peers de los que recibe señales, y detecta
   como caídos a los que superan un timeout configurable.
5. Expone esa vista de peers (conocidos, vivos, vista parcial) a través de
   una interfaz reducida (`PeerDirectory`) pensada para ser consumida por
   Pub/Sub.

Pendiente (plan, no implementado todavía):

6. Pub/Sub utilizará esa red de peers para publicar/suscribirse a topics y
   distribuir eventos, incluyendo reglas de forwarding.
7. Los componentes de datos y analítica procesarán y visualizarán la
   información distribuida a través de la red.

## Desarrollo

- **Python**: 3.10 o superior (probado con 3.14).
- **Dependencias externas**: ninguna por ahora; el paquete y los tests usan
  únicamente la librería estándar.

Ejecutar los tests:

```bash
python -m unittest discover -s tests -v
```

Verificar sintaxis/compilación:

```bash
python -m py_compile civicmesh/gossip/*.py
```

## Flujo Git

- `main` está protegida: no se realizan commits directos ni push directo
  sobre ella.
- El desarrollo ocurre en ramas por tipo de cambio: `feature/*` (nueva
  funcionalidad), `fix/*` (correcciones), `docs/*` (documentación).
- Los cambios se integran a `main` exclusivamente mediante Pull Request,
  con revisión humana antes del merge.
- Los issues se usan para reportar bugs, tareas y dependencias entre roles.
- La integración de CI (cuando exista, a cargo del Rol 5) debe pasar antes
  de habilitar el merge de un PR.

## Estado del proyecto

| Componente | Estado |
| --- | --- |
| Gossip / Membership (Rol 1) | En desarrollo: dominio (peer, membership, vista parcial, gossip/fanout, heartbeat/timeout, JOIN) implementado y testeado; transporte de red real pendiente. |
| Pub/Sub (Rol 2) | No iniciado. |
| Datos (Rol 3) | No iniciado. |
| Analítica / Visualización (Rol 4) | No iniciado. |
| Integración / CI / Docker (Rol 5) | No iniciado. |

## Laboratorio 3 / Entregables

De acuerdo con el alcance general del laboratorio, el proyecto contempla
como entregables:

- Implementación de la red de peers con descubrimiento y Gossip/membership.
- Implementación de Pub/Sub sobre dicha red, con reglas de forwarding.
- Componente de datos utilizado por la aplicación.
- Componente de analítica/visualización sobre los resultados obtenidos.
- Infraestructura de ejecución (Docker/CI) para experimentación distribuida.
- Documentación del proyecto y flujo de trabajo Git profesional (issues,
  PRs, revisión, CI).
- Release final integrando los componentes anteriores.

El detalle de cada entregable se documentará en `docs/` a medida que cada
rol avance; este README se actualizará para reflejar únicamente el estado
verificable del repositorio.
# Lab3-CivicMesh

## Integración a `main`, CI y agentes automatizados

CivicMesh integra cambios a `main` exclusivamente mediante Pull Requests:
cada PR corre el workflow de CI (job `tests`) y requiere revisión humana
antes de fusionarse. La protección formal de `main` en la configuración de
GitHub (status checks obligatorios, etc.) es una política del proyecto —
este README no afirma que ya esté activada en GitHub, solo que es así como
se trabaja. El detalle completo del flujo de ramas, Pull Requests e issues
está en [docs/git-flow.md](docs/git-flow.md).

El repositorio usa tres agentes auxiliares de GitHub Actions (documentador,
revisor de bugs, revisor de Pull Requests). Son estrictamente auxiliares:
**nunca aprueban ni fusionan Pull Requests, nunca hacen push directo a
`main`, y nunca deciden cambios de protocolo o semántica distribuida**
(Gossip, membership, Pub/Sub, `should_forward`, TTL, prioridad) — esas
decisiones son siempre responsabilidad humana. Su documentación específica
(qué hace cada uno, límites, deduplicación de issues, configuración
opcional de un proveedor de IA) está en
[scripts/agents/README.md](scripts/agents/README.md).
