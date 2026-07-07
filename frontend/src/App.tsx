import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { createBrowserRouter, RouterProvider } from 'react-router-dom'
import { AppShell } from '@/components/layout/AppShell'
import { Toaster } from '@/components/ui/sonner'
import { Dashboard } from '@/pages/Dashboard'
import { Operations } from '@/pages/Operations'
import { Crypto } from '@/pages/Crypto'
import { Tax } from '@/pages/Tax'
import { Import } from '@/pages/Import'
import { Settings } from '@/pages/Settings'
import { Objetivo } from '@/pages/Objetivo'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: 1, refetchOnWindowFocus: false },
  },
})

const router = createBrowserRouter([
  {
    path: '/',
    element: <AppShell />,
    children: [
      { index: true, element: <Dashboard /> },
      { path: 'operaciones', element: <Operations /> },
      { path: 'crypto', element: <Crypto /> },
      { path: 'objetivo', element: <Objetivo /> },
      { path: 'fiscalidad', element: <Tax /> },
      { path: 'importar', element: <Import /> },
      { path: 'ajustes', element: <Settings /> },
    ],
  },
])

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
      <Toaster />
    </QueryClientProvider>
  )
}
