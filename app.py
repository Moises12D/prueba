from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
import mysql.connector
from mysql.connector import pooling # Importamos la herramienta de pooling
import certifi
import os

app = Flask(__name__, template_folder="Templates", static_folder="Static")
CORS(app)

dbconfig = {
    "host": os.environ.get("DB_HOST"),
    "user": os.environ.get("DB_USER"),
    "password": os.environ.get("DB_PASSWORD"),
    "database": os.environ.get("DB_NAME", "inventario_db"),
    "port": int(os.environ.get("DB_PORT", 4000)),
    "ssl_ca": certifi.where(),
    "ssl_verify_cert": True,
    "ssl_verify_identity": True
}

conexion_pool = pooling.MySQLConnectionPool(pool_name="mypool", pool_size=5, **dbconfig)


def conectar_db():
    return conexion_pool.get_connection()

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
@app.route('/api/productos/<int:id>/venta', methods=['PUT'])
def vender_producto(id):
    data = request.json
    cantidad_vendida = int(data.get('cantidad', 1))
    usuario_id = 1 # Usuario maestro de prueba por ahora
    
    conn = conectar_db()
    cursor = conn.cursor(dictionary=True)
    
    try:
        # Verificamos si hay suficiente stock antes de restar
        cursor.execute("SELECT stock FROM productos WHERE id = %s", (id,))
        producto = cursor.fetchone()
        
        if not producto or producto['stock'] < cantidad_vendida:
            return jsonify({"error": "Stock insuficiente para realizar esta venta"}), 400
            
        # 1. Restamos el stock en inventario
        cursor.execute("UPDATE productos SET stock = stock - %s WHERE id = %s", (cantidad_vendida, id))
        
        # 2. Guardamos el registro de la venta para tu historial
        cursor.execute("""
            INSERT INTO movimientos (producto_id, usuario_id, tipo, cantidad)
            VALUES (%s, %s, 'venta', %s)
        """, (id, usuario_id, cantidad_vendida))
        
        conn.commit()
        return jsonify({"mensaje": "Venta registrada y guardada en el historial"}), 200
    finally:
        cursor.close()
        conn.close()

@app.route('/api/productos/<int:id>/ingreso', methods=['PUT'])
def ingresar_producto(id):
    data = request.json
    cantidad_ingresada = int(data.get('cantidad', 1))
    usuario_id = 1 # Usuario maestro de prueba por ahora
    
    conn = conectar_db()
    cursor = conn.cursor()
    
    try:
        # 1. Sumamos el stock en inventario
        cursor.execute("UPDATE productos SET stock = stock + %s WHERE id = %s", (cantidad_ingresada, id))
        
        # 2. Guardamos el registro del ingreso para tu historial
        cursor.execute("""
            INSERT INTO movimientos (producto_id, usuario_id, tipo, cantidad)
            VALUES (%s, %s, 'ingreso', %s)
        """, (id, usuario_id, cantidad_ingresada))
        
        conn.commit()
        return jsonify({"mensaje": "Ingreso registrado y guardado en el historial"}), 200
    finally:
        cursor.close()
        conn.close()

if __name__ == '__main__':
    app.run(debug=True, port=5000)