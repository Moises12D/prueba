from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
import mysql.connector
from mysql.connector import pooling
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

# ==========================================
# RUTAS DE AUTENTICACIÓN Y USUARIOS (NUEVAS)
# ==========================================

# API: Inicio de sesión
@app.route('/api/login', methods=['POST'])
def login():
    data = request.json
    usuario = data.get('usuario')
    clave = data.get('clave')
    
    conn = conectar_db()
    cursor = conn.cursor(dictionary=True)
    
    # Buscamos si las credenciales coinciden exactamente
    cursor.execute("SELECT id, nombre, rol, comision FROM usuarios WHERE nombre = %s AND clave = %s", (usuario, clave))
    user_data = cursor.fetchone()
    
    cursor.close()
    conn.close()
    
    if user_data:
        return jsonify(user_data), 200
    else:
        return jsonify({"error": "Usuario o contraseña incorrectos"}), 401

# API: Obtener todos los usuarios
@app.route('/api/usuarios', methods=['GET'])
def obtener_usuarios():
    conn = conectar_db()
    cursor = conn.cursor(dictionary=True)
    # Traemos los usuarios ocultando la contraseña por seguridad básica
    cursor.execute("SELECT id, nombre, rol, comision FROM usuarios ORDER BY id ASC")
    usuarios = cursor.fetchall()
    cursor.close()
    conn.close()
    return jsonify(usuarios)

# API: Crear nuevo empleado
@app.route('/api/usuarios', methods=['POST'])
def crear_usuario():
    data = request.json
    nombre = data['nombre']
    clave = data['clave']
    comision = float(data.get('comision', 0))
    
    conn = conectar_db()
    cursor = conn.cursor()
    
    try:
        # Siempre se crean como 'empleado'
        cursor.execute("""
            INSERT INTO usuarios (nombre, clave, rol, comision)
            VALUES (%s, %s, 'empleado', %s)
        """, (nombre, clave, comision))
        conn.commit()
        return jsonify({"mensaje": "Usuario creado exitosamente"}), 201
    except mysql.connector.IntegrityError:
        # Se activa si el nombre de usuario ya existe en la BD
        return jsonify({"error": "El nombre de usuario ya está en uso"}), 400
    finally:
        cursor.close()
        conn.close()

# API: Eliminar empleado
@app.route('/api/usuarios/<int:id>', methods=['DELETE'])
def eliminar_usuario(id):
    conn = conectar_db()
    cursor = conn.cursor()
    
    try:
        # Medida de seguridad: impedimos borrar al rol maestro desde la API
        cursor.execute("DELETE FROM usuarios WHERE id = %s AND rol != 'maestro'", (id,))
        conn.commit()
        
        if cursor.rowcount == 0:
            return jsonify({"error": "No se pudo eliminar (usuario no encontrado o protegido)"}), 403
            
        return jsonify({"mensaje": "Empleado eliminado correctamente"}), 200
    finally:
        cursor.close()
        conn.close()


# ==========================================
# RUTAS DE INVENTARIO (LAS QUE YA TENÍAMOS)
# ==========================================

# Ruta para mostrar tu página HTML principal
@app.route('/')
def inicio():
    return render_template('Index.html')

# API: Obtener productos activos
@app.route('/api/productos', methods=['GET'])
def obtener_productos():
    conn = conectar_db()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM productos WHERE activo = TRUE ORDER BY fecha_ingreso DESC")
    productos = cursor.fetchall()
    cursor.close()
    conn.close()
    return jsonify(productos)

# API: Agregar producto
@app.route('/api/productos', methods=['POST'])
def agregar_producto():
    data = request.json
    usuario_id = data.get('usuario_id', 1) 
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
    cursor.close()
    conn.close()
    return jsonify({"mensaje": "Producto agregado"}), 201

# API: Vender producto
@app.route('/api/productos/<int:id>/venta', methods=['PUT'])
def vender_producto(id):
    data = request.json
    cantidad_vendida = int(data.get('cantidad', 1))
    usuario_id = data.get('usuario_id', 1)
    
    conn = conectar_db()
    cursor = conn.cursor(dictionary=True)
    
    try:
        cursor.execute("SELECT stock FROM productos WHERE id = %s", (id,))
        producto = cursor.fetchone()
        
        if not producto or producto['stock'] < cantidad_vendida:
            return jsonify({"error": "Stock insuficiente para realizar esta venta"}), 400
            
        cursor.execute("UPDATE productos SET stock = stock - %s WHERE id = %s", (cantidad_vendida, id))
        
        cursor.execute("""
            INSERT INTO movimientos (producto_id, usuario_id, tipo, cantidad)
            VALUES (%s, %s, 'venta', %s)
        """, (id, usuario_id, cantidad_vendida))
        
        conn.commit()
        return jsonify({"mensaje": "Venta registrada"}), 200
    finally:
        cursor.close()
        conn.close()

# API: Ingreso de stock
@app.route('/api/productos/<int:id>/ingreso', methods=['PUT'])
def ingresar_producto(id):
    data = request.json
    cantidad_ingresada = int(data.get('cantidad', 1))
    usuario_id = data.get('usuario_id', 1)
    
    conn = conectar_db()
    cursor = conn.cursor()
    
    try:
        cursor.execute("UPDATE productos SET stock = stock + %s WHERE id = %s", (cantidad_ingresada, id))
        
        cursor.execute("""
            INSERT INTO movimientos (producto_id, usuario_id, tipo, cantidad)
            VALUES (%s, %s, 'ingreso', %s)
        """, (id, usuario_id, cantidad_ingresada))
        
        conn.commit()
        return jsonify({"mensaje": "Ingreso registrado"}), 200
    finally:
        cursor.close()
        conn.close()

# API: Eliminar producto (Borrado Lógico)
@app.route('/api/productos/<int:id>', methods=['DELETE'])
def eliminar_producto(id):
    conn = conectar_db()
    cursor = conn.cursor()
    try:
        cursor.execute("UPDATE productos SET activo = FALSE WHERE id = %s", (id,))
        conn.commit()
        return jsonify({"mensaje": "Producto archivado correctamente"}), 200
    finally:
        cursor.close()
        conn.close()

# API: Obtener historial de movimientos
@app.route('/api/historial', methods=['GET'])
def obtener_historial():
    conn = conectar_db()
    cursor = conn.cursor(dictionary=True)
    
    # Hacemos un JOIN para traer el nombre del producto y del usuario en lugar de solo sus números de ID
    query = """
        SELECT m.id, m.fecha, m.tipo, m.cantidad, 
               p.nombre AS producto, u.nombre AS usuario
        FROM movimientos m
        JOIN productos p ON m.producto_id = p.id
        JOIN usuarios u ON m.usuario_id = u.id
        ORDER BY m.fecha DESC
    """
    try:
        cursor.execute(query)
        movimientos = cursor.fetchall()
        return jsonify(movimientos), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        cursor.close()
        conn.close()
        
if __name__ == '__main__':
    app.run(debug=True, port=5000)