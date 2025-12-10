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
def _init_graph(usuario_nombre="Usuario123"):
    """Crea un grafo RDF base con el nodo del usuario."""
    g = Graph()
    g.bind("ex", EX)
    g.bind("foaf", FOAF)
    g.bind("rdfs", RDFS)

    usuario_uri = URIRef(EX[f"Usuario#{quote(usuario_nombre)}"])
    g.add((usuario_uri, RDF.type, FOAF.Person))
    g.add((usuario_uri, FOAF.nick, Literal(usuario_nombre)))
    return g, usuario_uri


def _add_destino_and_tours_to_graph(g, usuario_uri, destino):
    """Añade al grafo un destino y sus tours asociados."""
    try:
        slug_seguro = quote(destino["slug"])
    except KeyError:
        print("⚠️ Registro de destino sin slug, se omite en RDF")
        return

    destino_uri = URIRef(EX[f"Destino#{slug_seguro}"])

    g.add((destino_uri, RDF.type, EX.Destino))
    if "nombre" in destino:
        g.add((destino_uri, RDFS.label, Literal(destino["nombre"])))
    if "ubicacion" in destino:
        g.add((destino_uri, EX.ubicacion, Literal(destino["ubicacion"])))
    if "tipo" in destino:
        g.add((destino_uri, EX.tipo, Literal(destino["tipo"])))
    if "precio" in destino:
        g.add((destino_uri, EX.precio, Literal(destino["precio"])))
    if "duracion" in destino:
        g.add((destino_uri, EX.duracion, Literal(destino["duracion"])))
    if "descripcion" in destino:
        g.add((destino_uri, EX.descripcion, Literal(destino["descripcion"])))

    g.add((usuario_uri, EX.mostro_interes_en, destino_uri))

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


def build_graph_from_db(usuario_nombre="Usuario123"):
    """Genera un grafo RDF dinámico con los últimos destinos creados en MySQL (tabla Destino)."""
    g, usuario_uri = _init_graph(usuario_nombre=usuario_nombre)

    conn = get_mysql_connection()
    if not conn:
        print("⚠️ No se pudo conectar a MySQL, usando valores por defecto.")
        return g

    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM Destino ORDER BY creadoEn DESC LIMIT 10;")
    destinos = cursor.fetchall()

    for destino in destinos:
        _add_destino_and_tours_to_graph(g, usuario_uri, destino)

    cursor.close()
    conn.close()
    return g


def build_graph_for_destino_slug(slug, usuario_nombre="Usuario123"):
    """Genera un grafo RDF solo para un destino concreto identificado por su slug."""
    g, usuario_uri = _init_graph(usuario_nombre=usuario_nombre)

    conn = get_mysql_connection()
    if not conn:
        print("⚠️ No se pudo conectar a MySQL para destino específico, devolviendo grafo vacío.")
        return g

    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM Destino WHERE slug = %s LIMIT 1;", (slug,))
    destino = cursor.fetchone()

    if destino:
        _add_destino_and_tours_to_graph(g, usuario_uri, destino)
    else:
        print(f"⚠️ No se encontró destino con slug={slug} para RDF")

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


@rdf_bp.route("/rdf/destino/<slug>", methods=["GET"])
def get_rdf_for_destino(slug):
    """Devuelve el grafo RDF de un único destino (y sus tours) identificado por slug."""
    usuario = unquote(request.args.get("usuario", "Usuario123"))
    g = build_graph_for_destino_slug(slug, usuario_nombre=usuario)
    ttl_data = g.serialize(format="turtle")

    if isinstance(ttl_data, bytes):
        ttl_data = ttl_data.decode("utf-8")

    return Response(ttl_data, mimetype="text/plain")
