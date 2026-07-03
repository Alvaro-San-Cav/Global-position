import { useRef, useState, type DragEvent } from 'react'
import { UploadCloud, Loader2 } from 'lucide-react'
import { cn } from '@/lib/utils'

interface DropzoneProps {
  onFiles: (files: File[]) => void
  busy?: boolean
}

/**
 * Native drag-&-drop dropzone (no external lib). Clicking opens the file
 * picker; dropping or selecting `.csv` files calls `onFiles`.
 */
export function Dropzone({ onFiles, busy = false }: DropzoneProps) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [active, setActive] = useState(false)

  function pick(files: FileList | null) {
    if (!files || files.length === 0) return
    onFiles(Array.from(files))
  }

  function handleDrop(e: DragEvent<HTMLDivElement>) {
    e.preventDefault()
    setActive(false)
    if (busy) return
    pick(e.dataTransfer.files)
  }

  function handleDragOver(e: DragEvent<HTMLDivElement>) {
    e.preventDefault()
    if (!busy) setActive(true)
  }

  function handleDragLeave(e: DragEvent<HTMLDivElement>) {
    e.preventDefault()
    setActive(false)
  }

  return (
    <div
      role="button"
      tabIndex={0}
      aria-disabled={busy}
      onClick={() => !busy && inputRef.current?.click()}
      onKeyDown={(e) => {
        if ((e.key === 'Enter' || e.key === ' ') && !busy) {
          e.preventDefault()
          inputRef.current?.click()
        }
      }}
      onDrop={handleDrop}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      className={cn(
        'flex cursor-pointer flex-col items-center gap-2 rounded-[var(--radius-card-lg)] border-2 border-dashed border-border-strong bg-card2/30 px-6 py-9 text-center transition-colors',
        active && 'border-accent bg-accent/5',
        busy && 'pointer-events-none opacity-70',
      )}
    >
      <input
        ref={inputRef}
        type="file"
        accept=".csv"
        multiple
        className="hidden"
        onChange={(e) => {
          pick(e.target.files)
          e.target.value = ''
        }}
      />
      {busy ? (
        <Loader2 className="size-7 animate-spin text-accent" />
      ) : (
        <UploadCloud className="size-7 text-txt3" />
      )}
      <div className="text-sm font-semibold text-txt">
        {busy ? 'Subiendo…' : 'Arrastra o haz clic para seleccionar'}
      </div>
      <div className="text-xs text-txt3">
        Archivos CSV de Degiro, exchanges o fuentes personalizadas
      </div>
    </div>
  )
}
