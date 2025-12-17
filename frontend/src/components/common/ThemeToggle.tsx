import { Sun, Moon } from 'lucide-react'
import { useThemeStore } from '../../store/themeStore'

export default function ThemeToggle() {
  const { theme, setTheme } = useThemeStore()

  const toggleTheme = () => {
    if (theme === 'dark') {
      setTheme('light')
    } else {
      setTheme('dark')
    }
  }

  const isDark = theme === 'dark' || (theme === 'system' && typeof window !== 'undefined' && window.matchMedia('(prefers-color-scheme: dark)').matches)

  return (
    <button
      type="button"
      onClick={toggleTheme}
      className="flex h-8 w-8 items-center justify-center rounded-md border border-border bg-background text-foreground hover:bg-muted transition-colors"
      aria-label={isDark ? 'Switch to light mode' : 'Switch to dark mode'}
      title={isDark ? 'Switch to light mode' : 'Switch to dark mode'}
    >
      {isDark ? (
        <Sun className="h-4 w-4" />
      ) : (
        <Moon className="h-4 w-4" />
      )}
    </button>
  )
}
