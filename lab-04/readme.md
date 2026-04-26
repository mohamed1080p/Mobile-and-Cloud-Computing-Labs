# Lab 4: Microservices and Cloud-Native Design
**Environment:** Windows 11 + WSL2 (Ubuntu 24.04) + Docker Desktop v29.4.0

---

## Overview

This lab implements a mini e-commerce backend using two microservices: `product-service` and `order-service`. The system demonstrates cloud-native design principles including stateless services, environment-based configuration, health checks, service-to-service communication, and resilience through retry logic.

---

## Project Structure

```
week4-lab/
├── docker-compose.yml
├── product-service/
│   ├── app.py
│   ├── requirements.txt
│   └── Dockerfile
└── order-service/
    ├── app.py
    ├── requirements.txt
    └── Dockerfile
```

---

## Architecture

| Component | Technology | Responsibility |
|---|---|---|
| product-service | Python Flask | Returns product data from an in-memory catalog |
| order-service | Python Flask + requests | Creates orders after validating with product-service |
| Docker Compose | Container orchestration | Runs both services with networking and health checks |

---

## Part B: product-service Implementation

**requirements.txt:**
```
flask==3.0.3
```

**app.py:**
```python
from flask import Flask, jsonify

app = Flask(__name__)

PRODUCTS = {
    1: {"id": 1, "name": "Laptop", "price": 1200},
    2: {"id": 2, "name": "Phone", "price": 650},
    3: {"id": 3, "name": "Headphones", "price": 120}
}

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"service": "product-service", "status": "up"}), 200

@app.route("/products/<int:product_id>", methods=["GET"])
def get_product(product_id):
    product = PRODUCTS.get(product_id)
    if product:
        return jsonify(product), 200
    return jsonify({"error": "Product not found"}), 404

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001)
```

**Key design decisions:**
- The service is stateless — all data lives in an in-memory dictionary with no dependency on local files or sessions
- The `/health` endpoint enables orchestration platforms to monitor service availability
- JSON responses make the API compatible with any language or framework calling it

---

## Part C: order-service Implementation

**requirements.txt:**
```
flask==3.0.3
requests==2.32.3
```

**app.py:**
```python
import os
import time
import requests
from flask import Flask, jsonify, request

app = Flask(__name__)

PRODUCT_SERVICE_URL = os.getenv("PRODUCT_SERVICE_URL", "http://product-service:5001")

def fetch_product(product_id, retries=2, delay=1):
    url = f"{PRODUCT_SERVICE_URL}/products/{product_id}"
    for attempt in range(retries + 1):
        try:
            response = requests.get(url, timeout=2)
            return response
        except requests.exceptions.RequestException:
            if attempt < retries:
                time.sleep(delay)
            else:
                return None

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"service": "order-service", "status": "up"}), 200

@app.route("/orders", methods=["POST"])
def create_order():
    data = request.get_json()
    product_id = data.get("product_id")
    quantity = data.get("quantity", 1)

    response = fetch_product(product_id)

    if response is None:
        return jsonify({"error": "product-service unavailable"}), 503

    if response.status_code != 200:
        return jsonify({"error": "invalid product"}), 400

    product = response.json()
    total = product["price"] * quantity

    return jsonify({
        "message": "Order created",
        "product": product["name"],
        "quantity": quantity,
        "total_price": total
    }), 201

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5002)
```

**Key design decisions:**
- `PRODUCT_SERVICE_URL` is read from an environment variable — the address is never hardcoded
- `fetch_product()` implements timeout (2s) and retry (2 attempts) for basic resilience
- The service returns HTTP 503 when product-service is unreachable, giving callers a clear signal

---

## Part D: Dockerfiles

**product-service/Dockerfile:**
```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py .
EXPOSE 5001
CMD ["python", "app.py"]
```

**order-service/Dockerfile:**
```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py .
EXPOSE 5002
CMD ["python", "app.py"]
```

Each service has its own independent image — matching the microservice principle of independent deployment. `requirements.txt` is copied before `app.py` to maximize Docker layer caching.

---

## Part E: Docker Compose

**docker-compose.yml:**
```yaml
services:
  product-service:
    build: ./product-service
    container_name: product-service
    ports:
      - "5001:5001"
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:5001/health')"]
      interval: 10s
      timeout: 5s
      retries: 3
    restart: unless-stopped

  order-service:
    build: ./order-service
    container_name: order-service
    ports:
      - "5002:5002"
    environment:
      PRODUCT_SERVICE_URL: http://product-service:5001
    depends_on:
      - product-service
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:5002/health')"]
      interval: 10s
      timeout: 5s
      retries: 3
    restart: unless-stopped
```

---

## Part F: Build and Run

```bash
cd ~/week4-lab
docker compose up --build -d
docker compose ps
```

**Result:**
```
NAME              IMAGE                       STATUS
order-service     week4-lab-order-service     Up 6 minutes (healthy)
product-service   week4-lab-product-service   Up 6 minutes (healthy)
```

Both containers started successfully and passed their health checks.

---

## Part G: Functional Testing

### product-service tests

**Health check:**
```bash
curl http://localhost:5001/health
```
```json
{"service": "product-service", "status": "up"}
```

**Valid product lookup:**
```bash
curl http://localhost:5001/products/1
```
```json
{"id": 1, "name": "Laptop", "price": 1200}
```

**Invalid product lookup:**
```bash
curl http://localhost:5001/products/99
```
```json
{"error": "Product not found"}
```

### order-service test

```bash
curl -X POST http://localhost:5002/orders \
  -H "Content-Type: application/json" \
  -d '{"product_id": 1, "quantity": 2}'
```
```json
{"message": "Order created", "product": "Laptop", "quantity": 2, "total_price": 2400}
```

All endpoints returned correct responses.

---

## Part H: Failure Injection and Resilience

**Step 1:** product-service was stopped to simulate a failure:
```bash
docker stop product-service
```

**Step 2:** An order request was sent while product-service was down:
```bash
curl -X POST http://localhost:5002/orders \
  -H "Content-Type: application/json" \
  -d '{"product_id": 2, "quantity": 1}'
```

**Result** (after ~6 seconds of retries):
```json
{"error": "product-service unavailable"}
```

**Step 3:** product-service was restarted:
```bash
docker start product-service
docker compose ps
```

Both services returned to healthy status immediately.

**What happened during the failure:**
- order-service attempted to reach product-service 3 times (1 initial + 2 retries) with 1 second delay between each
- After all retries were exhausted, it returned HTTP 503 with a clear error message
- The service did not crash — it degraded gracefully
- Once product-service restarted, Docker's `restart: unless-stopped` policy kept it running and the system recovered automatically

---

## Part I: Architecture Reflection

### Which parts show the benefits of microservices over a monolith?

**Independent deployment:** Each service has its own Dockerfile and image. product-service can be updated, rebuilt, and redeployed without touching order-service. In a monolith, any change requires redeploying the entire application.

**Independent scaling:** If product lookups become a bottleneck, only product-service needs to be scaled horizontally. In a monolith, the entire application must be scaled even if only one feature is under load.

**Technology isolation:** Each service manages its own dependencies in its own `requirements.txt`. They could use different languages or frameworks entirely without affecting each other.

### Which new complexities were introduced by splitting into two services?

**Network dependency:** order-service now depends on a network call to product-service. In a monolith, this would be a simple in-process function call that never fails due to network issues.

**Distributed failure modes:** When product-service goes down, order-service must handle that failure gracefully. In a monolith, a failure in the product lookup module would cause an exception in the same process — simpler to catch and handle.

**Operational overhead:** Two services means two sets of logs, two health checks, two images to build, and two containers to manage. This overhead grows with every new service added.

**Latency:** Every order request now includes a synchronous HTTP call to another service. Network latency, even on localhost, adds overhead that would not exist in a monolith.

### What would break if network latency increased or one service became slow?

With increased latency, the 2-second timeout in `fetch_product()` would trigger more frequently, causing orders to fail even when product-service is technically running. The retry logic would add up to 6 seconds of wait time per failed request (3 attempts × 2 seconds timeout), making the order endpoint very slow from the user's perspective.

If product-service became slow but not completely down, every order request would block for up to 6 seconds before completing or failing. Under high load, this would cause request queuing and potentially exhaust order-service's connection pool — a cascading failure pattern known as the "slow dependency" problem.

### Which 12-factor app principles are visible in this implementation?

**Factor III — Config:** `PRODUCT_SERVICE_URL` is read from an environment variable, not hardcoded. The same image can run in development, staging, or production by changing the environment variable alone.

**Factor VI — Processes:** Both services are stateless. They store no data locally between requests. The in-memory product catalog is read-only and identical on every instance, so multiple replicas would behave consistently.

**Factor VII — Port binding:** Each service exposes itself on a port (`5001`, `5002`) and is self-contained — no external web server is needed.

**Factor VIII — Concurrency:** The services can be scaled by running multiple container instances behind a load balancer without any code changes.

**Factor XI — Logs:** Flask writes logs to stdout by default, which Docker captures and makes available via `docker compose logs`. This matches the 12-factor principle of treating logs as event streams rather than files.
