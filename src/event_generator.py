"""
PayFlow — Generador de Eventos de Transacción
Equivalente a: Azure Event Hubs (ingesta de eventos)

Genera los 3 tipos de transacciones requeridos por el caso:
  - normal      : monto $1.000 – $300.000 COP → se espera 'aprobada'
  - alto_valor  : monto $5.000.001 – $10.000.000 COP → se espera 'en_revision'
  - invalido    : formato incorrecto (string) → se espera 'rechazada'
"""

import random
import json

# Simula el buffer de entrada de Azure Event Hubs
event_hub = []


def generar_transaccion():
    """Genera un evento de transacción de uno de los 3 tipos requeridos."""
    tipo = random.choice(["normal", "alto_valor", "invalido"])

    if tipo == "normal":
        return {
            "id": random.randint(1000, 9999),
            "comercio": random.choice(["Tienda A", "Supermercado XYZ", "Farmacia Central"]),
            "monto": random.randint(1000, 300000),
            "tipo": "normal"
        }

    if tipo == "alto_valor":
        return {
            "id": random.randint(1000, 9999),
            "comercio": random.choice(["Tienda VIP", "Inmobiliaria Norte", "Concesionario BMW"]),
            "monto": random.randint(5000001, 10000000),
            "tipo": "alto_valor"
        }

    # Tipo inválido: retorna string en lugar de dict
    return "ERROR_JSON_FORMATO_INVALIDO"


def publicar_eventos(n=10):
    """Publica n eventos en el Event Hub simulado."""
    print(f"\n{'='*55}")
    print(f"  PayFlow — Azure Event Hubs (Ingesta de Eventos)")
    print(f"{'='*55}")
    print(f"  Publicando {n} eventos...\n")

    for i in range(n):
        evento = generar_transaccion()
        event_hub.append(evento)
        tipo_display = evento.get("tipo", "invalido") if isinstance(evento, dict) else "invalido"
        print(f"  [{i+1:02d}] 📨 Evento enviado → tipo={tipo_display} | {json.dumps(evento) if isinstance(evento, dict) else evento}")

    print(f"\n  ✅ {len(event_hub)} eventos en el buffer de Event Hubs\n")
    return event_hub


if __name__ == "__main__":
    eventos = publicar_eventos(10)
    print("Eventos en Event Hub:")
    for e in eventos:
        print(" ", e)
