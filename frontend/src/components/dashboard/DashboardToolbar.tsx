import { FileDown, Loader2, RefreshCw, Wallet } from 'lucide-react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { useGenerateReport, useRefreshDashboard } from '@/api/queries'
import { downloadFile } from '@/api/client'
import { CashDialog } from '@/components/dashboard/CashDialog'

export function DashboardToolbar() {
  const refresh = useRefreshDashboard()
  const report = useGenerateReport()

  const onRefresh = () => {
    refresh.mutate(undefined, {
      onSuccess: () => toast.success('Precios actualizados'),
      onError: (e) => toast.error(`Error al actualizar: ${(e as Error).message}`),
    })
  }

  const onReport = async () => {
    try {
      await report.mutateAsync()
      await downloadFile('/api/report/pdf', 'informe.pdf')
      toast.success('Informe generado')
    } catch (e) {
      toast.error(`Error al generar PDF: ${(e as Error).message}`)
    }
  }

  return (
    <>
      <CashDialog
        trigger={
          <Button variant="outline" size="sm">
            <Wallet />
            Efectivo
          </Button>
        }
      />
      <Button variant="outline" size="sm" onClick={onRefresh} disabled={refresh.isPending}>
        {refresh.isPending ? (
          <Loader2 className="animate-spin" />
        ) : (
          <RefreshCw />
        )}
        Actualizar precios
      </Button>
      <Button size="sm" onClick={onReport} disabled={report.isPending}>
        {report.isPending ? <Loader2 className="animate-spin" /> : <FileDown />}
        Generar PDF
      </Button>
    </>
  )
}
