from flask import Flask, render_template, request, jsonify

import jwt
import time
import requests
import clickhouse_connect
import re

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


@app.route("/crear-servicio", methods=["POST"])
def crear_servicio():
    try:
        # Obtener los datos del cuerpo de la solicitud
        data = request.json
        entidad = data.get("entidad")  # Sigla de la entidad
        version = data.get("version")  # Version del servicio
        nombre = data.get("nombre")  # Nombre del servicio

        url = data.get("url")  # URL del servicio
        token = data.get("token")  # token del servicio

        # Validar que los campos obligatorios estén presentes
        if not entidad or not version or not nombre or not url:
            return jsonify(
                {"error": "Se requieren 'entidad', 'version', 'nombre' y 'url'"}
            ), 400

        # Reemplazar espacios y caracteres no permitidos con guiones bajos
        def formatear_nombre(texto):
            # Reemplazar espacios y caracteres no permitidos con guiones bajos
            texto = re.sub(r"[^a-zA-Z0-9._-]", "_", texto)
            return texto

        entidad_formateada = formatear_nombre(entidad)
        version_formateada = formatear_nombre(version)
        nombre_formateado = formatear_nombre(nombre)

        # Formar el nombre del servicio sin caracteres no permitidos
        nombre_servicio = (
            f"{entidad_formateada}_{version_formateada}_{nombre_formateado}"
        )

        # Crear el servicio en Kong
        servicio_kong = {
            "name": nombre_servicio,  # Nombre del servicio en Kong
            "url": url,  # URL del backend
        }

        response = requests.post(f"{KONG_ADMIN_URL}/services", json=servicio_kong)

        # Verificar si la creación del servicio fue exitosa
        if response.status_code != 201:
            return jsonify(
                {
                    "error": "No se pudo crear el servicio en Kong",
                    "detalles": response.json(),
                }
            ), 500

        # Crear una ruta (route) para el servicio en Kong con barras
        ruta = f"/{entidad}/{version}/{nombre_formateado}"
        ruta_kong = {
            "paths": [f"{ruta}"],  # Ruta con barras
            "service": {"name": nombre_servicio},  # Nombre del servicio asociado
        }

        # Hacer una solicitud POST a la API de Kong para crear la ruta
        response_ruta = requests.post(f"{KONG_ADMIN_URL}/routes", json=ruta_kong)

        # Verificar si la creación de la ruta fue exitosa
        if response_ruta.status_code != 201:
            return jsonify(
                {
                    "error": "No se pudo crear la ruta en Kong",
                    "detalles": response_ruta.json(),
                }
            ), 500

        def habilitar_plugin(nombre_plugin, config=None):
            payload = {"name": nombre_plugin}
            if config:
                payload.update(config)
            response = requests.post(
                f"{KONG_ADMIN_URL}/services/{nombre_servicio}/plugins", data=payload
            )
            return response

        response_jwt = habilitar_plugin("jwt")
        if response_jwt.status_code not in [201, 200]:
            return jsonify(
                {
                    "error": "No se pudo habilitar el plugin JWT",
                    "detalles": response_jwt.json(),
                }
            ), 500

        response_mirror = habilitar_plugin(
            "mirror-req-traffic",
            {
                "config.mirror_url": "https://fastapi-production-8132.up.railway.app/bitacora",
                "config.connect_timeout": "6000",
                "config.ssl_verify": "true",
            },
        )
        if response_mirror.status_code not in [201, 200]:
            return jsonify(
                {
                    "error": "No se pudo habilitar el plugin mirror-req-traffic",
                    "detalles": response_mirror.json(),
                }
            ), 500

        response_transform = habilitar_plugin(
            "request-transformer",
            {
                "config.add.headers": f"Authorization:Bearer {token}",
                "config.remove.headers": "authorization",
            },
        )
        if response_transform.status_code not in [201, 200]:
            return jsonify(
                {
                    "error": "No se pudo habilitar el plugin request-transformer",
                    "detalles": response_transform.json(),
                }
            ), 500

        return jsonify(
            {
                "mensaje": "Servicio creado exitosamente en Kong",
                "nombre_servicio": nombre_servicio,
                "url_backend": url,
                "ruta_kong": f"{ruta}",
                "token": token,
            }
        ), 200

    except Exception as e:  # Capturar cualquier excepción
        return jsonify(
            {"error": str(e)}
        ), 500  # Retornar un error 500 con el mensaje de error capturado


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

        # Construir la consulta SQL para obtener los datos
        query = f"SELECT * FROM {CLICKHOUSE_TABLE} WHERE 1=1"
        if idTransaccion:
            query += f" AND idTransaccion = '{idTransaccion}'"
        if usuarioConsumidor:
            query += f" AND usuarioConsumidor = '{usuarioConsumidor}'"
        if estado:
            query += f" AND estado = '{estado}'"

        # Ejecutar la consulta para obtener los datos
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

        # Construir la consulta SQL para contar el total de registros
        count_query = f"SELECT count() FROM {CLICKHOUSE_TABLE} WHERE 1=1"
        if idTransaccion:
            count_query += f" AND idTransaccion = '{idTransaccion}'"
        if usuarioConsumidor:
            count_query += f" AND usuarioConsumidor = '{usuarioConsumidor}'"
        if estado:
            count_query += f" AND estado = '{estado}'"

        # Ejecutar la consulta para contar los registros
        count_result = clickhouse_client.query(count_query)
        total_registros = count_result.result_rows[0][
            0
        ]  # Obtener el total de registros

        # Devolver la respuesta con los datos y el total de registros
        return jsonify(
            {
                "total_registros": total_registros,
                "datos": datos,
            }
        ), 200

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
