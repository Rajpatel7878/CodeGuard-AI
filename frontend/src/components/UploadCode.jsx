import { useRef, useState } from 'react'
import { AlertCircle, FileCode2, Upload, X } from 'lucide-react'
import { cn } from '../lib/cn.js'
import { CODE_FILE_EXTENSIONS } from '../lib/languages.js'

const MAX_BYTES = 200 * 1024

function extensionOf(fileName = '') {
  return fileName.includes('.') ? fileName.split('.').pop().toLowerCase() : ''
}

/**
 * Loads a source file into the editor, via the file picker or drag and drop.
 */
export default function UploadCode({ onFileLoad, onClear, fileName, disabled = false }) {
  const inputRef = useRef(null)
  const [dragActive, setDragActive] = useState(false)
  const [error, setError] = useState('')

  async function readFile(file) {
    if (!file) return
    setError('')

    const extension = extensionOf(file.name)
    if (!CODE_FILE_EXTENSIONS.includes(extension)) {
      setError(
        extension
          ? `Unsupported file type ".${extension}". Use a source file such as .js, .ts, .py, or .go.`
          : 'That file has no extension. Upload a source file such as .js, .ts, .py, or .go.',
      )
      return
    }

    if (file.size > MAX_BYTES) {
      setError('Files larger than 200 KB are not supported. Paste the relevant snippet instead.')
      return
    }

    try {
      const text = await file.text()
      if (!text.trim()) {
        setError('That file appears to be empty.')
        return
      }
      onFileLoad?.({ code: text, fileName: file.name, size: file.size })
    } catch {
      setError('That file could not be read. Try another file or paste the code.')
    }
  }

  function handleChange(event) {
    const file = event.target.files?.[0]
    void readFile(file)
    event.target.value = ''
  }

  function handleDrop(event) {
    event.preventDefault()
    setDragActive(false)
    if (disabled) return
    void readFile(event.dataTransfer.files?.[0])
  }

  return (
    <div>
      <div
        onDragOver={(event) => {
          event.preventDefault()
          if (!disabled) setDragActive(true)
        }}
        onDragLeave={() => setDragActive(false)}
        onDrop={handleDrop}
        className={cn(
          'flex items-center gap-3 rounded-xl border border-dashed px-3 py-2.5 transition-colors',
          dragActive
            ? 'border-brand-400 bg-brand-500/10'
            : 'border-ink-600 bg-ink-950/40 hover:border-ink-500',
          disabled && 'opacity-60',
        )}
      >
        <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-ink-700 bg-ink-800/70 text-mist-400">
          {fileName ? (
            <FileCode2 className="h-4 w-4" aria-hidden="true" />
          ) : (
            <Upload className="h-4 w-4" aria-hidden="true" />
          )}
        </span>

        <div className="min-w-0 flex-1">
          <p className="truncate text-xs font-medium text-mist-200">
            {fileName ?? 'Upload a file or drop it here'}
          </p>
          <p className="truncate text-[11px] text-mist-500">
            {fileName ? 'Loaded into the editor' : '.js .ts .py .java .go .rs · 200 KB max'}
          </p>
        </div>

        {fileName ? (
          <button
            type="button"
            onClick={onClear}
            disabled={disabled}
            aria-label="Remove uploaded file"
            className="btn btn-ghost shrink-0 p-1.5"
          >
            <X className="h-4 w-4" aria-hidden="true" />
          </button>
        ) : null}

        <button
          type="button"
          onClick={() => inputRef.current?.click()}
          disabled={disabled}
          className="btn btn-secondary shrink-0 px-3 py-1.5 text-xs"
        >
          Browse
        </button>
      </div>

      <input
        ref={inputRef}
        type="file"
        accept={CODE_FILE_EXTENSIONS.map((extension) => `.${extension}`).join(',')}
        onChange={handleChange}
        className="sr-only"
        tabIndex={-1}
        aria-hidden="true"
      />

      {error ? (
        <p role="alert" className="mt-2 flex items-start gap-1.5 text-xs text-rose-300">
          <AlertCircle className="mt-px h-3.5 w-3.5 shrink-0" aria-hidden="true" />
          <span>{error}</span>
        </p>
      ) : null}
    </div>
  )
}
