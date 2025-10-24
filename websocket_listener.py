from flask import Flask, request, jsonify
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Initialize Flask app
app = Flask(__name__)

@app.route('/webhook', methods=['POST'])
def wowza_webhook():
    """
    Endpoint to receive JSON payloads from Wowza.
    """
    try:
        # Parse the JSON payload
        payload = request.get_json()
        logging.info("Received payload: %s", payload)

        # Print the payload to the terminal
        print("Received Webhook:", payload)

        return jsonify({"status": "success"}), 200
    except Exception as e:
        logging.error("An error occurred: %s", e)
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == '__main__':
    # Run the Flask app
    app.run(host='0.0.0.0', port=8080)