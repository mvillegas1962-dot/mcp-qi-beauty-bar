import json
import os
import httpx
import uvicorn
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route
from starlette.middleware import Middleware
from starlette.middleware.base import BaseHTTPMiddleware

AGENDAPRO_API_KEY = "apk_live_9e6a576c0be489891777985b4e029444"
AGENDAPRO_BASE    = "https://connect.agendapro.com/v3"
LOCATION_ID       = 3856
PROVIDER_ID       = 22861

HEADERS = {
    "Authorization": f"Bearer {AGENDAPRO_API_KEY}",
    "Content-Type": "application/json",
}

# ── Tools ──────────────────────────────────────────────────

async def consultar_servicios():
    async with httpx.AsyncClient() as client:
        r = await client.get(f"{AGENDAPRO_BASE}/services", headers=HEADERS, params={"location_id": LOCATION_ID})
    data = r.json().get("data", [])
    return [{"id": s["id"], "nombre": s["name"], "precio": f"${float(s['price']):.0f} MXN", "duracion": f"{s['duration']} min"} for s in data if s.get("active") and s.get("online_booking")]

async def consultar_disponibilidad(fecha: str, servicio_id: int):
    async with httpx.AsyncClient() as client:
        r = await client.get(f"{AGENDAPRO_BASE}/available_slots", headers=HEADERS, params={"location_id": LOCATION_ID, "service_id": servicio_id, "date": fecha})
    slots = r.json().get("data", [])
    if not slots:
        return {"mensaje": f"No hay horarios disponibles para el {fecha}."}
    return {"fecha": fecha, "horarios_disponibles": [s.get("time", str(s)) for s in slots]}

async def crear_cita(nombre: str, telefono: str, email: str, servicio_id: int, fecha: str, hora: str):
    payload = {"location_id": LOCATION_ID, "provider_id": PROVIDER_ID, "service_id": servicio_id, "date": fecha, "time": hora, "client": {"name": nombre, "phone": telefono, "email": email}}
    async with httpx.AsyncClient() as client:
        r = await client.post(f"{AGENDAPRO_BASE}/bookings", headers=HEADERS, json=payload)
    if r.status_code in (200, 201):
        return {"exito": True, "mensaje": f"Cita confirmada para {nombre} el {fecha} a las {hora}.", "id_cita": r.json().get("data", {}).get("id")}
    return {"exito": False, "detalle": r.text}

async def cancelar_cita(id_cita: int):
    async with httpx.AsyncClient() as client:
        r = await client.patch(f"{AGENDAPRO_BASE}/bookings/{id_cita}/cancel", headers=HEADERS)
    if r.status_code in (200, 204):
        return {"exito": True, "mensaje": "Cita cancelada correctamente."}
    return {"exito": False, "detalle": r.text}

# ── MCP Handler ────────────────────────────────────────────

TOOLS = [
    {"name": "consultar_servicios", "description": "Devuelve servicios de Qi Beauty Bar con ID, nombre, precio y duración. Úsalo cuando el cliente pregunte qué servicios hay, precios o duración.", "inputSchema": {"type": "object", "properties": {}, "required": []}},
    {"name": "consultar_disponibilidad", "description": "Consulta horarios disponibles para una fecha y servicio. Úsalo cuando el cliente quiera saber qué horas hay disponibles.", "inputSchema": {"type": "object", "properties": {"fecha": {"type": "string", "description": "Fecha en formato YYYY-MM-DD"}, "servicio_id": {"type": "integer", "description": "ID del servicio"}}, "required": ["fecha", "servicio_id"]}},
    {"name": "crear_cita", "description": "Crea una cita en AgendaPro. Úsalo cuando el cliente confirme que quiere agendar y tengas todos sus datos.", "inputSchema": {"type": "object", "properties": {"nombre": {"type": "string"}, "telefono": {"type": "string"}, "email": {"type": "string"}, "servicio_id": {"type": "integer"}, "fecha": {"type": "string"}, "hora": {"type": "string"}}, "required": ["nombre", "telefono", "email", "servicio_id", "fecha", "hora"]}},
    {"name": "cancelar_cita", "description": "Cancela una cita existente dado su ID numérico. Úsalo cuando el cliente quiera cancelar una cita agendada.", "inputSchema": {"type": "object", "properties": {"id_cita": {"type": "integer"}}, "required": ["id_cita"]}},
]

async def handle_mcp(request: Request):
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON"}, status_code=400)

    method = body.get("method")
    msg_id = body.get("id")
    params = body.get("params", {})

    if method == "initialize":
        return JSONResponse({"jsonrpc": "2.0", "id": msg_id, "result": {"protocolVersion": "2024-11-05", "capabilities": {"tools": {}}, "serverInfo": {"name": "qi-beauty-bar", "version": "1.0.0"}}})

    if method == "tools/list":
        return JSONResponse({"jsonrpc": "2.0", "id": msg_id, "result": {"tools": TOOLS}})

    if method == "tools/call":
        tool_name = params.get("name")
        args = params.get("arguments", {})
        try:
            if tool_name == "consultar_servicios":
                result = await consultar_servicios()
            elif tool_name == "consultar_disponibilidad":
                result = await consultar_disponibilidad(args["fecha"], args["servicio_id"])
            elif tool_name == "crear_cita":
                result = await crear_cita(args["nombre"], args["telefono"], args["email"], args["servicio_id"], args["fecha"], args["hora"])
            elif tool_name == "cancelar_cita":
                result = await cancelar_cita(args["id_cita"])
            else:
                return JSONResponse({"jsonrpc": "2.0", "id": msg_id, "error": {"code": -32601, "message": f"Tool not found: {tool_name}"}})
            return JSONResponse({"jsonrpc": "2.0", "id": msg_id, "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False)}]}})
        except Exception as e:
            return JSONResponse({"jsonrpc": "2.0", "id": msg_id, "error": {"code": -32000, "message": str(e)}})

    if method == "notifications/initialized":
        return Response(status_code=204)

    return JSONResponse({"jsonrpc": "2.0", "id": msg_id, "error": {"code": -32601, "message": f"Method not found: {method}"}})

app = Starlette(routes=[Route("/mcp", handle_mcp, methods=["POST"])])

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)
    
