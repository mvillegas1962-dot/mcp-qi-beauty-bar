import json
import os
import httpx
import uvicorn
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

AGENDAPRO_API_KEY = "apk_live_9e6a576c0be489891777985b4e029444"
AGENDAPRO_BASE    = "https://connect.agendapro.com/v3"
LOCATION_ID       = 3856

HEADERS = {
    "Authorization": f"Bearer {AGENDAPRO_API_KEY}",
    "Content-Type": "application/json",
}

async def consultar_servicios():
    async with httpx.AsyncClient() as client:
        r = await client.get(f"{AGENDAPRO_BASE}/services", headers=HEADERS, params={"location_id": LOCATION_ID})
    data = r.json().get("data", [])
    return [{"id": s["id"], "nombre": s["name"], "precio": f"${float(s['price']):.0f} MXN", "duracion": f"{s['duration']} min"} for s in data if s.get("active") and s.get("online_booking")]

async def consultar_disponibilidad(fecha: str, servicio_id: int):
    async with httpx.AsyncClient() as client:
        r = await client.get(f"{AGENDAPRO_BASE}/available_slots", headers=HEADERS, params={"location_id": LOCATION_ID, "service_id": servicio_id, "start_date": fecha})
    print(f"DISPONIBILIDAD raw: {r.text[:2000]}")
    slots = r.json().get("data", {}).get("slots", [])
    if not slots:
        return {"mensaje": f"No hay horarios disponibles para el {fecha}."}
    return {
        "fecha": fecha,
        "horarios_disponibles": [
            {
                "hora": s.get("start_time"),
                "hora_fin": s.get("end_time"),
                "provider_id": s.get("provider_id"),
                "especialista": s.get("provider_name"),
                "time_resource_id": s.get("time_resource_id")
            }
            for s in slots
        ]
    }

async def buscar_o_crear_cliente(nombre: str, telefono: str, email: str) -> int:
    async with httpx.AsyncClient() as client:
        r = await client.get(
            f"{AGENDAPRO_BASE}/clients",
            headers=HEADERS,
            params={"location_id": LOCATION_ID, "email": email}
        )
        print(f"BUSCAR_CLIENTE status: {r.status_code} response: {r.text}")

        if r.status_code == 200:
            data = r.json().get("data", [])
            if data and len(data) > 0:
                client_id = data[0].get("id")
                print(f"CLIENTE ENCONTRADO id: {client_id}")
                return client_id

        partes = nombre.strip().split(" ", 1)
        first_name = partes[0]
        last_name = partes[1] if len(partes) > 1 else ""

        nuevo_cliente = {
            "location_id": LOCATION_ID,
            "first_name": first_name,
            "last_name": last_name,
            "phone": telefono,
            "email": email
        }
        print(f"CREAR_CLIENTE payload: {json.dumps(nuevo_cliente)}")
        r2 = await client.post(f"{AGENDAPRO_BASE}/clients", headers=HEADERS, json=nuevo_cliente)
        print(f"CREAR_CLIENTE status: {r2.status_code} response: {r2.text}")

        if r2.status_code in (200, 201):
            client_id = r2.json().get("data", {}).get("id")
            print(f"CLIENTE CREADO id: {client_id}")
            return client_id

        raise Exception(f"No se pudo obtener client_id. Respuesta: {r2.text}")

async def crear_cita(nombre: str, telefono: str, email: str, servicio_id: int, fecha: str, hora: str, provider_id: int = None, hora_fin: str = None, time_resource_id: int = None):
    client_id = await buscar_o_crear_cliente(nombre, telefono, email)

    start_time = f"{fecha}T{hora}:00Z"
    end_time = f"{fecha}T{hora_fin}:00Z" if hora_fin else None

    payload = {
        "location_id": LOCATION_ID,
        "service_id": servicio_id,
        "start_time": start_time,
        "status_id": 1,
        "client_id": client_id,
        "client": {"name": nombre, "phone": telefono, "email": email}
    }
    if provider_id:
        payload["provider_id"] = provider_id
    if end_time:
        payload["end_time"] = end_time
    if time_resource_id:
        payload["time_resource_id"] = time_resource_id

    print(f"CREAR_CITA payload: {json.dumps(payload)}")
    async with httpx.AsyncClient() as client:
        r = await client.post(f"{AGENDAPRO_BASE}/bookings", headers=HEADERS, json=payload)
    print(f"CREAR_CITA status: {r.status_code} response: {r.text}")

    if r.status_code in (200, 201):
        data = r.json()
        scheduled = data.get("scheduled", False)
        print(f"CREAR_CITA scheduled: {scheduled}")
        return {
            "exito": True,
            "mensaje": f"Cita confirmada para {nombre} el {fecha} a las {hora}.",
            "id_cita": data.get("id"),
            "scheduled": scheduled
        }
    return {"exito": False, "detalle": r.text}

async def cancelar_cita(id_cita: int):
    async with httpx.AsyncClient() as client:
        r = await client.patch(f"{AGENDAPRO_BASE}/bookings/{id_cita}/cancel", headers=HEADERS)
    if r.status_code in (200, 204):
        return {"exito": True, "mensaje": "Cita cancelada correctamente."}
    return {"exito": False, "detalle": r.text}

TOOLS = [
    {"name": "consultar_servicios", "description": "Devuelve servicios de Qi Beauty Bar con ID, nombre, precio y duración. Úsalo cuando el cliente pregunte qué servicios hay, precios o duración.", "inputSchema": {"type": "object", "properties": {}, "required": []}},
    {"name": "consultar_disponibilidad", "description": "Consulta horarios disponibles para una fecha y servicio. Devuelve hora, hora_fin, provider_id, especialista y time_resource_id. SIEMPRE llama esta herramienta antes de crear una cita para obtener los valores exactos.", "inputSchema": {"type": "object", "properties": {"fecha": {"type": "string", "description": "Fecha en formato YYYY-MM-DD"}, "servicio_id": {"type": "integer", "description": "ID del servicio obtenido de consultar_servicios"}}, "required": ["fecha", "servicio_id"]}},
    {"name": "crear_cita", "description": "Crea una cita en AgendaPro. IMPORTANTE: Usa exactamente los valores de hora, hora_fin, provider_id y time_resource_id que devolvió consultar_disponibilidad sin modificarlos.", "inputSchema": {"type": "object", "properties": {"nombre": {"type": "string"}, "telefono": {"type": "string"}, "email": {"type": "string"}, "servicio_id": {"type": "integer"}, "fecha": {"type": "string", "description": "Fecha en formato YYYY-MM-DD"}, "hora": {"type": "string", "description": "Hora exactamente como la devolvió consultar_disponibilidad"}, "hora_fin": {"type": "string", "description": "Hora fin exactamente como la devolvió consultar_disponibilidad"}, "provider_id": {"type": "integer", "description": "ID del especialista exactamente como lo devolvió consultar_disponibilidad"}, "time_resource_id": {"type": "integer", "description": "time_resource_id exactamente como lo devolvió consultar_disponibilidad, puede ser null"}}, "required": ["nombre", "telefono", "email", "servicio_id", "fecha", "hora", "hora_fin", "provider_id"]}},
    {"name": "cancelar_cita", "description": "Cancela una cita existente dado su ID numérico.", "inputSchema": {"type": "object", "properties": {"id_cita": {"type": "integer"}}, "required": ["id_cita"]}},
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
                result = await crear_cita(
                    args["nombre"], args["telefono"], args["email"],
                    args["servicio_id"], args["fecha"], args["hora"],
                    args.get("provider_id"), args.get("hora_fin"),
                    args.get("time_resource_id")
                )
            elif tool_name == "cancelar_cita":
                result = await cancelar_cita(args["id_cita"])
            else:
                return JSONResponse({"jsonrpc": "2.0", "id": msg_id, "error": {"code": -32601, "message": f"Tool not found: {tool_name}"}})
            return JSONResponse({"jsonrpc": "2.0", "id": msg_id, "result": {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False)}]}})
        except Exception as e:
            print(f"ERROR en tool {tool_name}: {str(e)}")
            return JSONResponse({"jsonrpc": "2.0", "id": msg_id, "error": {"code": -32000, "message": str(e)}})

    if method == "notifications/initialized":
        return Response(status_code=204)

    return JSONResponse({"jsonrpc": "2.0", "id": msg_id, "error": {"code": -32601, "message": f"Method not found: {method}"}})

app = Starlette(routes=[Route("/mcp", handle_mcp, methods=["POST"])])

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)




    
