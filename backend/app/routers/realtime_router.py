from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ..services.realtime import manager

router = APIRouter()

@router.websocket('/ws/dispatch')
async def websocket_dispatch(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_json()
            if data.get('type') == 'ping':
                await manager.send_personal_message(websocket, {'type': 'pong'})
            # noop: backend initiates events via broadcast_event
    except WebSocketDisconnect:
        manager.disconnect(websocket)
