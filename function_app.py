"""
PayFlow — Azure Functions App (Python v2 Programming Model)
Punto de entrada principal. Registra las 4 funciones de la arquitectura:

  1. ingest_transaction   → HTTP POST  (POS / Canales Digitales → Event Hubs)
  2. process_transaction  → Event Hub trigger (validación + antifraude → Cosmos DB + Service Bus)
  3. monitor_metrics      → HTTP GET   (dashboard Azure Monitor)
  4. health_check         → HTTP GET   (disponibilidad para equipos OPS / Risk)

Variables de entorno requeridas en func-payflow-prd-brs-006:
  - EventHubConnectionString
  - EventHubName
  - ServiceBusConnectionString
  - ServiceBusQueueName
  - CosmosDBConnectionString
  - CosmosDBName
  - CosmosDBContainer
"""

import azure.functions as func
import json
import logging
import os
from datetime import datetime, timezone

from azure.eventhub import EventHubProducerClient, EventData
from azure.servicebus import ServiceBusClient, ServiceBusMessage
from azure.cosmos import CosmosClient

# Lógica de negocio reutilizada de los scripts originales
from src.function_validate import validar_transaccion
from src.service_bus_router import enrutar_alto_valor
from src.cosmos_writer      import guardar_transaccion

app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)
logger = logging.getLogger("payflow")


# ══════════════════════════════════════════════════════════════════════════════
# FUNCIÓN 1 — ingest_transaction
# Trigger : HTTP POST /api/ingest
# Rol     : Simula Terminales POS / Canales Digitales publicando en Event Hubs
# ══════════════════════════════════════════════════════════════════════════════
@app.route(route="ingest", methods=["POST"])
def ingest_transaction(req: func.HttpRequest) -> func.HttpResponse:
    logger.info("PayFlow › ingest_transaction activada")

    try:
        body = req.get_json()
    except ValueError:
        return func.HttpResponse(
            json.dumps({"error": "Body inválido — se esperaba JSON"}),
            status_code=400, mimetype="application/json"
        )

    for campo in ["id", "monto", "comercio"]:
        if campo not in body:
            return func.HttpResponse(
                json.dumps({"error": f"Campo requerido faltante: '{campo}'"}),
                status_code=400, mimetype="application/json"
            )

    conn_str = os.environ["EventHubConnectionString"]
    hub_name = os.environ.get("EventHubName", "evh-payflow-transacciones")

    try:
        producer = EventHubProducerClient.from_connection_string(
            conn_str=conn_str, eventhub_name=hub_name
        )
        with producer:
            batch = producer.create_batch()
            batch.add(EventData(json.dumps(body)))
            producer.send_batch(batch)
    except Exception as e:
        logger.error(f"Error publicando en Event Hubs: {e}")
        return func.HttpResponse(
            json.dumps({"error": "No se pudo publicar el evento", "detalle": str(e)}),
            status_code=500, mimetype="application/json"
        )

    logger.info(f"Evento publicado › id={body.get('id')} | monto={body.get('monto')}")
    return func.HttpResponse(
        json.dumps({
            "status":    "evento_publicado",
            "id":        body.get("id"),
            "comercio":  body.get("comercio"),
            "monto":     body.get("monto"),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }),
        status_code=202, mimetype="application/json"
    )


# ══════════════════════════════════════════════════════════════════════════════
# FUNCIÓN 2 — process_transaction
# Trigger : Azure Event Hubs
# Rol     : Consume eventos, valida, aplica antifraude,
#           persiste en Cosmos DB y encola alto valor en Service Bus
# ══════════════════════════════════════════════════════════════════════════════
@app.event_hub_message_trigger(
    arg_name="event",
    event_hub_name="%EventHubName%",
    connection="EventHubConnectionString"
)
def process_transaction(event: func.EventHubEvent) -> None:
    logger.info("PayFlow › process_transaction activada")

    try:
        raw        = event.get_body().decode("utf-8")
        transaccion = json.loads(raw)
    except Exception as e:
        logger.error(f"No se pudo deserializar el evento: {e}")
        return

    logger.info(f"Evento recibido › id={transaccion.get('id')} | monto={transaccion.get('monto')}")

    # Validar + antifraude
    resultado = validar_transaccion(transaccion)
    logger.info(f"Validación › estado={resultado.get('estado')} | motivo={resultado.get('motivo','OK')}")

    # Persistir en Cosmos DB
    _persistir_cosmos(resultado)

    # Enrutar alto valor a Service Bus si aplica
    if resultado.get("estado") == "en_revision":
        _encolar_service_bus(resultado)


def _persistir_cosmos(resultado: dict) -> None:
    try:
        conn_str  = os.environ["CosmosDBConnectionString"]
        db_name   = os.environ.get("CosmosDBName",      "payflow-db")
        container = os.environ.get("CosmosDBContainer", "transacciones")

        client   = CosmosClient.from_connection_string(conn_str)
        database = client.get_database_client(db_name)
        col      = database.get_container_client(container)

        doc      = guardar_transaccion(resultado)
        doc["id"] = str(doc.get("id", datetime.now(timezone.utc).timestamp()))
        col.upsert_item(doc)

        logger.info(f"Cosmos DB › persistido id={doc['id']} | estado={doc.get('estado')}")
    except Exception as e:
        logger.error(f"Error Cosmos DB: {e}")


def _encolar_service_bus(resultado: dict) -> None:
    try:
        conn_str   = os.environ["ServiceBusConnectionString"]
        queue_name = os.environ.get("ServiceBusQueueName", "sbq-payflow-alto-valor")

        mensaje = enrutar_alto_valor(resultado)
        if not mensaje:
            return

        sb_client = ServiceBusClient.from_connection_string(conn_str)
        with sb_client:
            sender = sb_client.get_queue_sender(queue_name=queue_name)
            with sender:
                sender.send_messages(ServiceBusMessage(json.dumps(mensaje)))

        logger.info(f"Service Bus › encolado id={resultado.get('id')} | monto={resultado.get('monto')}")
    except Exception as e:
        logger.error(f"Error Service Bus: {e}")


# ══════════════════════════════════════════════════════════════════════════════
# FUNCIÓN 3 — monitor_metrics
# Trigger : HTTP GET /api/monitor
# Rol     : Métricas operativas en tiempo real (Azure Monitor / App Insights)
# ══════════════════════════════════════════════════════════════════════════════
@app.route(route="monitor", methods=["GET"])
def monitor_metrics(req: func.HttpRequest) -> func.HttpResponse:
    logger.info("PayFlow › monitor_metrics activada")

    try:
        conn_str  = os.environ["CosmosDBConnectionString"]
        db_name   = os.environ.get("CosmosDBName",      "payflow-db")
        container = os.environ.get("CosmosDBContainer", "transacciones")

        client   = CosmosClient.from_connection_string(conn_str)
        database = client.get_database_client(db_name)
        col      = database.get_container_client(container)

        items = list(col.query_items(
            query="SELECT * FROM c ORDER BY c._ts DESC OFFSET 0 LIMIT 100",
            enable_cross_partition_query=True
        ))
    except Exception as e:
        logger.error(f"Error consultando Cosmos DB: {e}")
        return func.HttpResponse(
            json.dumps({"error": "No se pudo consultar Cosmos DB", "detalle": str(e)}),
            status_code=500, mimetype="application/json"
        )

    total       = len(items)
    aprobadas   = sum(1 for i in items if i.get("estado") == "aprobada")
    rechazadas  = sum(1 for i in items if i.get("estado") == "rechazada")
    en_revision = sum(1 for i in items if i.get("estado") == "en_revision")
    tasa_error  = round((rechazadas / total * 100), 2) if total > 0 else 0

    return func.HttpResponse(
        json.dumps({
            "timestamp":              datetime.now(timezone.utc).isoformat(),
            "throughput_total":       total,
            "estados": {
                "aprobadas":          aprobadas,
                "rechazadas":         rechazadas,
                "en_revision":        en_revision
            },
            "tasa_error_pct":         tasa_error,
            "alerta_error":           tasa_error > 20,
            "alto_valor_service_bus": en_revision,
            "sistema":                "OK" if tasa_error <= 20 else "ALERTA"
        }, indent=2),
        status_code=200, mimetype="application/json"
    )


# ══════════════════════════════════════════════════════════════════════════════
# FUNCIÓN 4 — health_check
# Trigger : HTTP GET /api/health
# Rol     : Verificación de disponibilidad para equipos OPS y Risk
# ══════════════════════════════════════════════════════════════════════════════
@app.route(route="health", methods=["GET"])
def health_check(req: func.HttpRequest) -> func.HttpResponse:
    logger.info("PayFlow › health_check activada")
    return func.HttpResponse(
        json.dumps({
            "status":    "healthy",
            "servicio":  "func-payflow-prd-brs-006",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "funciones": [
                "POST /api/ingest   → ingest_transaction  (Event Hubs)",
                "     Event Hub     → process_transaction (validación + antifraude)",
                "GET  /api/monitor  → monitor_metrics     (Azure Monitor)",
                "GET  /api/health   → health_check        (OPS / Risk)"
            ]
        }, indent=2),
        status_code=200, mimetype="application/json"
    )