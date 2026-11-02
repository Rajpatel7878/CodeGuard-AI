export const LANGUAGES = [
  { id: 'javascript', label: 'JavaScript', monaco: 'javascript', extension: 'js' },
  { id: 'typescript', label: 'TypeScript', monaco: 'typescript', extension: 'ts' },
  { id: 'python', label: 'Python', monaco: 'python', extension: 'py' },
  { id: 'java', label: 'Java', monaco: 'java', extension: 'java' },
  { id: 'c', label: 'C', monaco: 'c', extension: 'c' },
  { id: 'cpp', label: 'C++', monaco: 'cpp', extension: 'cpp' },
  { id: 'csharp', label: 'C#', monaco: 'csharp', extension: 'cs' },
  { id: 'go', label: 'Go', monaco: 'go', extension: 'go' },
  { id: 'rust', label: 'Rust', monaco: 'rust', extension: 'rs' },
  { id: 'php', label: 'PHP', monaco: 'php', extension: 'php' },
  { id: 'html', label: 'HTML', monaco: 'html', extension: 'html' },
  { id: 'css', label: 'CSS', monaco: 'css', extension: 'css' },
  { id: 'json', label: 'JSON', monaco: 'json', extension: 'json' },
  { id: 'sql', label: 'SQL', monaco: 'sql', extension: 'sql' },
  { id: 'bash', label: 'Bash', monaco: 'shell', extension: 'sh' },
]

export const CODE_FILE_EXTENSIONS = [
  'js',
  'jsx',
  'mjs',
  'cjs',
  'ts',
  'tsx',
  'py',
  'java',
  'c',
  'h',
  'hh',
  'hxx',
  'hpp',
  'cpp',
  'cc',
  'cxx',
  'cs',
  'go',
  'rs',
  'php',
  'html',
  'htm',
  'css',
  'scss',
  'less',
  'json',
  'sql',
  'sh',
  'bash',
  'txt',
]

export function getLanguage(id) {
  return LANGUAGES.find((language) => language.id === id) ?? LANGUAGES[0]
}

/**
 * Maps a file extension to a supported language id, used by the upload control.
 */
export function languageFromFileName(fileName = '') {
  const extension = fileName.split('.').pop()?.toLowerCase()
  if (!extension) return null

  if (extension === 'jsx') return 'javascript'
  if (extension === 'mjs' || extension === 'cjs') return 'javascript'
  if (extension === 'tsx') return 'typescript'
  if (extension === 'htm') return 'html'
  if (extension === 'sh' || extension === 'bash') return 'bash'
  if (extension === 'cc' || extension === 'cxx' || extension === 'cpp') return 'cpp'
  if (extension === 'h' || extension === 'hpp' || extension === 'hh' || extension === 'hxx') return 'cpp'
  if (extension === 'scss' || extension === 'less') return 'css'

  const match = LANGUAGES.find((language) => language.extension === extension)
  return match?.id ?? null
}
