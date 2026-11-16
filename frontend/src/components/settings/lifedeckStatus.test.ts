import { describe, expect, it } from 'vitest'
import { autoLooksStopped } from './lifedeckStatus'

const NOW = Date.parse('2026-11-16T12:00:00Z')

describe('autoLooksStopped', () => {
  it('no avisa sin ejecuciones o con fecha inválida', () => {
    expect(autoLooksStopped(null, 30, NOW)).toBe(false)
    expect(autoLooksStopped('ayer', 30, NOW)).toBe(false)
  })

  it('avisa pasadas 2,5 veces el intervalo', () => {
    expect(autoLooksStopped('2026-11-16T10:00:00Z', 30, NOW)).toBe(true) // 120 min > 75
    expect(autoLooksStopped('2026-11-16T11:30:00Z', 30, NOW)).toBe(false)
    expect(autoLooksStopped('2026-11-16T08:00:00Z', 120, NOW)).toBe(false) // 240 min < 300
    expect(autoLooksStopped('2026-11-16T06:00:00Z', 120, NOW)).toBe(true)
  })

  it('nunca avisa antes de una hora aunque el intervalo sea corto', () => {
    expect(autoLooksStopped('2026-11-16T11:15:00Z', 15, NOW)).toBe(false) // 45 min
    expect(autoLooksStopped('2026-11-16T10:55:00Z', 15, NOW)).toBe(true)
  })
})
