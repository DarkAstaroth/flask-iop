from flask import Flask, render_template, request, jsonify

import jwt
import time
import requests
import clickhouse_connect

app = Flask(__name__)

# Configuración de ClickHouse
CLICKHOUSE_HOST = "clickhouse-4bj6-production.up.railway.app"
CLICKHOUSE_PORT = 443
CLICKHOUSE_USER = "clickhouse"
CLICKHOUSE_PASSWORD = "IhaRmopenWm5lCav8huJkdmPF9bgApVN"
CLICKHOUSE_DATABASE = "railway"
CLICKHOUSE_TABLE = "bitacora"


# Conectar a ClickHouse
try:
    clickhouse_client = clickhouse_connect.get_client(
        host=CLICKHOUSE_HOST,
        port=CLICKHOUSE_PORT,
        username=CLICKHOUSE_USER,
        password=CLICKHOUSE_PASSWORD,
        database=CLICKHOUSE_DATABASE,
        secure=True,
    )
    print("Conexión exitosa a ClickHouse!")
except Exception as e:
    print(f"Error al conectar a ClickHouse: {e}")
    exit(1)


# Configuración de la API de Kong
KONG_ADMIN_URL = "https://kong-konga-production.up.railway.app"  # URL de la API administrativa de Kong


# Ruta para generar un token JWT con expiración personalizada
@app.route("/generar-token", methods=["POST"])
def generate_token():
    try:
        # Obtener los datos del cuerpo de la solicitud
        data = request.json
        unit = data.get("unit")  # Tipo de unidad (día, semana, mes)
        value = data.get("value")  # Valor (1, 2, 3, etc.)
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


# Endpoint para consultar la tabla bitacora
@app.route("/consultar-bitacora", methods=["GET"])
def consultar_bitacora():
    try:
        # Obtener parámetros de consulta
        idTransaccion = request.args.get("idTransaccion")
        usuarioConsumidor = request.args.get("usuarioConsumidor")
        estado = request.args.get("estado")
        limit = int(
            request.args.get("limit", 10)
        )  # Límite de resultados (por defecto 10)

        # Construir la consulta SQL
        query = f"SELECT * FROM {CLICKHOUSE_TABLE} WHERE 1=1"
        if idTransaccion:
            query += f" AND idTransaccion = '{idTransaccion}'"
        if usuarioConsumidor:
            query += f" AND usuarioConsumidor = '{usuarioConsumidor}'"
        if estado:
            query += f" AND estado = '{estado}'"
        query += f" LIMIT {limit}"

        # Ejecutar la consulta
        result = clickhouse_client.query(query)

        # Convertir el resultado a un formato JSON
        datos = []
        for row in result.result_rows:
            datos.append(
                {
                    "idTransaccion": row[0],
                    "idSolicitud": row[1],
                    "codTramite": row[2],
                    "nroTramite": row[3],
                    "usuarioConsumidor": row[4],
                    "entidadConsumidora": row[5],
                    "sistemaConsumidor": row[6],
                    "sistemaPublicador": row[7],
                    "servicio": row[8],
                    "entidadPublicadora": row[9],
                    "fechayHora": row[10].strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "estado": row[11],
                    "codHTTP": row[12],
                }
            )

        return jsonify({"datos": datos}), 200

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
