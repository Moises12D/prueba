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

# Asegura que exista la columna comision_pagada en la tabla movimientos
def inicializar_columna_pagos():
    conn = conectar_db()
    cursor = conn.cursor()
    try:
        cursor.execute("ALTER TABLE movimientos ADD COLUMN comision_pagada BOOLEAN DEFAULT FALSE")
        conn.commit()
    except mysql.connector.Error:
        # Si ya existe la columna, continuamos normalmente
        pass
    finally:
        cursor.close()
        conn.close()

inicializar_columna_pagos()

# ==========================================
# RUTAS DE AUTENTICACIÓN Y USUARIOS
# ==========================================

@app.route('/api/login', methods=['POST'])
def login():
    data = request.json
    usuario = data.get('usuario')
    clave = data.get('clave')
    
    conn = conectar_db()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT id, nombre, rol, comision FROM usuarios WHERE nombre = %s AND clave = %s", (usuario, clave))
    user_data = cursor.fetchone()
    cursor.close()
    conn.close()
    
    if user_data:
        return jsonify(user_data), 200
    else:
        return jsonify({"error": "Usuario o contraseña incorrectos"}), 401

@app.route('/api/usuarios', methods=['GET'])
def obtener_usuarios():
    conn = conectar_db()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT id, nombre, rol, comision FROM usuarios ORDER BY id ASC")
    usuarios = cursor.fetchall()
    cursor.close()
    conn.close()
    return jsonify(usuarios)

@app.route('/api/usuarios', methods=['POST'])
def crear_usuario():
    data = request.json
    nombre = data['nombre']
    clave = data['clave']
    comision = float(data.get('comision', 0))
    rol = data.get('rol', 'empleado')
    
    if rol not in ['maestro', 'empleado']:
        rol = 'empleado'
    
    conn = conectar_db()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO usuarios (nombre, clave, rol, comision)
            VALUES (%s, %s, %s, %s)
        """, (nombre, clave, rol, comision))
        conn.commit()
        return jsonify({"mensaje": "Usuario creado exitosamente"}), 201
    except mysql.connector.IntegrityError:
        return jsonify({"error": "El nombre de usuario ya está en uso"}), 400
    finally:
        cursor.close()
        conn.close()

@app.route('/api/usuarios/<int:id>', methods=['DELETE'])
def eliminar_usuario(id):
    conn = conectar_db()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM usuarios WHERE id = %s AND rol != 'maestro'", (id,))
        conn.commit()
        if cursor.rowcount == 0:
            return jsonify({"error": "No se pudo eliminar (usuario no encontrado o protegido)"}), 403
        return jsonify({"mensaje": "Empleado eliminado correctamente"}), 200
    finally:
        cursor.close()
        conn.close()

# ==========================================
# RUTAS DE INVENTARIO
# ==========================================

@app.route('/')
def inicio():
    return render_template('Index.html')

@app.route('/api/productos', methods=['GET'])
def obtener_productos():
    conn = conectar_db()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM productos WHERE activo = TRUE ORDER BY fecha_ingreso DESC")
    productos = cursor.fetchall()
    cursor.close()
    conn.close()
    return jsonify(productos)

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
            INSERT INTO movimientos (producto_id, usuario_id, tipo, cantidad, comision_pagada)
            VALUES (%s, %s, 'venta', %s, FALSE)
        """, (id, usuario_id, cantidad_vendida))
        
        conn.commit()
        return jsonify({"mensaje": "Venta registrada"}), 200
    finally:
        cursor.close()
        conn.close()

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

@app.route('/api/productos/<int:id>', methods=['PUT'])
def editar_producto(id):
    data = request.json
    conn = conectar_db()
    cursor = conn.cursor()
    try:
        query = """
            UPDATE productos 
            SET nombre = %s, precio_compra = %s, precio_venta = %s 
            WHERE id = %s
        """
        cursor.execute(query, (data['nombre'], data['precio_compra'], data['precio_venta'], id))
        conn.commit()
        return jsonify({"mensaje": "Producto actualizado"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        cursor.close()
        conn.close()

# ==========================================
# HISTORIAL Y COMISIONES
# ==========================================

@app.route('/api/historial', methods=['GET'])
def obtener_historial():
    usuario_id = request.args.get('usuario_id')
    rol = request.args.get('rol')
    
    conn = conectar_db()
    cursor = conn.cursor(dictionary=True)
    
    base_query = """
        SELECT m.id, 
               m.fecha, 
               m.tipo, m.cantidad, 
               COALESCE(p.nombre, 'Producto Eliminado') AS producto, 
               COALESCE(u.nombre, 'Usuario Eliminado') AS usuario
        FROM movimientos m
        LEFT JOIN productos p ON m.producto_id = p.id
        LEFT JOIN usuarios u ON m.usuario_id = u.id
    """
    
    try:
        if rol == 'empleado' and usuario_id:
            query = base_query + " WHERE m.usuario_id = %s ORDER BY m.fecha DESC"
            cursor.execute(query, (int(usuario_id),))
        else:
            query = base_query + " ORDER BY m.fecha DESC"
            cursor.execute(query)
            
        movimientos = cursor.fetchall()
        for mov in movimientos:
            mov['fecha'] = str(mov['fecha']) if mov['fecha'] is not None else ""
                
        return jsonify(movimientos), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        cursor.close()
        conn.close()

@app.route('/api/comisiones', methods=['GET'])
def obtener_comisiones():
    usuario_id = request.args.get('usuario_id')
    rol = request.args.get('rol')
    
    conn = conectar_db()
    cursor = conn.cursor(dictionary=True)
    
    # Calcula la comisión sobre la ganancia real (precio_venta - precio_compra)
    base_query = """
        SELECT 
            u.id, 
            u.nombre, 
            u.comision,
            COALESCE(SUM(m.cantidad * p.precio_venta), 0) AS total_ventas_dinero,
            COALESCE(SUM(m.cantidad * GREATEST(p.precio_venta - p.precio_compra, 0)), 0) AS total_ganancia,
            COALESCE(SUM(m.cantidad * GREATEST(p.precio_venta - p.precio_compra, 0) * (u.comision / 100)), 0) AS total_comision
        FROM usuarios u
        LEFT JOIN movimientos m 
            ON u.id = m.usuario_id 
            AND m.tipo = 'venta' 
            AND (m.comision_pagada = FALSE OR m.comision_pagada IS NULL)
        LEFT JOIN productos p ON m.producto_id = p.id
        WHERE u.rol = 'empleado'
    """
    
    try:
        if rol == 'empleado' and usuario_id:
            query = base_query + " AND u.id = %s GROUP BY u.id, u.nombre, u.comision"
            cursor.execute(query, (int(usuario_id),))
        else:
            query = base_query + " GROUP BY u.id, u.nombre, u.comision ORDER BY total_comision DESC"
            cursor.execute(query)
            
        comisiones = cursor.fetchall()
        return jsonify(comisiones), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        cursor.close()
        conn.close()

# NUEVA RUTA: Marcar comisiones de un vendedor como pagadas y reiniciar su contador
@app.route('/api/comisiones/<int:usuario_id>/pagar', methods=['PUT'])
def pagar_comisiones(usuario_id):
    conn = conectar_db()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            UPDATE movimientos 
            SET comision_pagada = TRUE 
            WHERE usuario_id = %s 
              AND tipo = 'venta' 
              AND (comision_pagada = FALSE OR comision_pagada IS NULL)
        """, (usuario_id,))
        conn.commit()
        return jsonify({"mensaje": "Comisiones marcadas como pagadas y contador reiniciado"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500