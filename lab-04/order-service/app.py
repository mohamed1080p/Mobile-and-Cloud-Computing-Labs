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
