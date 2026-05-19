"""
PayFlow — Observabilidad y Métricas
Equivalente a: Azure Monitor + Application Insights

Consolida métricas del flujo de transacciones:
  - Throughput (transacciones procesadas)
  - Distribución de estados (aprobada / rechazada / en_revision)
  - Tasa de errores
  - Transacciones de alto valor en Service Bus
  - Simulación de alertas automáticas (latencia < 30s)
"""

import pandas as pd
from datetime import datetime


def generar_reporte(procesados, service_bus_queue=None):
    """
    Genera el reporte de métricas del sistema.
    Equivale al dashboard de Azure Monitor en tiempo real.
    """
    print(f"\n{'='*55}")
    print(f"  PayFlow — Azure Monitor + Application Insights")
    print(f"{'='*55}")
    print(f"  Timestamp: {datetime.utcnow().isoformat()}Z\n")

    if not procesados:
        print("  ⚠️  Sin transacciones procesadas.")
        return

    df = pd.DataFrame(procesados)

    # --- Métricas de throughput ---
    total = len(df)
    print(f"  📊 THROUGHPUT")
    print(f"     Total transacciones procesadas : {total}")

    # --- Distribución de estados ---
    print(f"\n  📈 DISTRIBUCIÓN DE ESTADOS")
    conteo = df["estado"].value_counts()
    iconos = {"aprobada": "✅", "rechazada": "❌", "en_revision": "🚨"}
    for estado, count in conteo.items():
        icono = iconos.get(estado, "❓")
        pct = count / total * 100
        barra = "█" * int(pct / 5)
        print(f"     {icono} {estado:<15} : {count:3d} ({pct:5.1f}%) {barra}")

    # --- Tasa de errores ---
    rechazadas = conteo.get("rechazada", 0)
    tasa_error = rechazadas / total * 100
    alerta_error = "🔴 ALERTA" if tasa_error > 20 else "🟢 OK"
    print(f"\n  🚨 TASA DE ERRORES")
    print(f"     Tasa de error: {tasa_error:.1f}% — {alerta_error}")

    # --- Transacciones alto valor ---
    alto_valor = conteo.get("en_revision", 0)
    print(f"\n  💎 TRANSACCIONES ALTO VALOR (> $5M COP)")
    print(f"     Enrutadas a Service Bus: {alto_valor}")
    if service_bus_queue:
        print(f"     Mensajes en cola       : {len(service_bus_queue)}")

    # --- Alerta de disponibilidad (simulada < 30s) ---
    print(f"\n  ⚡ ALERTAS AUTOMÁTICAS (latencia detección < 30s)")
    if tasa_error > 20:
        print(f"     🔴 ALERTA CRÍTICA: tasa de error {tasa_error:.1f}% supera umbral del 20%")
        print(f"        → Notificación enviada al Equipo de Operaciones")
    else:
        print(f"     🟢 Sistema operando dentro de parámetros normales")

    print(f"\n  {'='*51}")
    print(f"  DataFrame completo del flujo:\n")
    print(df.to_string(index=False))
    print()

    return df


if __name__ == "__main__":
    from event_generator import publicar_eventos
    from function_validate import procesar_batch
    from service_bus_router import procesar_cola, service_bus_queue
    from cosmos_writer import guardar_batch

    event_hub = publicar_eventos(15)
    procesados = procesar_batch(event_hub)
    cola = procesar_cola(procesados)
    guardar_batch(procesados)
    generar_reporte(procesados, service_bus_queue)
