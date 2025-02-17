from flask import Flask, render_template, request, jsonify

import jwt
import time
import requests
import clickhouse_connect

app = Flask(__name__)


# Configuración de la API de Kong
KONG_ADMIN_URL = "https://kong-konga-production.up.railway.app"  # URL de la API administrativa de Kong


# Ruta para generar un token JWT con expiración personalizada
@app.route("/generar-token", methods=["POST"])
def generate_token():
    try:
        # Obtener los datos del cuerpo de la solicitud
        data = request.json
        unit = data.get("tipo")  # Tipo de unidad (día, semana, mes)
        value = data.get("valor")  # Valor (1, 2, 3, etc.)
        CONSUMER_USERNAME = data.get("consumidor")  # Nombre del consumidor en Kong

        # Validar los datos de entrada
        if not unit or not value:
            return jsonify({"error": "Se requieren 'unit' y 'value'"}), 400

        if unit not in ["day", "week", "month"]:
            return jsonify(
                {"error": "Unidad no válida. Use 'day', 'week' o 'month'"}
            ), 400

        try:
            value = int(value)
            if value <= 0:
                return jsonify({"error": "El valor debe ser mayor que 0"}), 400
        except ValueError:
            return jsonify({"error": "El valor debe ser un número entero"}), 400

        # Obtener los datos del consumidor desde la API de Kong
        consumer_url = f"{KONG_ADMIN_URL}/consumers/{CONSUMER_USERNAME}/jwt"
        response = requests.get(consumer_url)

        # Verificar si la solicitud fue exitosa
        if response.status_code != 200:
            return jsonify(
                {"error": "No se pudo obtener los datos del consumidor"}
            ), 500

        # Extraer la clave (key) y el secreto (secret) del consumidor
        consumer_data = response.json()
        if not consumer_data.get("data"):
            return jsonify(
                {"error": "No se encontraron credenciales JWT para el consumidor"}
            ), 404

        jwt_credentials = consumer_data["data"][0]  # Tomar la primera credencial JWT
        consumer_key = jwt_credentials.get("key")
        consumer_secret = jwt_credentials.get("secret")

        if not consumer_key or not consumer_secret:
            return jsonify(
                {"error": "El consumidor no tiene credenciales JWT válidas"}
            ), 404

        # Calcular la fecha de expiración
        current_time = int(time.time())
        if unit == "day":
            expiration_time = current_time + (value * 86400)  # 1 día = 86400 segundos
        elif unit == "week":
            expiration_time = current_time + (
                value * 604800
            )  # 1 semana = 604800 segundos
        elif unit == "month":
            expiration_time = current_time + (
                value * 2592000
            )  # 1 mes = 2592000 segundos (30 días)

        # Crear el payload del JWT con los campos adicionales
        payload = {
            "iss": consumer_key,  # Campo requerido por Kong
            "iat": current_time,  # Fecha de emisión
            "exp": expiration_time,  # Fecha de expiración
            "EntidadConsumidora": "1",  # Campo hardcodeado
            "SistemaConsumidor": "1",  # Campo hardcodeado
            "SistemaPublicador": "1",  # Campo hardcodeado
            "Servicio": "1",  # Campo hardcodeado
            "EntidadPublicadora": "entidad-publicadora",  # Campo hardcodeado
        }

        # Generar el token JWT
        token = jwt.encode(payload, consumer_secret, algorithm="HS256")
        return jsonify(
            {
                "token": token,
                "expires_in": expiration_time,
                "expires_at": time.strftime(
                    "%Y-%m-%d %H:%M:%S", time.localtime(expiration_time)
                ),
            }
        )

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/hola", methods=["GET"])
def hola():
    return jsonify({"mensaje": "Hola"}), 200


@app.route("/")
def index():
    return render_template("index.html")


if __name__ == "__main__":
    app.run(port=5000)
