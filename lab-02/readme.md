# Lab 2: Distributed Consistency and Consensus in the Cloud 
**Environment:** Windows 11 + WSL2 (Ubuntu 24.04) + Docker Desktop v29.4.0

---

## Overview

This lab explores how distributed systems handle consistency, availability, and consensus under different conditions using Redis (replication and eventual consistency) and etcd (Raft consensus protocol).

---

## Tools Used

- Docker Desktop v29.4.0 with WSL2 backend
- Redis 7 (two containers: primary + replica)
- etcd v3.5.9 (quay.io/coreos/etcd)
- Docker Compose

---

## Setup

The following `docker-compose.yml` was used to spin up all containers:

```yaml
services:
  redis-node1:
    image: redis:7
    container_name: redis-node1
    ports:
      - "6379:6379"

  redis-node2:
    image: redis:7
    container_name: redis-node2
    command: redis-server --replicaof redis-node1 6379
    ports:
      - "6380:6379"
    depends_on:
      - redis-node1

  etcd:
    image: quay.io/coreos/etcd:v3.5.9
    container_name: etcd
    command:
      - etcd
      - --advertise-client-urls=http://0.0.0.0:2379
      - --listen-client-urls=http://0.0.0.0:2379
    ports:
      - "2379:2379"
```

Started with:

```bash
docker-compose up -d
```

---

## Task 1: Redis Replication and CAP Theorem

### Step 1: Write a key to the primary node

```bash
docker exec -it redis-node1 redis-cli set mykey "hello from node1"
```

**Result:** `OK`

### Step 2: Read from the replica

```bash
docker exec -it redis-node2 redis-cli get mykey
```

**Result:** `"hello from node1"`

This confirms that replication is working — the key written to node1 was successfully replicated to node2.

### Step 3: Simulate a network partition

Node2 was stopped to simulate a network partition:

```bash
docker stop redis-node2
```

A new key was written to node1 while node2 was down:

```bash
docker exec -it redis-node1 redis-cli set afterpartition "this was written during partition"
```

**Result:** `OK` — node1 continued accepting writes even with node2 unavailable.

### Step 4: Restore and observe eventual consistency

Node2 was restarted:

```bash
docker start redis-node2
```

After a few seconds, the key was read from node2:

```bash
docker exec -it redis-node2 redis-cli get afterpartition
```

**Result:** `"this was written during partition"`

Node2 successfully caught up with the missed write after reconnecting.

### Analysis

This experiment demonstrates Redis's position on the **AP side of the CAP theorem**:

- **Available:** Node1 kept accepting reads and writes during the partition without waiting for node2.
- **Eventually Consistent:** Once node2 reconnected, it synced the missed data automatically.
- **Not Strongly Consistent:** During the partition, node2 would have returned stale data (or nothing) if queried.

Redis prioritizes availability over strong consistency, making it ideal for use cases like caching and session storage where temporary inconsistency is acceptable.

---

## Task 2: Raft Consensus with etcd

### Step 1: Write a key-value pair

```bash
docker exec -it etcd etcdctl put foo bar
```

**Result:** `OK`

### Step 2: Read the value back

```bash
docker exec -it etcd etcdctl get foo
```

**Result:**
```
foo
bar
```

### Step 3: Observe cluster status and leader

```bash
docker exec -it etcd etcdctl endpoint status --write-out=table
```

**Result:**
```
+----------------+------------------+---------+---------+-----------+------------+-----------+------------+--------------------+--------+
|    ENDPOINT    |        ID        | VERSION | DB SIZE | IS LEADER | IS LEARNER | RAFT TERM | RAFT INDEX | RAFT APPLIED INDEX | ERRORS |
+----------------+------------------+---------+---------+-----------+------------+-----------+------------+--------------------+--------+
| 127.0.0.1:2379 | 8e9e05c52164694d |   3.5.9 |   20 kB |      true |      false |         2 |          5 |                  5 |        |
+----------------+------------------+---------+---------+-----------+------------+-----------+------------+--------------------+--------+
```

Key observations:
- **IS LEADER: true** — this node is the current Raft leader
- **RAFT TERM: 2** — the cluster has completed 2 election cycles
- **RAFT INDEX: 5** — 5 operations have been committed to the Raft log

### Step 4: Stop etcd and observe unavailability

```bash
docker stop etcd
docker exec -it etcd etcdctl get foo
```

**Result:**
```
Error response from daemon: container ... is not running
```

The cluster became completely unavailable once the leader went down — no reads or writes were possible.

### Analysis

This experiment demonstrates etcd's position on the **CP side of the CAP theorem**:

- **Consistent:** etcd uses the Raft consensus protocol to guarantee that all reads and writes go through the elected leader, ensuring no stale data is ever served.
- **Partition tolerant:** In a multi-node setup, etcd requires a quorum (majority) before accepting any write, preventing split-brain scenarios.
- **Not Always Available:** When the leader went down, the cluster refused all requests rather than risk returning inconsistent data.

This behavior is exactly what is needed for use cases like distributed configuration management and leader election, where correctness is more important than availability.

---

## Redis vs etcd — CAP Theorem Comparison

| Property | Redis | etcd |
|---|---|---|
| CAP choice | AP (Available + Partition tolerant) | CP (Consistent + Partition tolerant) |
| During partition | Continues serving reads/writes | Refuses all requests |
| Data guarantee | Eventual consistency | Strong consistency (linearizable) |
| Consensus protocol | None (simple replication) | Raft |
| Best used for | Caching, sessions, queues | Config storage, service discovery, leader election |

---

## Discussion Questions

**Q: What is the CAP theorem and how did you observe it in this lab?**  
The CAP theorem states that a distributed system can only guarantee two of three properties at the same time: Consistency, Availability, and Partition tolerance. In this lab, Redis demonstrated AP behavior by staying available during a partition at the cost of temporary inconsistency. etcd demonstrated CP behavior by refusing to serve requests when the leader was unavailable, guaranteeing that no stale data was ever returned.

**Q: What is Raft and why does etcd use it?**  
Raft is a consensus algorithm designed to make distributed systems agree on a single value even in the presence of failures. etcd uses Raft to elect a leader node that handles all writes. Every write is replicated to a majority of nodes before being acknowledged, ensuring no data is lost even if some nodes fail. This makes etcd reliable for storing critical configuration data.

**Q: What is eventual consistency and when is it acceptable?**  
Eventual consistency means that if no new updates are made, all replicas will eventually converge to the same value — but they may be temporarily out of sync. This is acceptable in scenarios where small delays in data propagation do not cause serious problems, such as caching, user session storage, or social media feeds. It is not acceptable for financial transactions or any system where reading stale data could cause incorrect behavior.
