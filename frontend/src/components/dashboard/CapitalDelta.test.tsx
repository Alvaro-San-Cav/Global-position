import { describe, it, expect } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { CapitalDelta } from './CapitalDelta'
import type { PortfolioChart } from '@/api/types'

const chart: PortfolioChart = {
  value: [
    { x: '2025-07-10', y: 50000 },
    { x: '2026-06-10', y: 90000 },
    { x: '2026-07-07', y: 98000 },
    { x: '2026-07-09', y: 99000 },
    { x: '2026-07-10', y: 100000 },
  ],
  invested: [
    { x: '2025-07-10', y: 40000 },
    { x: '2026-06-10', y: 60000 },
    { x: '2026-07-07', y: 60000 },
    { x: '2026-07-09', y: 60000 },
    { x: '2026-07-10', y: 60000 },
  ],
}

describe('CapitalDelta', () => {
  it('defaults to Ayer: delta vs previous point', () => {
    render(<CapitalDelta chart={chart} />)
    // 100000 - 99000 = +1000
    expect(screen.getByText(/\+1\.?000,00/)).toBeInTheDocument()
    expect(screen.getByText(/desde 09\/07\/2026/)).toBeInTheDocument()
  })

  it('Semana uses closest point at or before cutoff', () => {
    render(<CapitalDelta chart={chart} />)
    fireEvent.click(screen.getByText('Semana'))
    // cutoff 2026-07-03 → falls back to 2026-06-10 (90000): +10000
    expect(screen.getByText(/\+10\.000,00/)).toBeInTheDocument()
    expect(screen.getByText(/desde 10\/06\/2026/)).toBeInTheDocument()
  })

  it('Histórico compares against first point and shows net-of-flows variation', () => {
    render(<CapitalDelta chart={chart} />)
    fireEvent.click(screen.getByText('Histórico'))
    // 100000 - 50000 = +50000; flows = 20000; market = +30000
    expect(screen.getByText(/\+50\.000,00/)).toBeInTheDocument()
    expect(screen.getByText(/Aportaciones netas/)).toBeInTheDocument()
    expect(screen.getByText(/\+30\.000,00/)).toBeInTheDocument()
  })

  it('renders nothing with fewer than 2 points', () => {
    const { container } = render(
      <CapitalDelta chart={{ value: [{ x: '2026-07-10', y: 100 }], invested: [] }} />,
    )
    expect(container).toBeEmptyDOMElement()
  })

  it('colors negative delta red', () => {
    render(
      <CapitalDelta
        chart={{
          value: [
            { x: '2026-07-09', y: 100000 },
            { x: '2026-07-10', y: 99000 },
          ],
          invested: [],
        }}
      />,
    )
    const el = screen.getByText(/-1\.?000,00/)
    expect(el.closest('div')!.className).toContain('text-red')
  })

  function endOfMonthChart(end: string, cutoffDay: string): PortfolioChart {
    return {
      value: [
        { x: '2020-01-01', y: 1 },
        { x: cutoffDay, y: 100 },
        { x: end, y: 150 },
      ],
      invested: [],
    }
  }

  it('Mes from 31 March cuts at 28 Feb (no overflow into March)', () => {
    render(<CapitalDelta chart={endOfMonthChart('2026-03-31', '2026-02-28')} />)
    fireEvent.click(screen.getByText('Mes'))
    expect(screen.getByText(/desde 28\/02\/2026/)).toBeInTheDocument()
  })

  it('Trimestre from 31 May cuts at 28 Feb', () => {
    render(<CapitalDelta chart={endOfMonthChart('2026-05-31', '2026-02-28')} />)
    fireEvent.click(screen.getByText('Trimestre'))
    expect(screen.getByText(/desde 28\/02\/2026/)).toBeInTheDocument()
  })

  it('Año from 29 Feb 2028 cuts at 28 Feb 2027', () => {
    render(<CapitalDelta chart={endOfMonthChart('2028-02-29', '2027-02-28')} />)
    fireEvent.click(screen.getByText('Año'))
    expect(screen.getByText(/desde 28\/02\/2027/)).toBeInTheDocument()
  })

  it('period buttons are type=button with aria-pressed', () => {
    render(<CapitalDelta chart={chart} />)
    const mes = screen.getByRole('button', { name: 'Mes' })
    expect(mes).toHaveAttribute('type', 'button')
    expect(mes).toHaveAttribute('aria-pressed', 'false')
    fireEvent.click(mes)
    expect(mes).toHaveAttribute('aria-pressed', 'true')
  })
})
