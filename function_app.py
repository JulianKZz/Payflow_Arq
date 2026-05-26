"""
PayFlow — Azure Functions App (Python v2 Programming Model)
Arquitectura Event-Driven sobre Microsoft Azure

Funciones:
  1. health_check        → GET  /api/health
  2. ingest_transaction  → POST /api/ingest
  3. process_transaction → GET  /api/process (simula Event Hub trigger)
  4. monitor_metrics     → GET  /api/monitor
"""

import azure.functions as func
import json
import logging
from datetime import datetime, timezone

# Lógica de negocio de los módulos src/
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from src.function_validate import validar_transaccion
from src.service_bus_router  import enrutar_alto_valor, service_bus_queue
from src.cosmos_writer       import guardar_transaccion, cosmos_db
from src.event_generator     import generar_transaccion

app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)
logger = logging.getLogger("payflow")

# Buffer en memoria que simula Event Hubs
event_hub_buffer = []


# ══════════════════════════════════════════════════════════════════════════════
# FUNCIÓN 1 — health_check
# GET /api/health
# Verifica disponibilidad del sistema (Equipos OPS / Risk)
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
                "GET  /api/health   → health_check",
                "POST /api/ingest   → ingest_transaction",
                "GET  /api/process  → process_transaction",
                "GET  /api/monitor  → monitor_metrics"
            ]
        }, indent=2),
        status_code=200,
        mimetype="application/json"
    )


# ══════════════════════════════════════════════════════════════════════════════
# FUNCIÓN 2 — ingest_transaction
# POST /api/ingest
# Simula Terminales POS / Canales Digitales publicando en Azure Event Hubs
# ══════════════════════════════════════════════════════════════════════════════
@app.route(route="ingest", methods=["POST"])
def ingest_transaction(req: func.HttpRequest) -> func.HttpResponse:
    logger.info("PayFlow › ingest_transaction activada")

    # Aceptar body JSON o generar transacción aleatoria si no hay body
    try:
        body = req.get_json()
    except ValueError:
        body = generar_transaccion()
        if not isinstance(body, dict):
            body = generar_transaccion()

    # Validar campos mínimos
    if not isinstance(body, dict):
        body = generar_transaccion()

    for campo in ["id", "monto", "comercio"]:
        if campo not in body:
            return func.HttpResponse(
                json.dumps({"error": f"Campo requerido faltante: '{campo}'"}),
                status_code=400,
                mimetype="application/json"
            )

    # Publicar en Event Hub (buffer en memoria)
    event_hub_buffer.append(body)

    logger.info(f"Evento publicado › id={body.get('id')} | monto={body.get('monto')} | comercio={body.get('comercio')}")

    return func.HttpResponse(
        json.dumps({
            "status":              "evento_publicado",
            "id":                  body.get("id"),
            "comercio":            body.get("comercio"),
            "monto":               body.get("monto"),
            "tipo":                body.get("tipo", "normal"),
            "eventos_en_buffer":   len(event_hub_buffer),
            "timestamp":           datetime.now(timezone.utc).isoformat()
        }, indent=2),
        status_code=202,
        mimetype="application/json"
    )


# ══════════════════════════════════════════════════════════════════════════════
# FUNCIÓN 3 — process_transaction
# GET /api/process
# Simula Azure Functions consumiendo eventos de Event Hubs:
# validación + antifraude + enrutamiento Service Bus + persistencia Cosmos DB
# ══════════════════════════════════════════════════════════════════════════════
@app.route(route="process", methods=["GET"])
def process_transaction(req: func.HttpRequest) -> func.HttpResponse:
    logger.info("PayFlow › process_transaction activada")

    # Si no hay eventos en el buffer, generar 5 automáticamente
    if not event_hub_buffer:
        for _ in range(5):
            evento = generar_transaccion()
            if isinstance(evento, dict):
                event_hub_buffer.append(evento)

    procesados   = []
    enrutados_sb = []

    for evento in event_hub_buffer:
        # Validar + antifraude (function_validate.py)
        resultado = validar_transaccion(evento)
        doc       = guardar_transaccion(resultado)
        doc["id"] = str(doc.get("id", ""))
        procesados.append(doc)

        # Enrutar alto valor a Service Bus
        if resultado.get("estado") == "en_revision":
            msg = enrutar_alto_valor(resultado)
            if msg:
                enrutados_sb.append(msg)

        logger.info(f"Procesado › id={doc.get('id')} | estado={doc.get('estado')}")

    # Limpiar buffer tras procesar
    event_hub_buffer.clear()

    # Métricas
    total       = len(procesados)
    aprobadas   = sum(1 for p in procesados if p.get("estado") == "aprobada")
    rechazadas  = sum(1 for p in procesados if p.get("estado") == "rechazada")
    en_revision = sum(1 for p in procesados if p.get("estado") == "en_revision")

    return func.HttpResponse(
        json.dumps({
            "status":        "procesado",
            "total":         total,
            "aprobadas":     aprobadas,
            "rechazadas":    rechazadas,
            "en_revision":   en_revision,
            "service_bus":   len(enrutados_sb),
            "cosmos_db":     len(cosmos_db),
            "transacciones": procesados,
            "timestamp":     datetime.now(timezone.utc).isoformat()
        }, indent=2),
        status_code=200,
        mimetype="application/json"
    )


# ══════════════════════════════════════════════════════════════════════════════
# FUNCIÓN 4 — monitor_metrics
# GET /api/monitor
# Dashboard Azure Monitor + Application Insights
# ══════════════════════════════════════════════════════════════════════════════
@app.route(route="monitor", methods=["GET"])
def monitor_metrics(req: func.HttpRequest) -> func.HttpResponse:
    logger.info("PayFlow › monitor_metrics activada")

    total       = len(cosmos_db)
    aprobadas   = sum(1 for i in cosmos_db if i.get("estado") == "aprobada")
    rechazadas  = sum(1 for i in cosmos_db if i.get("estado") == "rechazada")
    en_revision = sum(1 for i in cosmos_db if i.get("estado") == "en_revision")
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
            "alto_valor_service_bus": len(service_bus_queue),
            "sistema":                "OK" if tasa_error <= 20 else "ALERTA",
            "eventos_pendientes":     len(event_hub_buffer)
        }, indent=2),
        status_code=200,
        mimetype="application/json"
    )        