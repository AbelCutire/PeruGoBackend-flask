# backend/generate_rdf.py
from flask import Blueprint, request, Response
from rdflib import Graph, Namespace, URIRef, Literal
from rdflib.namespace import RDF, RDFS, FOAF
from urllib.parse import unquote, quote
import mysql.connector
import json

# -------------------------------
# Configuración y namespaces RDF
# -------------------------------
rdf_bp = Blueprint("rdf_bp", __name__)
EX = Namespace("https://www.perugo/")


# -------------------------------
# Conexión directa a MySQL
# -------------------------------
def get_mysql_connection():
    """Crea una conexión directa a la base de datos MySQL de Railway."""
    try:
        conn = mysql.connector.connect(
            host="caboose.proxy.rlwy.net",
            port=16304,
            user="root",
            password="hshczChHDeaxsiMBnLOWZnaNHwQOrMnZ",
            database="railway"
        )
        return conn
    except mysql.connector.Error as err:
        print(f"❌ Error conectando a MySQL: {err}")
        return None


# -------------------------------
# Construcción del grafo RDF
# -------------------------------
def build_graph_from_db(usuario_nombre="Usuario123"):
    """Genera un grafo RDF dinámico leyendo datos reales desde MySQL (tabla Destino)."""
    g = Graph()
    g.bind("ex", EX)
    g.bind("foaf", FOAF)
    g.bind("rdfs", RDFS)

    # Nodo del usuario
    usuario_uri = URIRef(EX[f"Usuario#{quote(usuario_nombre)}"])
    g.add((usuario_uri, RDF.type, FOAF.Person))
    g.add((usuario_uri, FOAF.nick, Literal(usuario_nombre)))

    conn = get_mysql_connection()
    if not conn:
        print("⚠️ No se pudo conectar a MySQL, usando valores por defecto.")
        return g

    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM Destino ORDER BY creadoEn DESC LIMIT 10;")
    destinos = cursor.fetchall()

    for destino in destinos:
        # Crear URI del destino (segura)
        slug_seguro = quote(destino['slug'])
        destino_uri = URIRef(EX[f"Destino#{slug_seguro}"])

        g.add((destino_uri, RDF.type, EX.Destino))
        g.add((destino_uri, RDFS.label, Literal(destino['nombre'])))
        g.add((destino_uri, EX.ubicacion, Literal(destino['ubicacion'])))
        g.add((destino_uri, EX.tipo, Literal(destino['tipo'])))
        g.add((destino_uri, EX.precio, Literal(destino['precio'])))
        g.add((destino_uri, EX.duracion, Literal(destino['duracion'])))
        g.add((destino_uri, EX.descripcion, Literal(destino['descripcion'])))
        g.add((usuario_uri, EX.mostro_interes_en, destino_uri))

        # Tours (si existen en JSON)
        if destino.get("tours"):
            try:
                tours = json.loads(destino["tours"]) if isinstance(destino["tours"], str) else destino["tours"]
                for t in tours:
                    tour_id = t.get("id") or t.get("nombre", "tour")
                    tour_uri_safe = quote(str(tour_id).replace(" ", "_"))
                    tour_ref = URIRef(EX[f"Tour#{tour_uri_safe}"])
                    
                    g.add((tour_ref, RDF.type, EX.Tour))
                    g.add((tour_ref, RDFS.label, Literal(t.get("nombre", "Tour sin nombre"))))
                    
                    if "precio" in t:
                        g.add((tour_ref, EX.priceUSD, Literal(t["precio"])))
                    if "operador" in t:
                        g.add((tour_ref, EX.operator, Literal(t["operador"])))
                    
                    g.add((destino_uri, EX.ofrece, tour_ref))
            except Exception as e:
                print("⚠️ Error al procesar JSON de tours:", e)

    cursor.close()
    conn.close()
    return g


# -------------------------------
# Endpoint Flask /rdf
# -------------------------------
@rdf_bp.route("/rdf", methods=["GET"])
def get_rdf():
    """Devuelve el grafo RDF generado desde la base de datos MySQL (Railway)."""
    usuario = unquote(request.args.get("usuario", "Usuario123"))
    g = build_graph_from_db(usuario_nombre=usuario)
    ttl_data = g.serialize(format="turtle")

    if isinstance(ttl_data, bytes):
        ttl_data = ttl_data.decode("utf-8")

    return Response(ttl_data, mimetype="text/plain")
