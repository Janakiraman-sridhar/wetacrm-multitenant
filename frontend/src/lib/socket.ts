import { io, Socket } from "socket.io-client";

import { API_URL, tokenStore } from "./api";

let socket: Socket | null = null;

export function connectSocket(): Socket | null {
  const token = tokenStore.access;
  if (!token) return null;
  if (socket?.connected) return socket;
  socket = io(API_URL || window.location.origin, {
    path: "/ws/socket.io",
    auth: { token },
    transports: ["websocket", "polling"],
    reconnectionAttempts: 5,
  });
  return socket;
}

export function disconnectSocket(): void {
  socket?.disconnect();
  socket = null;
}
