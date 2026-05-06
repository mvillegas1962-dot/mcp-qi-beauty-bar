import json
import os
import httpx
from mcp.server.fastmcp import FastMCP
from mcp.server.sse import SseServerTransport
from starlette.applications import Starlette
from starlette.routing import Route
import uvicorn

AGENDAPRO_API_KEY = "apk_live_9e6a576c0be489891777985b4e029444"
AGENDAPRO_BASE    = "https://connect.agendapro.com/v3"
LOCATION_ID       = 3856
PROVIDER_ID       = 22861

HEADERS = {
    "Authorization": f"Bearer {AGENDAPRO_API_KEY}",
    "Content-Type": "application/json",
}

mcp = FastMCP("qi-beauty-bar")

@mcp.tool()
async def consultar_servicios() -> str:
    """Devuelve servicios de Qi Beauty Bar con ID, nombre, precio y duración.
    Úsalo cuando el cliente pregunte qué servicios hay, precios o duración."""
    async with httpx.AsyncClient() as client:
        r = await client.get(f"{AGENDAPRO_BASE}/services", headers=HEADERS, params={"location_id": LOCATION_ID})
    data = r.json().get("data", [])
    servicios = [{"id": s["id"], "nombre": s["name"], "precio": f"${float(s['price']):.0f} MXN", "duracion": f"{s['duration']} min"} for s in data if s.get("active") and s.get("online_booking")]
    return json.dumps(servicios, ensure_ascii=False)

@mcp.tool()
async def consultar_disponibilidad(fecha: str, servicio_id: int) -> str:
    """Consulta horarios disponibles para una fecha y servicio.
    Parámetros: fecha (YYYY-MM-DD), servicio_id (entero).
    Úsalo cuando el cliente quiera saber qué horas hay disponibles."""
    async with httpx.AsyncClient() as client:
        r = await client.get(f"{AGENDAPRO_BASE}/available_slots", headers=HEADERS, params={"location_id": LOCATION_ID, "service_id": servicio_id, "date": fecha})
    slots = r.json().get("data", [])
    if not slots:
        return f"No hay horarios disponibles para el {fecha}."
    return json.dumps({"fecha": fecha, "horarios_disponibles": [s.get("time", str(s)) for s in slots]}, ensure_ascii=False)

@mcp.tool()
async def crear_cita(nombre: str, telefono: str, email: str, servicio_id: int, fecha: str, hora: str) -> str:
    """Crea una cita en AgendaPro. Parámetros: nombre, telefono, email, servicio_id, fecha (YYYY-MM-DD), hora (HH:MM).
    Úsalo cuando el cliente confirme que quiere agendar y tengas todos sus datos."""
    payload = {"location_id": LOCATION_ID, "provider_id": PROVIDER_ID, "service_id": servicio_id, "date": fecha, "time": hora, "client": {"name": nombre, "phone": telefono, "email": email}}
    async with httpx.AsyncClient() as client:
        r = await client.post(f"{AGENDAPRO_BASE}/bookings", headers=HEADERS, json=payload)
    if r.status_code in (200, 201):
        return json.dumps({"exito": True, "mensaje": f"Cita confirmada para {nombre} el {fecha} a las {hora}.", "id_cita": r.json().get("data", {}).get("id")}, ensure_ascii=False)
    return json.dumps({"exito": False, "detalle": r.text}, ensure_ascii=False)

@mcp.tool()
async def cancelar_cita(id_cita: int) -> str:
    """Cancela una cita existente dado su ID numérico.
    Úsalo cuando el cliente quiera cancelar una cita agendada."""
    async with httpx.AsyncClient() as client:
        r = await client.patch(f"{AGENDAPRO_BASE}/bookings/{id_cita}/cancel", headers=HEADERS)
    if r.status_code in (200, 204):
        return json.dumps({"exito": True, "mensaje": "Cita cancelada correctamente."}, ensure_ascii=False)
    return json.dumps({"exito": False, "detalle": r.text}, ensure_ascii=False)

sse_transport = SseServerTransport("/messages/")
starlette_app = mcp.sse_app()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(starlette_app, host="0.0.0.0", port=port) 
    
