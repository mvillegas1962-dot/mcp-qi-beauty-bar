import json
import httpx
from mcp.server.fastmcp import FastMCP
from mcp.server.sse import SseServerTransport
from starlette.applications import Starlette
from starlette.routing import Route

AGENDAPRO_API_KEY = "apk_live_9e6a576c0be489891777985b4e029444"
AGENDAPRO_BASE    = "https://connect.agendapro.com/v3"
LOCATION_ID       = 3856
PROVIDER_ID       = 22861  # Regina Villegas

HEADERS = {
    "Authorization": f"Bearer {AGENDAPRO_API_KEY}",
    "Content-Type": "application/json",
}

mcp = FastMCP("qi-beauty-bar")

@mcp.tool()
async def consultar_servicios() -> str:
    """Devuelve la lista de servicios de Qi Beauty Bar con ID, nombre, precio y duración.
    Úsalo cuando el cliente pregunte qué servicios hay, precios o duración."""
    async with httpx.AsyncClient() as client:
        r = await client.get(
            f"{AGENDAPRO_BASE}/services",
            headers=HEADERS,
            params={"location_id": LOCATION_ID},
        )
    data = r.json().get("data", [])
    servicios = [
        {
            "id": s["id"],
            "nombre": s["name"],
            "precio": f"${float(s['price']):.0f} MXN",
            "duracion": f"{s['duration']} min",
            "categoria": s.get("category", {}).get("name", ""),
        }
        for s in data if s.get("active") and s.get("online_booking")
    ]
    return json.dumps(servicios, ensure_ascii=False)

@mcp.tool()
async def consultar_disponibilidad(fecha: str, servicio_id: int) -> str:
    """Consulta horarios disponibles para una fecha y servicio específico.
    Parámetros: fecha (YYYY-MM-DD), servicio_id (número entero).
    Úsalo cuando el cliente quiera saber qué horas hay disponibles."""
    async with httpx.AsyncClient() as client:
        r = await client.get(
            f"{AGENDAPRO_BASE}/available_slots",
            headers=HEADERS,
            params={
                "location_id": LOCATION_ID,
                "service_id": servicio_id,
                "date": fecha,
            },
        )
    data = r.json()
    slots = data.get("data", [])
    if not slots:
        return f"No hay horarios disponibles para el {fecha}."
    horarios = [s.get("time", s) for s in slots]
    return json.dumps({"fecha": fecha, "horarios_disponibles": horarios}, ensure_ascii=False)

@mcp.tool()
async def crear_cita(nombre: str, telefono: str, email: str,
                     servicio_id: int, fecha: str, hora: str) -> str:
    """Crea una cita en AgendaPro para un cliente de Qi Beauty Bar.
    Parámetros: nombre, telefono, email, servicio_id, fecha (YYYY-MM-DD), hora (HH:MM).
    Úsalo cuando el cliente confirme que quiere agendar y ya tengas todos sus datos."""
    payload = {
        "location_id": LOCATION_ID,
        "provider_id": PROVIDER_ID,
        "service_id": servicio_id,
        "date": fecha,
        "time": hora,
        "client": {"name": nombre, "phone": telefono, "email": email},
    }
    async with httpx.AsyncClient() as client:
        r = await client.post(f"{AGENDAPRO_BASE}/bookings", headers=HEADERS, json=payload)
    if r.status_code in (200, 201):
        data = r.json().get("data", {})
        return json.dumps({
            "exito": True,
            "mensaje": f"Cita confirmada para {nombre} el {fecha} a las {hora}.",
            "id_cita": data.get("id"),
        }, ensure_ascii=False)
    return json.dumps({"exito": False, "detalle": r.text}, ensure_ascii=False)

@mcp.tool()
async def cancelar_cita(id_cita: int) -> str:
    """Cancela una cita existente en AgendaPro dado su ID numérico.
    Úsalo cuando el cliente quiera cancelar una cita que ya tiene agendada."""
    async with httpx.AsyncClient() as client:
        r = await client.patch(f"{AGENDAPRO_BASE}/bookings/{id_cita}/cancel", headers=HEADERS)
    if r.status_code in (200, 204):
        return json.dumps({"exito": True, "mensaje": "Cita cancelada correctamente."}, ensure_ascii=False)
    return json.dumps({"exito": False, "detalle": r.text}, ensure_ascii=False)

sse = SseServerTransport("/messages/")

async def handle_sse(request):
    async with sse.connect_sse(request.scope, request.receive, request._send) as streams:
        await mcp.run(streams[0], streams[1], mcp.create_initialization_options())

app = Starlette(routes=[
    Route("/sse", endpoint=handle_sse),
    Route("/messages/", endpoint=sse.handle_post_message, methods=["POST"]),
])

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
