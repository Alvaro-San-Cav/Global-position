/** La tarea no ha dejado rastro en más de 2,5 intervalos (mín. 1 h): probablemente ya no se ejecuta. */
export function autoLooksStopped(lastAutoAt: string | null | undefined, minutes: number, now = Date.now()): boolean {
  if (!lastAutoAt) return false
  const t = new Date(lastAutoAt).getTime()
  if (Number.isNaN(t)) return false
  return now - t > Math.max(2.5 * minutes, 60) * 60_000
}
