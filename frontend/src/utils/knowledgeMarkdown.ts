import MarkdownIt from 'markdown-it'

const markdown = new MarkdownIt({ html: false, linkify: false, breaks: true })

// Knowledge chunks are read-only content; links and images are displayed as text.
markdown.renderer.rules.link_open = () => ''
markdown.renderer.rules.link_close = () => ''
markdown.renderer.rules.image = (tokens, index) => markdown.utils.escapeHtml(tokens[index]?.content || '')
markdown.renderer.rules.table_open = () => '<div class="knowledge-table-scroll"><table>'
markdown.renderer.rules.table_close = () => '</table></div>'
markdown.renderer.rules.text = (tokens, index, _options, env) => {
  const value = tokens[index]?.content || ''
  const query = String(env?.highlight || '').trim()
  if (!query) return markdown.utils.escapeHtml(value)
  const needle = query.toLocaleLowerCase()
  const lower = value.toLocaleLowerCase()
  let output = ''
  let start = 0
  while (start < value.length) {
    const match = lower.indexOf(needle, start)
    if (match < 0) return output + markdown.utils.escapeHtml(value.slice(start))
    output += markdown.utils.escapeHtml(value.slice(start, match))
    output += `<mark>${markdown.utils.escapeHtml(value.slice(match, match + needle.length))}</mark>`
    start = match + needle.length
  }
  return output
}

export function renderKnowledgeMarkdown(value: string, query = ''): string {
  return markdown.render(value, { highlight: query })
}

export function knowledgeListSnippet(value: string): string {
  const tokens = markdown.parse(value, {})
  const hasTable = tokens.some(token => token.type === 'table_open')
  const pieces: string[] = []
  let inTable = false
  for (const token of tokens) {
    if (token.type === 'table_open') inTable = true
    else if (token.type === 'table_close') inTable = false
    else if (!inTable && token.type === 'inline') {
      pieces.push(...(token.children || [])
        .filter(child => ['text', 'code_inline', 'image'].includes(child.type))
        .map(child => child.content))
    }
  }
  const text = pieces.join(' ').replace(/\s+/g, ' ').trim()
  if (hasTable) return [text.slice(0, 120), '包含表格内容，点击查看'].filter(Boolean).join(' · ')
  return text || value.replace(/\s+/g, ' ').slice(0, 180)
}
