# Lab 3: Containerization and Cluster Orchestration
**Environment:** Windows 11 + WSL2 (Ubuntu 24.04) + Docker Desktop v29.4.0 + kind v0.23.0 + kubectl v1.36.0

---

## Overview

This lab covers Linux container isolation mechanisms (namespaces and cgroups), Docker image layering and multi-stage builds, and Kubernetes orchestration including scheduling, self-healing, and health probes — all running locally using kind (Kubernetes in Docker).

---

## Tools Used

- Docker Desktop v29.4.0 with WSL2 backend
- kind v0.23.0 (Kubernetes in Docker)
- kubectl v1.36.0
- Ubuntu 22.04 (container base image)
- Python 3.12-slim (application base image)
- Flask 3.0.0

---

## Part A: Containers, Namespaces, and cgroups

### Task A1: Interactive Container — Namespace Isolation

An Ubuntu 22.04 container was launched interactively:

```bash
docker run --rm -it --name nsdemo ubuntu:22.04 bash
```

The following commands were run inside the container:

```bash
hostname       # shows container's own isolated hostname
ps -ef         # shows only 2 processes: bash and ps
mount | head   # shows container's own isolated filesystem mounts
cat /proc/1/cgroup  # shows cgroup membership
```

**Observations:**
- The container had its own unique hostname (e.g. `719a210657a4`)
- Only 2 processes were visible inside the container — complete isolation from the host's 9+ processes
- The mount table showed a simple overlay filesystem, not the host's complex WSL mounts
- `/proc/1/cgroup` confirmed the container is controlled by Docker's cgroup hierarchy

### Task A2: Host vs Container Process View

From the host, the container's real PID was retrieved:

```bash
docker inspect nsdemo --format "{{.State.Pid}}"
# Result: 515

ps -fp 515
```

**Key finding:** Inside the container, bash thinks it is **PID 1** — the first and only process. On the host, the same process is **PID 515**. This is the **PID namespace** in action: each container gets its own isolated process numbering starting from 1, completely separate from the host's process table.

### Task A3: Resource Limits with cgroups

A container was launched with explicit CPU and memory limits:

```bash
docker run --rm -it --cpus="0.5" --memory="256m" ubuntu:22.04 bash
```

Inside the container, the `stress` tool was installed and used to generate load:

```bash
apt-get update && apt-get install -y stress
stress --cpu 2 --vm 1 --vm-bytes 220M --timeout 30
```

`docker stats` in a second terminal confirmed that CPU usage was capped at ~50% and memory stayed within the 256MB ceiling despite the stress tool attempting to use more.

### Analysis

Namespaces and cgroups serve complementary roles:

- **Namespaces** control *what* a process can see — its own PID space, hostname, network interface, and filesystem. The container is unaware that the host has hundreds of other processes.
- **cgroups** control *how much* of a resource a process can use — CPU, memory, disk I/O. Without cgroups, a container could consume all host resources and starve other containers.

A container runtime (like Docker) combines both to create a manageable, isolated execution unit. Namespaces alone would not prevent a noisy neighbor from consuming all CPU — cgroups are essential for cluster stability.

---

## Part B: Docker Image Layering

### Task B1: Application Files

**requirements.txt:**
```
flask==3.0.0
```

**app.py:**
```python
from flask import Flask
app = Flask(__name__)

@app.route("/")
def home():
    return "Hello from Lab 3"

@app.route("/health")
def health():
    return "ok"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
```

### Task B2: Basic Image

**Dockerfile.basic:**
```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY app.py .
EXPOSE 5000
CMD ["python", "app.py"]
```

Built with:
```bash
docker build -f Dockerfile.basic -t lab3-basic .
```

**Result:** `lab3-basic` — 199MB

### Task B3: Multi-Stage Image

**Dockerfile.multistage:**
```dockerfile
FROM python:3.12-slim AS builder
WORKDIR /build
COPY requirements.txt .
RUN pip install --prefix=/install -r requirements.txt

FROM python:3.12-slim
WORKDIR /app
COPY --from=builder /install /usr/local
COPY app.py .
EXPOSE 5000
CMD ["python", "app.py"]
```

Built with:
```bash
docker build -f Dockerfile.multistage -t lab3-multi .
```

**Result:** `lab3-multi` — 184MB

### Comparison Table

| Property | lab3-basic | lab3-multi |
|---|---|---|
| Size | 199MB | 184MB |
| Build stages | 1 | 2 |
| pip cache in final image | Yes | No (discarded) |
| Build tools in final image | Yes | No |
| Layer count | More | Fewer |

### Analysis

**Which image is smaller?** `lab3-multi` at 184MB — 15MB smaller than `lab3-basic`.

**Which steps are cached if only app.py changes?** The `pip install` layer is cached in both images because `requirements.txt` didn't change. Docker detects this and reuses the cached layer. Only the `COPY app.py` step re-runs, making rebuilds much faster.

**Why does layer order matter?** Docker builds images top to bottom and caches each layer. If a layer changes, all layers below it are invalidated. By placing rarely-changing steps (installing dependencies) before frequently-changing ones (copying app code), we maximize cache reuse and minimize build time.

---

## Part C: Local Kubernetes Orchestration with kind

### Task C1: Create the Cluster

```bash
kind create cluster --name lab3-cluster
kubectl cluster-info
kubectl get nodes -o wide
```

**Result:**
```
NAME                         STATUS   ROLES           AGE   VERSION
lab3-cluster-control-plane   Ready    control-plane   3m    v1.30.0
```

A single-node Kubernetes cluster was created successfully inside Docker.

### Task C2: Load Images into kind

```bash
kind load docker-image lab3-basic --name lab3-cluster
kind load docker-image lab3-multi --name lab3-cluster
```

### Task C3: Deploy a Replicated Application

**deployment.yaml:**
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: lab3-web
spec:
  replicas: 3
  selector:
    matchLabels:
      app: lab3-web
  template:
    metadata:
      labels:
        app: lab3-web
    spec:
      containers:
      - name: web
        image: lab3-multi
        imagePullPolicy: Never
        ports:
        - containerPort: 5000
```

**service.yaml:**
```yaml
apiVersion: v1
kind: Service
metadata:
  name: lab3-web-svc
spec:
  selector:
    app: lab3-web
  ports:
  - port: 80
    targetPort: 5000
  type: ClusterIP
```

Applied with:
```bash
kubectl apply -f deployment.yaml
kubectl apply -f service.yaml
```

**Result:** 3 pods running successfully:
```
NAME                        READY   STATUS    RESTARTS   AGE
lab3-web-5d56ff7f5b-9stv7   1/1     Running   0          14s
lab3-web-5d56ff7f5b-w7lh6   1/1     Running   0          14s
lab3-web-5d56ff7f5b-xqq9p   1/1     Running   0          14s
```

### Task C4: Access the Service

```bash
kubectl port-forward service/lab3-web-svc 8080:80
curl http://localhost:8080/       # Response: "Hello from Lab 3"
curl http://localhost:8080/health # Response: "ok"
```

The application was accessible and responding correctly through the Kubernetes service.

---

## Part D: Scheduling and Placement

### Task D1: Label the Node

```bash
kubectl label nodes --all node-role=general
kubectl get nodes --show-labels
```

The label `node-role=general` was applied to the control-plane node.

### Task D2: Force Placement with Node Selector

`nodeSelector` was added to `deployment.yaml` under `spec.template.spec`:

```yaml
nodeSelector:
  node-role: general
```

After re-applying the deployment, all pods were scheduled exclusively on the labeled node.

**Reflection:** Node selectors are fundamentally different from hardcoding a machine name in traditional deployments. With a node selector, you declare *what kind of node* you need, not *which specific machine*. Kubernetes then finds a matching node automatically. This makes deployments portable, resilient (if a node goes down, pods can be rescheduled on another matching node), and maintainable (adding new nodes with the same label automatically makes them eligible for scheduling).

---

## Part E: Self-Healing and Health Probes

### Task E1: Self-Healing by Pod Deletion

One pod was manually deleted:

```bash
kubectl delete pod lab3-web-c457fd886-2n4g7
```

`kubectl get pods -w` immediately showed:

```
lab3-web-c457fd886-2n4g7   1/1     Terminating   0          2m
lab3-web-c457fd886-7l4qk   1/1     Running       0          13s  ← new pod
```

A brand-new pod (`7l4qk`) was created automatically within seconds to maintain the desired replica count of 3.

**Why is this reconciliation, not restart?** The Deployment controller continuously compares the *desired state* (3 replicas) with the *actual state*. When it detects a mismatch, it creates a new pod from scratch — not by restarting the old one. This is reconciliation: a control loop that drives the system toward the desired state regardless of how it got out of sync.

### Task E2: Readiness and Liveness Probes

**probe-deployment.yaml:**
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: lab3-web-probe
spec:
  replicas: 2
  selector:
    matchLabels:
      app: lab3-web-probe
  template:
    metadata:
      labels:
        app: lab3-web-probe
    spec:
      containers:
      - name: web
        image: lab3-multi
        imagePullPolicy: Never
        ports:
        - containerPort: 5000
        readinessProbe:
          httpGet:
            path: /health
            port: 5000
          initialDelaySeconds: 3
          periodSeconds: 5
        livenessProbe:
          httpGet:
            path: /health
            port: 5000
          initialDelaySeconds: 10
          periodSeconds: 10
```

`kubectl describe pod` confirmed both probes were active:
```
Liveness:   http-get http://:5000/health delay=10s timeout=1s period=10s
Readiness:  http-get http://:5000/health delay=3s timeout=1s period=5s
```

### Task E3: Kill Container Process

`kill 1` was run inside the container. Kubernetes detected the process death via the liveness probe and **restarted the container in place** (same pod, incremented RESTARTS counter) — unlike Task E1 where a new pod was created. This demonstrates the difference:

- **Liveness probe failure / process crash** → container is restarted inside the same pod
- **Pod deletion** → entire pod is replaced with a brand-new pod

---

## Reflection Questions

**Why do namespaces alone not guarantee fair resource use?**  
Namespaces only control visibility — what a process can see. They place no limits on how much CPU or memory a process consumes. A container using only namespaces could consume all host resources and starve other containers. cgroups are required to enforce resource limits.

**How do cgroups improve cluster stability?**  
By capping each container's CPU and memory usage, cgroups prevent any single container from monopolizing host resources. This ensures predictable performance for all workloads on the same node and prevents cascading failures caused by resource exhaustion.

**Why is Docker image layering important for large-scale orchestration?**  
In a cluster with many nodes, images must be pulled frequently. Layering allows nodes to cache shared base layers (like `python:3.12-slim`) and only download changed layers. This dramatically reduces bandwidth usage, pull times, and storage costs across the cluster.

**What does Kubernetes mean by desired state?**  
Desired state is a declaration of what you want the system to look like — for example, "3 replicas of this container running." Kubernetes continuously monitors actual state and automatically takes actions to match it, without requiring manual intervention.

**How is self-healing different from traditional manual operations?**  
In traditional deployments, a failed process requires a human to notice the failure, diagnose it, and manually restart or replace it — which can take minutes or hours. Kubernetes detects failures automatically within seconds and creates replacement pods without any human involvement.

**Why are readiness and liveness probes not interchangeable?**  
A readiness probe determines if a pod should receive traffic. A failing readiness probe removes the pod from the load balancer but keeps it running. A liveness probe determines if the container is still functional. A failing liveness probe causes Kubernetes to restart the container. A pod can be alive but not ready (still warming up), or ready but about to crash — treating them as the same would cause either premature traffic routing or unnecessary restarts.

**What is one limitation of observing scheduling in a single-node kind cluster?**  
With only one node, all pods are always placed on the same node regardless of labels or selectors. There is no real scheduling decision to observe — the scheduler has no choice. In a real multi-node cluster, the scheduler evaluates node resources, labels, taints, and affinity rules to distribute pods optimally across multiple machines.
