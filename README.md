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
| Rol 1: Nicolás Morales| Capa de Red / Gossip | Representación de peers, JOIN, descubrimiento, vista parcial, rondas de Gossip, fanout, heartbeat/last_seen, detección de fallos por timeout, interfaz para Pub/Sub. |
| Rol 2: Gabriel Cabrera | Pub/Sub | Topics, suscripciones, publicación y recepción de eventos, forwarding, `should_forward`, uso de la vista de peers entregada por Gossip. |
| Rol 3: Amaru Monje | Datos | Adquisición/carga de datasets o fuentes requeridas por CivicMesh, caché/procesamiento, preparación de los datos usados por los peers. |
| Rol 4: Francisco Riquelme | Analítica / Visualización | Métricas, análisis de resultados, visualizaciones y componentes analíticos del laboratorio. |
| Rol 5: Thomas Gustafsson | Integración / CI / Ejecución | Infraestructura de integración, CI/CD, Docker, ejecución distribuida/cluster cuando corresponda, soporte a experimentos e integración del proyecto. |

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

## Levantar el entorno localmente (Docker Compose)

Para levantar los nodos (peers, publicador y frontend) localmente con Docker Compose, ejecuta:

```bash
make up
```

Esto construirá la imagen base e iniciará la malla en red interna con:
- **3 peers** (`peer-1`, `peer-2`, `peer-3`) con gossip/pub-sub sobre TCP.
- **Publicador Dominio A** (delitos) usando `scripts/run_publisher.py --domain crime`.
- **Frontend** Streamlit en [http://localhost:8501](http://localhost:8501).

Para también levantar el publicador de Dominio B (calidad del aire):

```bash
docker compose --profile domain-b up --build
```

Para bajar el entorno local y limpiar volúmenes:

```bash
make down
```

### Ejecución local sin Docker

Para ejecutar la malla directamente en tu máquina (requiere Python ≥ 3.10):

```bash
# Instalar el paquete en modo editable
pip install -e .[test]

# Terminal 1: Peer seed
python scripts/run_peer.py --peer-id peer-1 --host 127.0.0.1 --port 9001 --topic Santiago --metrics-dir runs/local/metrics

# Terminal 2: Peer 2 (hace JOIN al seed)
python scripts/run_peer.py --peer-id peer-2 --host 127.0.0.1 --port 9002 --topic Santiago \
    --seed-id peer-1 --seed-host 127.0.0.1 --seed-port 9001 --metrics-dir runs/local/metrics

# Terminal 3: Peer 3
python scripts/run_peer.py --peer-id peer-3 --host 127.0.0.1 --port 9003 --topic Santiago \
    --seed-id peer-1 --seed-host 127.0.0.1 --seed-port 9001 --metrics-dir runs/local/metrics

# Terminal 4: Publicador Dominio A (delitos)
python scripts/run_publisher.py --domain crime --comuna Santiago --peer-id publisher-a \
    --host 127.0.0.1 --port 9100 --seed-id peer-1 --seed-host 127.0.0.1 --seed-port 9001 \
    --metrics-dir runs/local/metrics --steps 20

# Terminal 5: Publicador Dominio B (calidad del aire)
python scripts/run_publisher.py --domain air --comuna Santiago --peer-id publisher-b \
    --host 127.0.0.1 --port 9101 --seed-id peer-1 --seed-host 127.0.0.1 --seed-port 9001 \
    --metrics-dir runs/local/metrics --steps 20

# Terminal 6: Frontend
python -m streamlit run civicmesh/analytics/frontend.py
```

El frontend se abre automáticamente en [http://localhost:8501](http://localhost:8501). En la barra lateral, apunta el directorio de métricas a `runs/local/metrics`.

## Pruebas (CI/CD)

Las pruebas unitarias y de integración son mandatorias y deben estar en verde en el CI antes de cualquier revisión de MR.

| Comando | Qué ejecuta |
| --- | --- |
| `make test-unit` | Tests unitarios (gossip, pubsub, generadores, analytics, network) — excluye integración TCP |
| `make test-generators` | Solo tests de generadores (Dominio A y B) |
| `make test-analytics` | Solo tests del módulo de analítica |
| `make test-network` | Solo tests del transporte TCP |
| `make test-agents` | Tests de los 3 agentes de IA |
| `make test-integration` | Tests de integración TCP multi-peer (3 peers reales en puertos efímeros) |
| `make test` | Suite completa: `test-unit` + `test-agents` + `test-integration` |

```bash
# Suite completa
make test

# Solo unitarios (rápido, sin red TCP)
make test-unit

# Solo integración TCP (levanta peers reales)
make test-integration
```

## Despliegue en Slurm (Clúster DIINF)

En el clúster DIINF, se utiliza Slurm y un filesystem compartido (shared FS). El script `slurm/run_civicmesh.sh` automatiza todo el despliegue.

### Convención de directorios (shared FS)

Toda corrida utiliza un subdirectorio bajo la variable de entorno `$CIVICMESH_RUNS`:

```text
$CIVICMESH_RUNS/<run_id>/
├── hostfile.txt     # peer_id host port (una línea por peer)
├── config.yaml      # Configuración de Pub/Sub, generadores y percepción
├── datasets/        # Dataset de calidad del aire para replay
├── metrics/         # Telemetría JSONL por peer (topic_state, network_state, message_event)
└── logs/            # stdout/stderr de cada proceso
```

En Slurm, `<run_id>` es `slurm-${SLURM_JOB_ID}`; en local se puede usar un id propio (p. ej. `local-${USER}-$(date +%s)`).

### Mapeo de procesos

| Recurso Slurm | Qué corre | Puerto(s) |
| --- | --- | --- |
| **2 nodos CPU** | 2 peers por nodo (4 peers total) — gossip + pub/sub + telemetría | 9001–9004 |
| **Nodo GPU 0** (solo CPU) | Publicador Dominio A (delitos) + Publicador Dominio B (aire) | 9100, 9101 |
| **Nodo GPU 1** (solo CPU) | Frontend Streamlit | 8501 |

### Lanzar una corrida

```bash
# 1. Definir la raíz de corridas (shared FS visible desde todos los nodos)
export CIVICMESH_RUNS=~/civicmesh-runs

# 2. Enviar el job a Slurm
sbatch slurm/run_civicmesh.sh

# 3. Monitorear el job
squeue -u $USER
tail -f $CIVICMESH_RUNS/slurm-<JOB_ID>/logs/*.out
```

### Acceso al frontend (túnel SSH)

El frontend Streamlit se lanza en un nodo GPU del clúster, que no es accesible directamente. Para acceder desde tu máquina local:

```bash
# Abrir túnel SSH hacia el nodo GPU que corre el frontend
ssh -L 8501:<gpu-host>:8501 <usuario>@<login-diinf>

# Luego abrir en el navegador:
# http://localhost:8501
```

El nombre del nodo GPU se imprime en los logs del job. Ejemplo:

```
[civicmesh] Lanzando frontend Streamlit en gpu-node-3:8501
[civicmesh] Acceso: ssh -L 8501:gpu-node-3:8501 usuario@login-diinf
```

### Experimento de caída de peers

Para probar la resiliencia ante fallos (Sección 5.3 del enunciado):

```bash
# Matar los peers de un nodo CPU (simula caída de host)
scancel --signal=TERM <step_id_del_nodo>

# O directamente desde dentro del nodo:
ssh <cpu-host> "pkill -f run_peer.py"
```

Los peers sobrevivientes detectarán la caída por timeout de gossip y las métricas reflejarán la degradación en el frontend.

## Frontend de Analítica (UI)

El dashboard de CivicMesh muestra en tiempo real:

1. **Estado por tópico × canal:** último valor objetivo y subjetivo por comuna.
2. **Convergencia entre peers:** dispersión (spread), estado convergido/divergente.
3. **Brecha percepción vs realidad:** gap absoluto promedio con normalización por dominio.
4. **Estado de red:** peers vivos/muertos, porcentaje de disponibilidad.
5. **Propagación Pub/Sub:** mensajes recibidos, descartados, saltos promedio/máximos.

### Cómo abrir la UI

| Entorno | Comando | URL |
| --- | --- | --- |
| **Docker Compose** | `make up` | [http://localhost:8501](http://localhost:8501) |
| **Local (sin Docker)** | `make frontend` o `python -m streamlit run civicmesh/analytics/frontend.py` | [http://localhost:8501](http://localhost:8501) |
| **Clúster DIINF** | Se lanza automáticamente por `sbatch`. Conectar con túnel SSH. | `ssh -L 8501:<gpu-host>:8501 usuario@login-diinf` → [http://localhost:8501](http://localhost:8501) |
| **Demo (sin malla activa)** | `make demo-metrics` y luego `make frontend` | [http://localhost:8501](http://localhost:8501) (apuntar a `runs/demo/metrics`) |

En la barra lateral del dashboard se configura el directorio de métricas, la tolerancia de convergencia, el dominio (`air`/`crime`) y la comuna a visualizar.

## Seeds y Dataset de Calidad de Aire

- **Seeds**: Para asegurar que los generadores sean reproducibles, se debe configurar el parámetro `--seed` de manera fija (default: `42` en `config.yaml`). La misma semilla produce la misma secuencia de eventos de delitos y la misma trayectoria de percepción.
- **Dataset**: La información base sobre la calidad del aire está en `datasets/dataset_aire.json`. Para regenerar o actualizar el dataset desde Open-Meteo:

```bash
python scripts/fetch_open_meteo.py
```
