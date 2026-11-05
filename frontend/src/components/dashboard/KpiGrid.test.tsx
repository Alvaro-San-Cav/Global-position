import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { KpiGrid, InfoDot } from './KpiGrid'
import type { Metrics } from '@/api/types'

const base: Metrics = {
  valor_total: 107312.56,
  capital_total: 71409.11,
  plusvalia_total: 35903.45,
  rentabilidad_total: 50.28,
  cagr_total: 6.65,
  twr_total_anual: 6.76,
}

describe('KpiGrid', () => {
  it('renders total KPIs', () => {
    render(<KpiGrid metrics={base} />)
    expect(screen.getByText('Valor total')).toBeInTheDocument()
    expect(screen.getByText('Capital aportado')).toBeInTheDocument()
    expect(screen.getAllByText(/107\.312,56/).length).toBeGreaterThan(0)
  })

  it('colors a negative plusvalía red', () => {
    render(<KpiGrid metrics={{ ...base, plusvalia_total: -1000 }} />)
    const negative = screen.getAllByText(/-1\.?000,00/)[0]
    expect(negative.className).toContain('text-red')
  })

  it('shows benchmark section only when present', () => {
    const { rerender } = render(<KpiGrid metrics={base} />)
    expect(screen.queryByText(/vs /)).not.toBeInTheDocument()
    rerender(
      <KpiGrid
        metrics={{ ...base, benchmark_ticker: 'IWDA.AS', benchmark_name: 'MSCI World', benchmark_annual: 15.36 }}
      />,
    )
    expect(screen.getByText(/vs MSCI World/)).toBeInTheDocument()
  })
})

describe('InfoDot', () => {
  it('is a focusable button described by its tooltip', () => {
    render(<InfoDot text="Explicacion" />)
    const btn = screen.getByRole('button', { name: 'Más información' })
    expect(btn).toHaveAttribute('type', 'button')
    const tip = screen.getByRole('tooltip', { hidden: true })
    expect(btn.getAttribute('aria-describedby')).toBe(tip.id)
    expect(tip).toHaveTextContent('Explicacion')
    expect(tip.className).toContain('group-focus-within:opacity-100')
    btn.focus()
    expect(btn).toHaveFocus()
  })
})
