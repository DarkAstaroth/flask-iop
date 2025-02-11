from flask import Flask, render_template, request, jsonify

import json
import datetime

app = Flask(__name__)

# Ruta para recibir los logs
@app.route('/logs', methods=['POST'])
def receive_logs():
    # Obtener los datos JSON de la solicitud
    log_data = request.json

    # Verificar si los datos están presentes
    if not log_data:
        return jsonify({"error": "No se recibieron datos"}), 400

    # Registrar los datos en un archivo de logs
    try:
        with open("kong_logs.log", "a") as log_file:
            timestamp = datetime.datetime.now().isoformat()
            log_entry = {
                "timestamp": timestamp,
                "data": log_data
            }
            log_file.write(json.dumps(log_entry) + "\n")
    except Exception as e:
        return jsonify({"error": f"Error al escribir en el archivo de logs: {str(e)}"}), 500

    # Devolver una respuesta exitosa

@app.route('/')
def index():
  return render_template('index.html')

if __name__ == '__main__':
  app.run(port=5000)
