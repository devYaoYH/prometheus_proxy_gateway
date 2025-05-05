#!/usr/bin/env python3
"""
Flask server that accepts packed URL and data payloads, forwards requests to a Prometheus Pushgateway,
and provides an HTML UI to view the latest received metrics.
"""

from flask import Flask, request, jsonify, render_template_string, redirect
import logging
import base64
import json
import time
from urllib.request import Request, build_opener, URLError, HTTPHandler
from typing import Dict, Any, List, Tuple, Optional
from datetime import datetime
import html
from prometheus_client.openmetrics import parser

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Store for the latest received metrics data
latest_metrics = {
    "timestamp": None,
    "target_url": None,
    "method": None,
    "headers": None,
    "raw_data": None,
    "decoded_data": None,
    "result": None
}

# HTML Template for the index page
INDEX_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Prometheus Metrics Proxy</title>
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            line-height: 1.6;
            color: #333;
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
        }
        h1, h2 {
            color: #2c3e50;
        }
        .container {
            background-color: #f9f9f9;
            border-radius: 5px;
            padding: 20px;
            margin-bottom: 20px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        .info-group {
            margin-bottom: 15px;
        }
        .label {
            font-weight: bold;
            color: #2980b9;
        }
        .value {
            font-family: monospace;
            background-color: #f1f1f1;
            padding: 5px;
            border-radius: 3px;
            white-space: pre-wrap;
            overflow-x: auto;
        }
        .metrics-data {
            max-height: 400px;
            overflow-y: auto;
            border: 1px solid #ddd;
            padding: 10px;
            background-color: #f5f5f5;
        }
        .no-data {
            color: #7f8c8d;
            font-style: italic;
        }
        .status {
            padding: 5px 10px;
            border-radius: 3px;
            font-weight: bold;
        }
        .status-success {
            background-color: #27ae60;
            color: white;
        }
        .status-error {
            background-color: #e74c3c;
            color: white;
        }
        .refresh-button {
            background-color: #3498db;
            color: white;
            border: none;
            padding: 10px 15px;
            border-radius: 4px;
            cursor: pointer;
            font-size: 14px;
            margin-top: 20px;
        }
        .refresh-button:hover {
            background-color: #2980b9;
        }
        .header-container {
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        .timestamp {
            font-size: 14px;
            color: #7f8c8d;
        }
    </style>
</head>
<body>
    <div class="header-container">
        <h1>Prometheus Metrics Proxy</h1>
        {% if latest.timestamp %}
        <div class="timestamp">Last update: {{ latest.timestamp }}</div>
        {% endif %}
    </div>
    
    <div class="container">
        <h2>Latest Received Metrics</h2>
        
        {% if not latest.timestamp %}
        <p class="no-data">No metrics have been received yet. Use the /push_metrics endpoint to send data.</p>
        {% else %}
        
        <div class="info-group">
            <div class="label">Target URL:</div>
            <div class="value">{{ latest.target_url }}</div>
        </div>
        
        <div class="info-group">
            <div class="label">Method:</div>
            <div class="value">{{ latest.method }}</div>
        </div>
        
        <div class="info-group">
            <div class="label">Headers:</div>
            <div class="value">{{ latest.headers }}</div>
        </div>
        
        <div class="info-group">
            <div class="label">Raw Data (base64):</div>
            <div class="value" style="max-height: 100px; overflow-y: auto;">{{ latest.raw_data }}</div>
        </div>
        
        <div class="info-group">
            <div class="label">Decoded Metrics Data:</div>
            <div class="metrics-data">{{ latest.decoded_data }}</div>
        </div>
        
        <div class="info-group">
            <div class="label">Result:</div>
            <div class="value">
                <span class="status {% if latest.result.success %}status-success{% else %}status-error{% endif %}">
                    {{ latest.result.status }}
                </span>
                {% if latest.result.message %}
                <div>{{ latest.result.message }}</div>
                {% endif %}
            </div>
        </div>
        {% endif %}
    </div>
    
    <form action="/" method="get">
        <button type="submit" class="refresh-button">Refresh Page</button>
    </form>
</body>
</html>
"""

@app.route('/', methods=['GET'])
def index():
    """Display the index page with the latest metrics data"""
    # Format the latest metrics data for display
    display_data = {
        "timestamp": latest_metrics["timestamp"],
        "target_url": latest_metrics["target_url"],
        "method": latest_metrics["method"],
        "headers": json.dumps(latest_metrics["headers"], indent=2) if latest_metrics["headers"] else None,
        "raw_data": latest_metrics["raw_data"],
        "decoded_data": html.escape(latest_metrics["decoded_data"]) if latest_metrics["decoded_data"] else None,
        "result": latest_metrics["result"]
    }
    
    return render_template_string(INDEX_TEMPLATE, latest=display_data)


_LINT_SERVER_URL = "http://localhost:8080/lint"  # Example URL for a linting server


def validate_data_plaintext(data: str) -> bool:
    """Validate the plaintext metrics data to ensure it is in the correct format."""
    try:
        request_obj = Request(_LINT_SERVER_URL, data.encode('utf-8'), method='PUT')
        request_obj.add_header('Content-Type', 'text/plain')
        resp = build_opener(HTTPHandler).open(request_obj, timeout=10)
        resp_body = resp.read().decode('utf-8')
        print(f"[Lint server] Response: {resp_body}")
        # Pessimistic check: if the response code is not 200, consider it an error
        if resp.code != 200:
            logger.error(f"Lint server returned error: {resp.code} {resp.msg}")
            return False
        else:
            response = json.loads(resp_body)
            status = response.get("status", None)
            if status != "success":
                logger.error(f"Lint server returned error: {resp_body}")
                return False
        return True
    except Exception as e:
        logger.error(f"Error sending request to lint server: {str(e)}")
        return False


@app.route('/push_metrics', methods=['POST'])
def push_metrics():
    """
    Endpoint to accept a packed request containing URL, method, headers, and data,
    then forward it to the Prometheus Pushgateway.
    
    Expected JSON payload:
    {
        "target_url": "http://localhost:9090/metrics/job/example_job",
        "method": "PUT",
        "headers": {"Content-Type": "text/plain", ...},
        "data": "base64_encoded_data"
    }
    """
    try:
        # Get request data
        payload = request.get_json()
        
        if not payload:
            return jsonify({"error": "No data provided"}), 400
        
        # Extract required fields
        target_url = payload.get('target_url')
        method = payload.get('method', 'POST')  # Default to POST if not specified
        headers_dict = payload.get('headers', {})
        encoded_data = payload.get('data')
        
        # Validate required fields
        if not target_url:
            return jsonify({"error": "Missing 'target_url' parameter"}), 400
        if not encoded_data:
            return jsonify({"error": "Missing 'data' parameter"}), 400
            
        # Decode base64 data
        try:
            data = base64.b64decode(encoded_data)
            # Try to decode as UTF-8 for display purposes
            decoded_data = data.decode('utf-8', errors='replace')
        except Exception as e:
            logger.error(f"Error decoding data: {str(e)}")
            return jsonify({"error": f"Invalid base64 data: {str(e)}"}), 400
        
        print(f"[Proxy server]] Received data: \n{decoded_data}")

        # Validate the target URL
        # Extract the base URL address and check it matches the defined _PUSH_GATEWAY_URL

        # Validate metrics data
        # Alternatively, we can also log into a retry-queue system for processing later
        if not validate_data_plaintext(decoded_data):
            return jsonify({"error": "Invalid metrics data"}), 400

        # Convert headers dict back to list of tuples
        headers = [(k, v) for k, v in headers_dict.items()]
        
        # Update the latest metrics data
        latest_metrics.update({
            "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            "target_url": target_url,
            "method": method,
            "headers": headers_dict,
            "raw_data": encoded_data[:100] + "..." if len(encoded_data) > 100 else encoded_data,
            "decoded_data": decoded_data,
            "result": None  # Will be updated after forwarding
        })
        
        # Forward the request to the Pushgateway
        try:
            # Create request
            request_obj = Request(target_url, data=data)
            
            # Set request method
            request_obj.get_method = lambda: method
            
            # Add headers
            for k, v in headers:
                request_obj.add_header(k, v)
            
            # Send request
            resp = build_opener(HTTPHandler).open(request_obj, timeout=10)
            
            # Check response
            if resp.code >= 400:
                error_msg = f"Error from Pushgateway: {resp.code} {resp.msg}"
                logger.error(error_msg)
                
                # Update result in latest metrics
                latest_metrics["result"] = {
                    "success": False,
                    "status": f"Error: {resp.code}",
                    "message": error_msg
                }
                
                return jsonify({"error": error_msg}), resp.code
            
            # Update result in latest metrics
            latest_metrics["result"] = {
                "success": True,
                "status": f"Success: {resp.code}",
                "message": f"Successfully forwarded to {target_url}"
            }
            
            logger.info(f"Successfully forwarded request to {target_url}")
            return jsonify({
                "success": True, 
                "message": f"Successfully forwarded to {target_url}",
                "status_code": resp.code
            }), 200
            
        except URLError as e:
            error_msg = f"Error connecting to Pushgateway: {str(e)}"
            logger.error(error_msg)
            
            # Update result in latest metrics
            latest_metrics["result"] = {
                "success": False,
                "status": "Connection Error",
                "message": error_msg
            }
            
            return jsonify({"error": error_msg}), 500
            
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        
        # Update result in latest metrics if we have any data
        if latest_metrics["timestamp"]:
            latest_metrics["result"] = {
                "success": False,
                "status": "Server Error",
                "message": f"Unexpected error: {str(e)}"
            }
            
        return jsonify({"error": f"Unexpected error: {str(e)}"}), 500

@app.route('/health', methods=['GET'])
def health_check():
    """Simple health check endpoint"""
    return jsonify({"status": "healthy"}), 200

@app.route('/clear', methods=['GET'])
def clear_metrics():
    """Clear the latest metrics data"""
    global latest_metrics
    latest_metrics = {
        "timestamp": None,
        "target_url": None,
        "method": None,
        "headers": None,
        "raw_data": None,
        "decoded_data": None,
        "result": None
    }
    return redirect('/')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=6000, debug=False)