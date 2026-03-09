import { useEffect, useRef, useCallback } from "react";
import type { WebSocketMessage } from "../types";

const WS_URL = import.meta.env.VITE_WS_URL || "ws://localhost:8080/ws";
const RECONNECT_DELAY = 3000;

type MessageHandler = (msg: WebSocketMessage) => void;

export function useWebSocket(onMessage: MessageHandler) {
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const isMounted = useRef(true);

  const connect = useCallback(() => {
    if (!isMounted.current) return;

    const ws = new WebSocket(WS_URL);
    wsRef.current = ws;

    ws.onopen = () => {
      console.log("[WS] Connected");
      if (reconnectRef.current) {
        clearTimeout(reconnectRef.current);
        reconnectRef.current = null;
      }
    };

    ws.onmessage = (event) => {
      try {
        const msg: WebSocketMessage = JSON.parse(event.data);
        onMessage(msg);
      } catch {
        // ignore malformed messages
      }
    };

    ws.onerror = () => {
      console.warn("[WS] Error");
    };

    ws.onclose = () => {
      console.log("[WS] Disconnected - reconnecting in 3s");
      if (isMounted.current) {
        reconnectRef.current = setTimeout(connect, RECONNECT_DELAY);
      }
    };
  }, [onMessage]);

  useEffect(() => {
    isMounted.current = true;
    connect();
    return () => {
      isMounted.current = false;
      if (reconnectRef.current) clearTimeout(reconnectRef.current);
      wsRef.current?.close();
    };
  }, [connect]);
}
