import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
  DialogClose,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'

interface ConfirmDeleteDialogProps {
  /** Filename pending deletion, or null when closed. */
  filename: string | null
  onOpenChange: (open: boolean) => void
  onConfirm: () => void
  busy?: boolean
}

/** Confirmation dialog for deleting a pending / source file. */
export function ConfirmDeleteDialog({
  filename,
  onOpenChange,
  onConfirm,
  busy = false,
}: ConfirmDeleteDialogProps) {
  return (
    <Dialog open={filename !== null} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Eliminar archivo</DialogTitle>
          <DialogDescription>
            ¿Seguro que quieres eliminar{' '}
            <span className="font-medium text-txt">{filename}</span>? Esta
            acción no se puede deshacer.
          </DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <DialogClose asChild>
            <Button variant="outline" size="sm" disabled={busy}>
              Cancelar
            </Button>
          </DialogClose>
          <Button
            variant="danger"
            size="sm"
            disabled={busy}
            onClick={onConfirm}
          >
            {busy ? 'Eliminando…' : 'Eliminar'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
