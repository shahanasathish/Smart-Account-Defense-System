from flask import Flask, render_template, request, jsonify
from simulator import run_simulation

app = Flask(__name__)

@app.get("/")
def home():
    return render_template("index.html")

@app.post("/api/simulate")
def simulate():
    data = request.get_json(silent=True) or {}
    try:
        result = run_simulation(data)
        return jsonify(result)
    except (ValueError, TypeError) as exc:
        return jsonify({"error": str(exc)}), 400

if __name__ == "__main__":
    app.run(debug=True)
