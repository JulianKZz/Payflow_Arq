"""
PayFlow — Persistencia de Transacciones
Equivalente a: Azure Cosmos DB (registrarResultado)

Almacena el estado final de cada transacción procesada con escrituras
de alta velocidad. Modelo de datos flexible en JSON para soportar
distintos tipos: pagos, reembolsos, transferencias.
"""

import json
from datetime import datetime

# Simula la colección de Cosmos DB
cosmos_db = []


def guardar_transaccion(transaccion):
    """
    Persiste una transacción en Cosmos DB.
    Agrega metadata de auditoría: timestamp y partition key.
    """
    documento = {
        **transaccion,
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "partition_key": f"comercio_{transaccion.get('comercio', 'desconocido').replace(' ', '_').lower()}"
    }
    cosmos_db.append(documento)
    return documento


def guardar_batch(procesados):
    """Persiste todos los documentos procesados en Cosmos DB."""
    print(f"\n{'='*55}")
    print(f"  PayFlow — Cosmos DB (Persistencia de Transacciones)")
    print(f"{'='*55}")
    print(f"  Guardando {len(procesados)} documentos...\n")

    for i, tx in enumerate(procesados):
        doc = guardar_transaccion(tx)
        icono = {"aprobada": "✅", "rechazada": "❌", "en_revision": "🚨"}.get(doc.get("estado"), "❓")
        print(f"  [{i+1:02d}] {icono} 💾 id={doc.get('id')} | estado={doc.get('estado')} | ts={doc.get('timestamp')}")

    print(f"\n  ✅ {len(cosmos_db)} documentos persistidos en Cosmos DB\n")
    return cosmos_db


if __name__ == "__main__":
    from event_generator import publicar_eventos
    from function_validate import procesar_batch
    event_hub = publicar_eventos(10)
    procesados = procesar_batch(event_hub)
    documentos = guardar_batch(procesados)
    print("\nMuestra de documentos en Cosmos DB:")
    for doc in documentos[:3]:
        print(" ", json.dumps(doc, indent=2, ensure_ascii=False))
