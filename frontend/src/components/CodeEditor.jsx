import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import Editor from '@monaco-editor/react'
import {
  AlignJustify,
  Copy,
  FileText,
  Minus,
  Plus,
  RotateCcw,
  Sidebar,
  WrapText,
} from 'lucide-react'
import '../lib/monacoSetup.js'
import LoadingIndicator from './LoadingIndicator.jsx'
import { getLanguage } from '../lib/languages.js'

const THEME = 'alpha-codeguard'

const THEME_DEFINITION = {
  base: 'vs-dark',
  inherit: true,
  rules: [
    { token: 'comment', foreground: '5b6b85', fontStyle: 'italic' },
    { token: 'keyword', foreground: '8098ff' },
    { token: 'string', foreground: '7dd6b8' },
    { token: 'number', foreground: 'f0b072' },
    { token: 'type', foreground: 'e0a5ff' },
    { token: 'type.identifier', foreground: 'e0a5ff' },
    { token: 'identifier', foreground: 'd7e0ec' },
    { token: 'delimiter', foreground: '8494a8' },
  ],
  colors: {
    'editor.background': '#0a0f17',
    'editor.foreground': '#d7e0ec',
    'editorLineNumber.foreground': '#43516a',
    'editorLineNumber.activeForeground': '#8fa2c0',
    'editorCursor.foreground': '#7c9cff',
    'editor.lineHighlightBackground': '#111a26',
    'editor.selectionBackground': '#26406e',
    'editor.inactiveSelectionBackground': '#1b2a45',
    'editorIndentGuide.background1': '#1a2331',
    'editorIndentGuide.activeBackground1': '#2b3a50',
    'editorWidget.background': '#0f151f',
    'editorWidget.border': '#1a2331',
    'editorSuggestWidget.background': '#0f151f',
    'editorSuggestWidget.selectedBackground': '#1a2331',
    'scrollbarSlider.background': '#24303f80',
    'scrollbarSlider.hoverBackground': '#35435a90',
    'scrollbarSlider.activeBackground': '#35435ab0',
  },
}

function handleBeforeMount(monaco) {
  monaco.editor.defineTheme(THEME, THEME_DEFINITION)
  monaco.editor.setTheme(THEME)
}

/**
 * Reusable Monaco editor styled to match the CodeGuard theme.
 * Monaco is bundled locally (see lib/monacoSetup.js) so no CDN is required.
 */
export default function CodeEditor({
  value = '',
  onChange,
  language = 'javascript',
  languageId,
  fontSize: initialFontSize = 13,
  wordWrap: initialWordWrap = false,
  minimap: initialMinimap = false,
  readOnly = false,
  height = '100%',
  onMount,
  className,
  showToolbar = true,
  title = 'Code Editor',
  onClear,
}) {
  const editorRef = useRef(null)
  const [fontSize, setFontSize] = useState(initialFontSize)
  const [wordWrap, setWordWrap] = useState(initialWordWrap)
  const [minimap, setMinimap] = useState(initialMinimap)
  const [formatStatus, setFormatStatus] = useState('')

  useEffect(() => {
    setFontSize(initialFontSize)
  }, [initialFontSize])

  useEffect(() => {
    setWordWrap(initialWordWrap)
  }, [initialWordWrap])

  useEffect(() => {
    setMinimap(initialMinimap)
  }, [initialMinimap])

  const languageMeta = useMemo(() => {
    if (languageId) {
      const meta = getLanguage(languageId)
      return meta.label
    }
    return language
  }, [language, languageId])

  const handleEditorMount = useCallback(
    (editor, monaco) => {
      editorRef.current = editor
      if (onMount) {
        onMount(editor, monaco)
      }
    },
    [onMount],
  )

  const handleCopy = useCallback(async () => {
    try {
      const currentValue = editorRef.current?.getValue?.() ?? value ?? ''
      await navigator.clipboard.writeText(currentValue)
      setFormatStatus('Copied')
      setTimeout(() => setFormatStatus(''), 1500)
    } catch (error) {
      setFormatStatus('Copy failed')
      setTimeout(() => setFormatStatus(''), 1500)
    }
  }, [value])

  const handleFormat = useCallback(async () => {
    const editor = editorRef.current
    if (!editor) return
    try {
      const action = editor.getAction('editor.action.formatDocument')
      if (action) {
        await action.run()
        setFormatStatus('Formatted')
        setTimeout(() => setFormatStatus(''), 1500)
        return
      }
      setFormatStatus('Formatting unavailable')
      setTimeout(() => setFormatStatus(''), 2000)
    } catch (error) {
      setFormatStatus('Formatting unavailable')
      setTimeout(() => setFormatStatus(''), 2000)
    }
  }, [])

  const handleClear = useCallback(() => {
    if (readOnly) return
    const confirmClear = window.confirm('Clear all code from the editor? This action cannot be undone.')
    if (!confirmClear) return
    onChange?.('')
    if (onClear) {
      onClear()
    }
  }, [onChange, onClear, readOnly])

  const increaseFont = useCallback(() => {
    setFontSize((current) => Math.min(current + 1, 24))
  }, [])

  const decreaseFont = useCallback(() => {
    setFontSize((current) => Math.max(current - 1, 10))
  }, [])

  return (
    <div className={className} style={{ height, display: 'flex', flexDirection: 'column' }}>
      {showToolbar ? (
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-ink-700/80 bg-ink-950/60 px-3 py-2 sm:px-4">
          <div className="flex flex-wrap items-center gap-2">
            <div className="flex items-center gap-1.5 text-xs text-white">
              <FileText className="h-3.5 w-3.5 text-mist-400" aria-hidden="true" />
              <span className="font-medium">{title}</span>
            </div>
            <span className="chip font-mono text-[10px] uppercase tracking-wide">{languageMeta}</span>
            {formatStatus ? (
              <span className="text-[10px] text-emerald-300">{formatStatus}</span>
            ) : null}
          </div>
          <div className="flex flex-wrap items-center gap-1">
            <div className="flex items-center gap-1 rounded-lg border border-ink-700/80 bg-ink-900/80 p-0.5" role="group" aria-label="Font size controls">
              <button
                type="button"
                onClick={decreaseFont}
                disabled={readOnly}
                className="btn btn-ghost px-1.5 py-1 text-[11px]"
                title="Decrease font size"
                aria-label="Decrease font size"
              >
                <Minus className="h-3.5 w-3.5" aria-hidden="true" />
              </button>
              <span className="px-1.5 text-[11px] text-mist-300">{fontSize}px</span>
              <button
                type="button"
                onClick={increaseFont}
                disabled={readOnly}
                className="btn btn-ghost px-1.5 py-1 text-[11px]"
                title="Increase font size"
                aria-label="Increase font size"
              >
                <Plus className="h-3.5 w-3.5" aria-hidden="true" />
              </button>
            </div>
            <button
              type="button"
              onClick={() => setWordWrap((current) => !current)}
              className={`btn btn-ghost px-2 py-1 text-[11px] ${wordWrap ? 'text-white' : 'text-mist-300'}`}
              title="Toggle word wrap"
              aria-label="Toggle word wrap"
              aria-pressed={wordWrap}
            >
              <WrapText className="h-3.5 w-3.5" aria-hidden="true" />
              <span className="hidden sm:inline">Wrap</span>
            </button>
            <button
              type="button"
              onClick={() => setMinimap((current) => !current)}
              className={`btn btn-ghost px-2 py-1 text-[11px] ${minimap ? 'text-white' : 'text-mist-300'}`}
              title="Toggle minimap"
              aria-label="Toggle minimap"
              aria-pressed={minimap}
            >
              <Sidebar className="h-3.5 w-3.5" aria-hidden="true" />
              <span className="hidden sm:inline">Minimap</span>
            </button>
            <button
              type="button"
              onClick={handleFormat}
              disabled={readOnly}
              className="btn btn-ghost px-2 py-1 text-[11px]"
              title="Format document"
              aria-label="Format document"
            >
              <AlignJustify className="h-3.5 w-3.5" aria-hidden="true" />
              <span className="hidden sm:inline">Format</span>
            </button>
            <button
              type="button"
              onClick={handleCopy}
              className="btn btn-ghost px-2 py-1 text-[11px]"
              title="Copy code"
              aria-label="Copy code"
            >
              <Copy className="h-3.5 w-3.5" aria-hidden="true" />
              <span className="hidden sm:inline">Copy</span>
            </button>
            <button
              type="button"
              onClick={handleClear}
              disabled={readOnly || !value}
              className="btn btn-ghost px-2 py-1 text-[11px]"
              title="Clear editor"
              aria-label="Clear editor"
            >
              <RotateCcw className="h-3.5 w-3.5" aria-hidden="true" />
              <span className="hidden sm:inline">Clear</span>
            </button>
          </div>
        </div>
      ) : null}
      <div style={{ flex: 1, minHeight: 0 }}>
        <Editor
          height="100%"
          language={language}
          theme={THEME}
          value={value}
          beforeMount={handleBeforeMount}
          onMount={handleEditorMount}
          onChange={(next) => onChange?.(next ?? '')}
          loading={
            <div className="flex h-full items-center justify-center bg-ink-900">
              <LoadingIndicator label="Loading editor…" description="Preparing the code surface." />
            </div>
          }
          options={{
            readOnly,
            fontSize,
            lineHeight: Math.round(fontSize * 1.6),
            fontFamily:
              "'JetBrains Mono', ui-monospace, SFMono-Regular, Menlo, Consolas, monospace",
            fontLigatures: true,
            minimap: { enabled: minimap },
            scrollBeyondLastLine: false,
            padding: { top: 16, bottom: 16 },
            renderLineHighlight: 'line',
            smoothScrolling: true,
            cursorBlinking: 'smooth',
            automaticLayout: true,
            tabSize: 2,
            wordWrap: wordWrap ? 'on' : 'off',
            scrollbar: { verticalScrollbarSize: 10, horizontalScrollbarSize: 10, useShadows: false },
            overviewRulerBorder: false,
            overviewRulerLanes: 0,
            hideCursorInOverviewRuler: true,
            guides: { indentation: true },
            bracketPairColorization: { enabled: true },
            lineNumbers: 'on',
            folding: true,
            find: {
              addExtraSpaceOnTop: false,
              autoFindInSelection: 'never',
              seedSearchStringFromSelection: 'selection',
            },
          }}
        />
      </div>
    </div>
  )
}
