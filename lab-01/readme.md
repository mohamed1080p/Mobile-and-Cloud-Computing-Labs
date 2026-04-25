# Lab 1: Exploring Cloud Virtualization and Data Center Architecture

**Course:** Cloud and Mobile Computing  
**Student:** Mohamed  
**Environment:** Windows 11 + WSL2 (Ubuntu 24.04) + Docker Desktop + AWS EC2

---

## Learning Objectives

By the end of this lab:
1. Understand the difference between VMs and containers in practice.
2. Deploy and compare instances on cloud and local environments.
3. Analyze tail latency patterns in a simulated web service.
4. Experiment with virtualization overhead and container density.

---

## Tools Used

- WSL2 (Ubuntu 24.04) — used as the local VM substitute
- Docker Desktop v29.4.0 with WSL2 backend
- AWS EC2 (t3.micro, Ubuntu 24.04) — Free Tier
- Apache Bench (`ab`) for load testing
- Flask (Python) for the web service simulation

---

## Part A: VMs vs Containers — Resource Comparison

### Setup

A Docker Ubuntu container was launched using:

```bash
docker run -it --name test-container ubuntu /bin/bash
```

Resource usage was measured inside the container using `free -h`, `ps aux`, and `df -h`, then compared with the same commands run in WSL2 (acting as the VM).

### Results

| Metric | WSL2 (VM substitute) | Docker Container |
|---|---|---|
| Startup time | ~30–60 seconds (full OS init) | ~3 seconds |
| Running processes | 9+ (systemd, redis, journald, etc.) | 2 (bash + ps) |
| Memory used | ~846 MB | ~889 MB (shared with host) |
| Disk layout | Complex (Windows drives, WSL mounts) | Simple overlay filesystem |

### Analysis

The container had only **2 running processes** compared to WSL's **9+ background services** (including systemd, redis-server, journald, packagekit, and wsl-pro-service). This demonstrates the core advantage of containers: they are isolated, minimal environments that only run what the application needs — nothing more.

VMs (and WSL as a VM substitute) carry significant OS overhead because they boot a full operating system with all its background services. Containers skip this entirely by sharing the host OS kernel, which is why they start in seconds and have far fewer processes.

---

## Part B: Cloud Infrastructure Exploration (AWS EC2)

### Setup

A **t3.micro** EC2 instance running Ubuntu 24.04 was launched on AWS. The instance was accessed via SSH from WSL:

```bash
ssh -i ~/lab-key.pem ubuntu@<public-ip>
```

### Nitro Hypervisor Exploration

**Command 1:**
```bash
dmesg | grep -i nitro
```
**Result:** `dmesg: read kernel buffer failed: Operation not permitted`

**Command 2:**
```bash
sudo dmidecode | grep -A3 "System Information"
```
**Result:**
```
System Information
    Manufacturer: Amazon EC2
    Product Name: t3.micro
    Version: Not Specified
```

### Analysis

The `dmesg` command was blocked even with root-level access. This is intentional — AWS Nitro enforces strict kernel isolation, preventing even the guest OS from reading low-level kernel logs. This demonstrates how Nitro uses dedicated hardware components (separate cards for networking, storage, and security) to enforce isolation at the hardware level rather than software.

The `dmidecode` output confirmed that the instance is running on AWS infrastructure (`Manufacturer: Amazon EC2`), and `htop` was used to observe the minimal set of processes running on a fresh cloud instance.

**Key insight:** The fact that Nitro is *visible* (via dmidecode) but *not accessible* (blocked dmesg) perfectly illustrates AWS's security model — the hypervisor is transparent enough to identify but locked down enough to prevent tampering.

---

## Part C: Tail Latency Simulation

### Setup

A Flask web application was created that introduces artificial random delays using an exponential distribution (simulating real-world unpredictable response times):

```python
from flask import Flask
import time, random

app = Flask(__name__)

@app.route('/')
def hello():
    delay = random.expovariate(1/0.1)
    time.sleep(delay)
    return f"Response after {delay:.2f} seconds"

app.run(host='0.0.0.0', port=5000)
```

Apache Bench was used to send **100 requests with 10 concurrent users**:

```bash
ab -n 100 -c 10 http://localhost:5000/
```

### Results

```
Concurrency Level:      10
Time taken for tests:   1.897 seconds
Complete requests:      100
Failed requests:        0
Requests per second:    52.73 [#/sec] (mean)

Connection Times (ms)
              min  mean[+/-sd] median   max
Processing:    12   129  108.9    101     592

Percentage of the requests served within a certain time (ms):
  50%    101
  66%    133
  75%    184
  80%    199
  90%    282
  95%    355
  98%    437
  99%    592
 100%    592 (longest request)
```

### Analysis

The results clearly demonstrate **tail latency behavior**:

- The **median (p50)** response time was **101ms** — most requests are fast.
- The **p90** reached **282ms** — already 2.8x the median.
- The **p99** reached **592ms** — nearly **6x the median**.

This gap between the median and the tail (p99) is the core concept of tail latency. In a real distributed system, if a single request fans out to 10 backend services, the total response time is determined by the **slowest** sub-request — meaning even a small percentage of slow responses can dominate the user-perceived latency. This is why Google and other large-scale systems invest heavily in techniques like hedged requests and load balancing to reduce tail latency.

---

## Deliverable 3: VM vs Container for Microservices

**Which architecture is better for microservices, and why?**

**Containers are significantly better for microservices.** Here's why:

1. **Startup time:** Containers start in seconds. Microservices need to scale up and down rapidly — waiting 60 seconds for a VM to boot is unacceptable.

2. **Resource efficiency:** As shown in Part A, a container runs with only 2 processes vs a VM's 9+. In a microservices system with dozens of services, this difference multiplies dramatically.

3. **Isolation per service:** Each microservice can be packaged in its own container with its exact dependencies, avoiding version conflicts between services.

4. **Orchestration:** Tools like Kubernetes are built around containers, enabling automatic scaling, health checks, and rolling deployments that would be far heavier with VMs.

VMs are still preferred when you need **strong security isolation** (e.g., multi-tenant environments where different customers' workloads must not share a kernel) or when running services that require a **different OS kernel** than the host.

---

## Discussion Questions

**Q: Why does AWS split Nitro into hardware components?**  
By offloading networking, storage I/O, and security monitoring to dedicated hardware cards, AWS frees the host CPU entirely for the guest VM's workload. This improves performance (no hypervisor tax on CPU), security (hardware-enforced isolation), and reliability (each component fails independently).

**Q: In which scenarios would you use VMs over containers?**  
VMs are preferred when: (1) strong security isolation is required between different tenants, (2) the workload needs a different OS kernel than the host, (3) compliance regulations require full OS separation, or (4) running legacy applications that assume full OS ownership.

**Q: How does tail latency change with the number of parallel calls?**  
Tail latency gets significantly worse with fan-out. If a request depends on N parallel sub-calls, the total latency is the **maximum** of all N responses. As N increases, the probability that at least one sub-call hits the slow tail approaches 1. For example, with p99 = 592ms, a request that fans out to just 5 services has roughly a 5% chance of hitting the tail — making the user-perceived p99 much higher than any single service's p99.
