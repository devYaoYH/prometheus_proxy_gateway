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
from prometheus_client.parser import text_string_to_metric_families
from prometheus_client import Metric

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

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
    

def extract_metric_properties(data: str) -> Dict[str, Metric]:
    """Extract metric properties from the decoded metrics data.

    This function parses the metrics data and extracts relevant properties
    such as metric names, labels, and types. It returns a dictionary of
    metric properties.

    Example output:
        Metric Family: sample_requests
          Documentation: Total number of requests processed
          Unit: 
          Type: counter
          Labels: {'userid', 'endpoint', 'method'}

    """
    metric_properties = {}
    try:
        # Decode the data to get the metric families
        for family in text_string_to_metric_families(data):
            labels = set()
            print(f"Metric Family: {family.name}")
            print(f"  Documentation: {family.documentation}")
            print(f"  Unit: {family.unit}")
            print(f"  Type: {family.type}")
            for sample in family.samples:
                labels.update(sample.labels.keys())
            print(f"  Labels: {labels}")
            metric_properties[family.name] = family
    except Exception as e:
        logger.error(f"Error parsing metrics data: {str(e)}")
        return None
    return metric_properties


def validate_metric_properties(properties: Dict[str, Metric]) -> bool:
    """Validate the metric properties to ensure they meet certain criteria."""
    # Example validation: Check if the metric name is valid
    for key, value in properties.items():
        logger.info(f"Key: {key}, Value: {value}")
    return True


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

        # Validate metrics data format
        # Alternatively, we can also log into a retry-queue system for processing later
        if not validate_data_plaintext(decoded_data):
            return jsonify({"error": "Invalid metrics data"}), 400
        
        # Validate metrics properties
        metric_properties = extract_metric_properties(decoded_data)
        if metric_properties is None or not validate_metric_properties(metric_properties):
            return jsonify({"error": "Invalid metric properties"}), 400

        # Convert headers dict back to list of tuples
        headers = [(k, v) for k, v in headers_dict.items()]
        
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
                
                return jsonify({"error": error_msg}), resp.code
            
            logger.info(f"Successfully forwarded request to {target_url}")
            return jsonify({
                "success": True, 
                "message": f"Successfully forwarded to {target_url}",
                "status_code": resp.code
            }), 200
            
        except URLError as e:
            error_msg = f"Error connecting to Pushgateway: {str(e)}"
            logger.error(error_msg)
            
            return jsonify({"error": error_msg}), 500
            
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        return jsonify({"error": f"Unexpected error: {str(e)}"}), 500


@app.route('/health', methods=['GET'])
def health_check():
    """Simple health check endpoint"""
    return jsonify({"status": "healthy"}), 200


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=6000, debug=False)