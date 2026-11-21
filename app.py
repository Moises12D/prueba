import os 
from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
import mysql.connector

app = Flask(__name__, template_folder="Templates", static_folder="Static")
CORS(app)

def conectar_db():
    return mysql.connector.connect(
        host=os.environ.get("DB_HOST", "localhost"),
        user=os.environ.get("DB_USER", "root"),
        password=os.environ.get("DB_PASSWORD", ""),
        database=os.environ.get("DB_NAME", "inventario_db"),
        port=os.environ.get("DB_PORT", 3306)
    )

# Ruta para mostrar tu página HTML
@app.route('/')
def inicio():
    return render_template('Index.html')

# API: Obtener productos
@app.route('/api/productos', methods=['GET'])
def obtener_productos():
    conn = conectar_db()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM productos ORDER BY fecha_ingreso DESC")
    productos = cursor.fetchall()
    conn.close()
    return jsonify(productos)

# API: Agregar producto
@app.route('/api/productos', methods=['POST'])
def agregar_producto():
    data = request.json
    usuario_id = 1 # Usamos el usuario de prueba por ahora
    precio_compra = float(data['precio_compra'])
    porcentaje = float(data['porcentaje_ganancia'])
    precio_venta = precio_compra + (precio_compra * (porcentaje / 100))
    stock = int(data['stock'])

    conn = conectar_db()
    cursor = conn.cursor()
    
    cursor.execute("""
        INSERT INTO productos (codigo, nombre, precio_compra, porcentaje_ganancia_esperada, precio_venta, stock)
        VALUES (%s, %s, %s, %s, %s, %s)
    """, (data['codigo'], data['nombre'], precio_compra, porcentaje, precio_venta, stock))
    
    producto_id = cursor.lastrowid

    cursor.execute("""
        INSERT INTO movimientos (producto_id, usuario_id, tipo, cantidad)
        VALUES (%s, %s, 'ingreso', %s)
    """, (producto_id, usuario_id, stock))

    conn.commit()
    conn.close()
    return jsonify({"mensaje": "Producto agregado"}), 201

# API: Eliminar producto
@app.route('/api/productos/<int:id>', methods=['DELETE'])
def eliminar_producto(id):
    conn = conectar_db()
    cursor = conn.cursor()
    # Eliminamos el historial de ese producto primero para evitar errores
    cursor.execute("DELETE FROM movimientos WHERE producto_id = %s", (id,))
    cursor.execute("DELETE FROM productos WHERE id = %s", (id,))
    conn.commit()
    conn.close()
    return jsonify({"mensaje": "Producto eliminado"})

if __name__ == '__main__':
    app.run(debug=True, port=5000)