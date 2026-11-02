import { ChevronDown } from 'lucide-react'
import { LANGUAGES } from '../lib/languages.js'
import { cn } from '../lib/cn.js'

export default function LanguageSelector({
  value,
  onChange,
  label = 'Language',
  id = 'language-select',
  disabled = false,
  className,
}) {
  return (
    <div className={cn('w-full', className)}>
      <label htmlFor={id} className="label">
        {label}
      </label>
      <div className="relative">
        <select
          id={id}
          value={value}
          onChange={(event) => onChange(event.target.value)}
          disabled={disabled}
          aria-label={label}
          className="field appearance-none pr-9 font-medium disabled:cursor-not-allowed disabled:opacity-60"
        >
          {LANGUAGES.map((language) => (
            <option key={language.id} value={language.id} className="bg-ink-900 text-mist-100">
              {language.label}
            </option>
          ))}
        </select>
        <ChevronDown
          className="pointer-events-none absolute top-1/2 right-3 h-4 w-4 -translate-y-1/2 text-mist-500"
          aria-hidden="true"
        />
      </div>
    </div>
  )
}
