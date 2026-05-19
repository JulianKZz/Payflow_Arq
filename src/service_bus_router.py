"""
PayFlow — Enrutamiento de Transacciones de Alto Valor
Equivalente a: Azure Service Bus (cola de alta prioridad)

Las transacciones con monto > $5.000.000 COP se enrutan a un canal
diferenciado con garantía de entrega at-least-once, reintentos automáticos
y dead-letter queue para auditoría obligatoria (requisito SFC).
"""

# Simula la cola de Azure Service Bus
service_bus_queue = []
dead_letter_queue = []


def enrutar_alto_valor(transaccion):
    """
    Enruta al canal de alta prioridad si el estado es 'en_revision'
    (es decir, monto > $5.000.000 COP).
    Simula el comportamiento de Azure Service Bus con at-least-once delivery.
    """
    if transaccion.get("estado") == "en_revision":
        mensaje = {
            **transaccion,
            "canal": "service_bus_alto_valor",
            "prioridad": "alta",
            "auditoria_requerida": True,
            "intentos_entrega": 1
        }
        service_bus_queue.append(mensaje)
        print(f"  🚨 Service Bus ← encolado | id={transaccion.get('id')} | monto=${transaccion.get('monto'):,} COP")
        return mensaje
    return None


def procesar_cola(procesados):
    """Enruta todas las transacciones de alto valor al Service Bus."""
    print(f"\n{'='*55}")
    print(f"  PayFlow — Azure Service Bus (Transacciones > $5M COP)")
    print(f"{'='*55}")

    enrutados = 0
    for transaccion in procesados:
        resultado = enrutar_alto_valor(transaccion)
        if resultado:
            enrutados += 1

    print(f"\n  ✅ {enrutados} transacciones enrutadas al Service Bus")
    print(f"  📋 Dead-letter queue: {len(dead_letter_queue)} mensajes\n")
    return service_bus_queue


if __name__ == "__main__":
    from event_generator import publicar_eventos
    from function_validate import procesar_batch
    event_hub = publicar_eventos(10)
    procesados = procesar_batch(event_hub)
    cola = procesar_cola(procesados)
    print(f"\nCola Service Bus ({len(cola)} mensajes):")
    for msg in cola:
        print(" ", msg)
