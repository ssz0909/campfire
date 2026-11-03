export type LoginViewport = { width: number; height: number }
export type LoginPointer = { id: number; clientX: number; clientY: number; x: number; y: number }

export function loginPoint(clientX: number, clientY: number, rect: DOMRect, viewport: LoginViewport) {
  return {
    x: Math.min(viewport.width - 1, Math.max(0, Math.floor((clientX - rect.left) * viewport.width / rect.width))),
    y: Math.min(viewport.height - 1, Math.max(0, Math.floor((clientY - rect.top) * viewport.height / rect.height))),
  }
}

export function loginPointerAction(start: LoginPointer, end: { x: number; y: number }, clientX: number, clientY: number) {
  // Measure hand movement in the displayed image, not the enlarged remote viewport.
  return Math.hypot(clientX - start.clientX, clientY - start.clientY) > 8
    ? { kind: 'drag', x: start.x, y: start.y, end_x: end.x, end_y: end.y }
    : { kind: 'click', x: start.x, y: start.y }
}
