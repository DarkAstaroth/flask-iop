from flask import Flask, render_template, request, jsonify

import json
import datetime

app = Flask(__name__)

# Ruta para recibir los logs
@app.route('/logs', methods=['POST'])
def receive_logs():
  return jsonify({"mensaje": "Hola logs"}), 201

@app.route('/')
def index():
  return render_template('index.html')

if __name__ == '__main__':
  app.run(port=5000)
