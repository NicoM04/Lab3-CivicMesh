# Utilizando SLURM en el Clúster del DIINF

**Autor:** Cristóbal Acosta (Coordinador TI - DIINF - USACH)  
**Institución:** Departamento de Ingeniería Informática, Universidad de Santiago de Chile (USACH)  
**Fecha:** Julio 2023  

---

## 1. Hardware del Clúster

El clúster del DIINF cuenta con **1 Login Node** y **4 Compute Nodes** conectados en la Red USACH (acceso cableado).

Acceso vía SSH:
```bash
ssh username@xi.diinf.usach.cl
```

### Servidores XI NetRaider 64 LT

* **Partición BATCH (2 nodos):**
  * **CPU:** 2x 32-Core / 64-Thread 3rd Gen AMD EPYC 7513
  * **RAM:** 256GB ($16 \times 16\text{ GB}$) DDR4-3200 ECC Registered SDRAM
* **Partición GPU (2 nodos):**
  * **CPU:** 1x 24-Core / 48-Thread 3rd Gen AMD EPYC 7443P
  * **RAM:** 128GB ($8 \times 16\text{ GB}$) DDR4-3200 ECC Registered SDRAM
  * **GPU:** 2x NVIDIA A30 PCIe (24GB HBM2, 3584 CUDA Cores, 336 Tensor Cores, PCIe 4.0 x16 / 1x NVLink para A30)

---

## 2. Acceso de Usuario y Entorno

* **Sistema Operativo:** Ubuntu 22.04 LTS
* **/home/xi:** Compartido por NFS (el directorio del usuario es visible en todos los nodos).
* Dependiendo del requerimiento (`batch`, `GPU`), un usuario puede acceder a GPU o no.

### Verificación básica:
```bash
$ ssh username@xi.diinf.usach.cl
$ pwd
/home/xi/username

$ sinfo --format="%.10P %.10D %.15N"
PARTITION  NODES      NODELIST       
batch*     2          xicpu[02-03]   
GPU        2          xigpu[01-02]   
```

---

## 3. Software Disponible

* **SLURM:** 22.05.2
* **Compiladores:** C/C++ 11.3.0
* **MPI:** OpenMPI 4.0.4
* **Python:** 3.10.6
* **Software Científico:**
  * MATLAB R2021a
  * COMSOL Multiphysics Module AC/DC
* **Drivers & SDKs NVIDIA:**
  * NVIDIA Driver 525.125.06 – CUDA 12.0
  * NVIDIA HPC-SDK 22.1

---

## 4. ¿Qué es SLURM?

SLURM es un sistema de administración de clústeres y planificación de trabajos (*job scheduler*) para clústeres Linux.
* Permite encolar $N$ trabajos en el clúster.
* Se encarga de planificar **cuándo** y **dónde** se ejecutan.
* *Referencia:* [Quick Start User Guide](https://slurm.schedmd.com/quickstart.html)

### Definiciones Principales:
* **Node:** Recurso computacional individual (servidor).
* **Partition:** Conjunto lógico de nodos (un nodo puede pertenecer a varias particiones). Funciona como una cola (*queue*) con ciertas restricciones y prioridades.
* **Job:** Cantidad de recursos asignados a un usuario por un tiempo determinado.
* **Job Step:** Conjunto de tareas (posiblemente paralelas) dentro de un Job.

---

## 5. Comandos Principales de SLURM

| Comando | Descripción |
| :--- | :--- |
| `sinfo` | Muestra información sobre nodos y particiones. |
| `srun` | Planifica y ejecuta un trabajo o paso de trabajo de forma interactiva/inmediata. |
| `squeue` | Consulta el estado de los trabajos en las colas/particiones. |
| `scancel` | Cancela o envía señales a trabajos o pasos en ejecución. |
| `salloc` | Asigna recursos en tiempo real (por ejemplo, para sesiones interactivas). |
| `sbatch` | Envía un script por lotes (*batch script*) para ser procesado por el planificador. |
| `sacct` | Muestra datos de contabilidad/historial de recursos de los trabajos ejecutados. |
| `scontrol`| Herramienta administrativa y de monitoreo detallado del estado del clúster. |

---

## 6. Ejemplos de Uso de Comandos

### `sinfo`
Muestra el estado de las particiones y nodos:
```bash
$ sinfo
PARTITION AVAIL  TIMELIMIT  NODES  STATE NODELIST
batch*       up   infinite      2   idle xicpu[02-03]
GPU          up   infinite      2   down xigpu[01-02]

# Ver motivos de nodos no disponibles:
$ sinfo -R  # --list-reasons
REASON             USER  TIMESTAMP           NODELIST
En mantencion      root  2023-07-04T11:38:47 xigpu[01-02]

# Formato personalizado:
$ sinfo --format="%.10P %.10a %.10D %.10T %.15N"
PARTITION  AVAIL      NODES      STATE      NODELIST       
batch*     up         2          idle       xicpu[02-03]   
GPU        up         2          down       xigpu[01-02]   
```

---

### `srun`
Ejecución interactiva o inmediata de tareas:
```bash
# Ejecutar un comando en un nodo:
$ srun /bin/hostname
xicpu02

# Ejecutar en 2 nodos:
$ srun -N 2 /bin/cat /etc/hostname
xicpu02
xicpu03

# Manejo de errores:
$ srun -N 2 /bin/false
srun: error: xicpu02: task 0: Exited with exit code 1
srun: error: xicpu03: task 1: Exited with exit code 1

# Especificar 2 nodos y 3 tareas:
$ srun -N 2 -n 3 /bin/hostname
xicpu03
xicpu02
xicpu02
```

---

### `squeue`
Monitoreo de trabajos en cola y en ejecución:
```bash
# Ejemplo lanzando trabajos de fondo:
$ srun -N 2 -n 5 -J hang01 hang &
$ srun -N 2 -n 5 -J hang02 hang &

# Salida estándar:
$ squeue
   JOBID PARTITION     NAME     USER ST       TIME  NODES NODELIST(REASON)
     504     batch   hang01 slurmtes  R      24:54      2 xicpu[02-03]
     505     batch   hang02 slurmtes  R      24:51      2 xicpu[02-03]

# Formato extendido:
$ squeue --format="%.6i %.13P %.13j %.10u %.10T %.10M %.15l %.10D %.20R"
 JOBID PARTITION     NAME          USER      STATE      TIME       TIME_LIMIT      NODES NODELIST(REASON)    
   504 batch         hang01        slurmtest RUNNING    3:56       UNLIMITED           2 xicpu[02-03]        
   505 batch         hang02        slurmtest RUNNING    3:53       UNLIMITED           2 xicpu[02-03]        
```

---

### `scancel`
Cancelar trabajos en ejecución o en espera:
```bash
$ scancel 504
srun: Job step aborted: Waiting up to 32 seconds for job step to finish.
slurmstepd: error: *** STEP 504.0 ON xicpu02 CANCELLED AT 2023-07-06T11:24:37 ***
srun: error: xicpu03: task 4: Terminated
srun: error: xicpu02: tasks 0-3: Terminated
[1]-  Exit 143                srun -N 2 -n 5 -J hang01 hang
```

---

### `salloc`
Asignación interactiva de recursos:
```bash
# Solicitar asignación en GPU: 1 nodo, 1 hora, 1GB por CPU
$ salloc -p GPU -N 1 -t 01:00:00 --mem-per-cpu=1G
salloc: Granted job allocation 488
salloc: Waiting for resource configuration
salloc: Nodes xigpu01 are ready for job

# En el nodo login falla nvidia-smi:
$ nvidia-smi -L
NVIDIA-SMI has failed

# Ejecutando mediante srun dentro de la asignación:
$ srun nvidia-smi -L
GPU 0: NVIDIA A30 (UUID: GPU-34046858-1ee2-2e76-98be-a539d0b89ebd)
```

---

### `sacct`
Consulta de contabilidad y métricas de trabajos finalizados:
* **Importante:** Liberar los recursos asignados con `exit` o `scancel` al finalizar la sesión.
```bash
$ sacct
       JobID    JobName  Partition    Account  AllocCPUS      State ExitCode 
------------ ---------- ---------- ---------- ---------- ---------- -------- 
488          interacti+        GPU    default          2    RUNNING      0:0 
488.extern       extern               default          2    RUNNING      0:0 
488.0        nvidia-smi               default          2  COMPLETED      0:0 
488.1          hostname               default          2  COMPLETED      0:0 
488.2             false               default          2     FAILED      1:0 
```

---

### `scontrol`
Inspección detallada de entidades (nodos, particiones, trabajos):
```bash
$ scontrol show node xigpu02
NodeName=xigpu02 Arch=x86_64 CoresPerSocket=24 
   CPUAlloc=0 CPUEfctv=48 CPUTot=48 CPULoad=0.16
   AvailableFeatures=(null)
   ActiveFeatures=(null)
   Gres=gpu:A30:2
   NodeAddr=xigpu02 NodeHostName=xigpu02 Version=22.05.2
   OS=Linux 5.15.0-76-generic #83-Ubuntu SMP Thu Jun 15 19:16:32 UTC 2023
   RealMemory=122240 AllocMem=0 FreeMem=126558 Sockets=1 Boards=1
   State=IDLE ThreadsPerCore=2 TmpDisk=0 Weight=1 Owner=N/A MCS_label=N/A
   Partitions=GPU 
   BootTime=2023-07-11T09:11:35 SlurmdStartTime=2023-07-11T09:11:54
   CfgTRES=cpu=48,mem=122240M,billing=48,gres/gpu=2
```

---

## 7. Ejecución de Scripts con `sbatch`

### Script Básico (`job.slurm`):
```bash
#!/bin/bash
#SBATCH --job-name=test
#SBATCH --partition=batch
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --output=job-%u-%x-%A.out    # Ej: job-slurmtest-test-509.out
#SBATCH --error=job-%A.err

/bin/hostname
```

Envío del trabajo:
```bash
$ sbatch job.slurm
Submitted batch job 509
```

---

### Job Arrays
Permiten sistematizar la creación masiva de tareas paralelas mediante la variable `$SLURM_ARRAY_TASK_ID`.

Opciones para `--array`:
* `--array=1-30`
* `--array=1,3,5,7`
* `--array=1-7:2` (genera los índices `1, 3, 5, 7`)

```bash
#!/bin/bash
#SBATCH --job-name=job_array
#SBATCH --partition=GPU
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --array=1-7:2                # Se crean 4 jobs
#SBATCH --output=job-%A_%a.out       # job-523_1.out, job-523_3.out, etc.
#SBATCH --error=job-%A_%a.err        # job-523_1.err, job-523_3.err, etc.

/bin/hostname
```

---

## 8. Contenedores en SLURM (Enroot + Pyxis)

SLURM en el clúster DIINF permite ejecutar tareas dentro de contenedores usando **Enroot** y **Pyxis**:
* **NVIDIA/Enroot:** Convierte imágenes tradicionales de contenedores/SO en *sandboxes* sin privilegios de administrador (*unprivileged*), adaptadas para HPC.
* **NVIDIA/Pyxis:** Plugin SPANK para SLURM que permite a usuarios sin privilegios ejecutar tareas dentro de contenedores mediante `srun`.

### Ejemplos con `srun`:

1. **Importar y ejecutar directamente desde Docker Hub:**
```bash
$ srun --container-image=python:3.11.4 -p batch python3 --version
pyxis: importing docker image
Python 3.11.4
```

2. **Montar rutas del host (`--container-mounts`):**
```bash
$ srun --container-image=alpine:3.18.2 -p batch     --container-mounts=/etc/os-release:/host/os-release     grep PRETTY /host/os-release
pyxis: importing docker image ...
PRETTY_NAME="Ubuntu 22.04.2 LTS"
```

3. **Descargar y guardar imagen en formato SquashFS (`.sqsh`):**
```bash
$ srun --container-image=alpine:3.18.2 -p batch     --container-save="${HOME}/enroot_images/alpine:3.18.2.sqsh"     grep PRETTY /etc/os-release
```

4. **Ejecutar usando la imagen local guardada:**
```bash
$ srun --container-image="${HOME}/enroot_images/alpine:3.18.2.sqsh" -p batch     grep PRETTY /etc/os-release
PRETTY_NAME="Alpine Linux v3.18"
```

---

### `sbatch` con GPU y Contenedor (`container-job.slurm`)

```bash
#!/bin/bash
#SBATCH --job-name=container-job
#SBATCH --partition=GPU
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --gres=gpu:A30:1             # Solicita 1 GPU (-G 1)
#SBATCH --output=job-%A.out
#SBATCH --error=job-%A.err

srun --container-image="${HOME}/enroot_images/nvidia+cuda+12.2.0-base-ubuntu22.04.sqsh"     nvidia-smi
```

Ejecución:
```bash
$ sbatch container-job.slurm
Submitted batch job 584
```

---

## 9. Demo: Entrenamiento de Clasificador

* **Dataset:** MNIST (base de datos de dígitos manuscritos).
* **Framework / Modelo:** `tf.keras.models.Sequential`
* **Flujo:**
  1. Obtención de datos.
  2. División en conjuntos de entrenamiento (*train*) y prueba (*test*).
  3. Definición y entrenamiento del modelo con aceleración por GPU.
  4. Evaluación de resultados.
* *Referencias:*
  * [MNIST Database](https://en.wikipedia.org/wiki/MNIST_database)
  * [TensorFlow Quickstart for Beginners](https://www.tensorflow.org/tutorials/quickstart/beginner)
