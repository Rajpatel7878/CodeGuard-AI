import { Code2, FileCheck, History, LayoutDashboard, Settings } from 'lucide-react'

export const NAV_ITEMS = [
  { to: '/', label: 'Dashboard', icon: LayoutDashboard, end: true },
  { to: '/review', label: 'Review Code', icon: Code2 },
  { to: '/results', label: 'Results', icon: FileCheck },
  { to: '/history', label: 'Review History', icon: History },
  { to: '/settings', label: 'Settings', icon: Settings },
]

export function getPageTitle(pathname) {
  if (pathname.startsWith('/review')) return 'Review Code'
  if (pathname.startsWith('/results')) return 'Results'
  if (pathname.startsWith('/history')) return 'Review History'
  if (pathname.startsWith('/settings')) return 'Settings'
  return 'Dashboard'
}
