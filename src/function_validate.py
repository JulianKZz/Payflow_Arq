"""
PayFlow — Validación y Antifraude
Equivalente a: Azure Functions (validarTransaccion + evaluarFraude)

Aplica las reglas antifraude ANTES de autorizar la transacción,
resolviendo el problema de detección reactiva de fraude del sistema legacy.

Trigger: Azure Event Hubs (evento de transacción)
Output:  Transacción con estado: aprobada | rechazada | en_revision
"""


def validar_transaccion(evento):
    """
    Azure Function: validarTransaccion + evaluarFraude

    Paso 1: Valida formato y campos obligatorios
    Paso 2: Aplica reglas antifraude antes de autorizar
    Paso 3: Clasifica por monto (enrutamiento posterior)
    """

    # --- Validación de formato (validarTransaccion) ---
    if not isinstance(evento, dict):
        return {
            "estado": "rechazada",
            "motivo": "formato_invalido — el evento no es un objeto JSON válido"
        }

    campos_requeridos = ["id", "monto", "comercio"]
    for campo in campos_requeridos:
        if campo not in evento:
            return {
                "estado": "rechazada",
                "motivo": f"campo_faltante — falta el campo '{campo}'"
            }

    monto = evento["monto"]

    # --- Reglas antifraude (evaluarFraude) — ANTES de autorizar ---
    if not isinstance(monto, (int, float)):
        return {
            "id": evento["id"],
            "comercio": evento.get("comercio", "desconocido"),
            "monto": monto,
            "estado": "rechazada",
            "motivo": "fraude_detectado — tipo de monto inválido"
        }

    if monto < 0:
        return {
            "id": evento["id"],
            "comercio": evento.get("comercio", "desconocido"),
            "monto": monto,
            "estado": "rechazada",
            "motivo": "fraude_detectado — monto negativo"
        }

    if monto == 0:
        return {
            "id": evento["id"],
            "comercio": evento.get("comercio", "desconocido"),
            "monto": monto,
            "estado": "rechazada",
            "motivo": "fraude_detectado — monto cero"
        }

    # --- Enrutamiento por monto (enrutarPorMonto) ---
    estado = "aprobada"
    if monto > 5_000_000:
        estado = "en_revision"  # → Canal diferenciado: Service Bus

    return {
        "id": evento["id"],
        "comercio": evento.get("comercio", "desconocido"),
        "monto": monto,
        "tipo": evento.get("tipo", "desconocido"),
        "estado": estado
    }


def procesar_batch(event_hub):
    """Procesa todos los eventos del Event Hub."""
    print(f"\n{'='*55}")
    print(f"  PayFlow — Azure Functions (Validación + Antifraude)")
    print(f"{'='*55}")
    print(f"  Procesando {len(event_hub)} eventos...\n")

    procesados = []
    for i, evento in enumerate(event_hub):
        resultado = validar_transaccion(evento)
        procesados.append(resultado)
        estado = resultado.get("estado", "?")
        icono = {"aprobada": "✅", "rechazada": "❌", "en_revision": "🚨"}.get(estado, "❓")
        print(f"  [{i+1:02d}] {icono} id={resultado.get('id','?')} | monto={resultado.get('monto','?')} | estado={estado}")

    print(f"\n  Resumen:")
    for estado in ["aprobada", "rechazada", "en_revision"]:
        count = sum(1 for p in procesados if p.get("estado") == estado)
        print(f"    {estado}: {count}")

    return procesados


if __name__ == "__main__":
    from event_generator import publicar_eventos
    event_hub = publicar_eventos(10)
    procesados = procesar_batch(event_hub)
