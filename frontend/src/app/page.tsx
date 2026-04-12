'use client'

import { useState, useRef, useEffect } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { Send, Loader2, Trash2, Wrench } from 'lucide-react'

// API URL - use Railway backend in production
const API_URL = process.env.NEXT_PUBLIC_API_URL || 'https://prox-challenge-production-a6f9.up.railway.app'

interface Message {
  role: 'user' | 'assistant'
  content: string
}

interface SuggestedQuestion {
  category: string
  questions: string[]
}

// Component to render message content with embedded diagrams
function MessageContent({ content }: { content: string }) {
  // Parse content to extract diagrams and text
  const parts: { type: 'text' | 'diagram'; content: string }[] = []

  // Split by [DIAGRAM] and [/DIAGRAM] tags
  const diagramRegex = /\[DIAGRAM\]([\s\S]*?)\[\/DIAGRAM\]/g
  let lastIndex = 0
  let match

  while ((match = diagramRegex.exec(content)) !== null) {
    // Add text before the diagram
    if (match.index > lastIndex) {
      const textBefore = content.slice(lastIndex, match.index).trim()
      if (textBefore) {
        parts.push({ type: 'text', content: textBefore })
      }
    }
    // Add the diagram
    parts.push({ type: 'diagram', content: match[1].trim() })
    lastIndex = match.index + match[0].length
  }

  // Add remaining text after last diagram
  if (lastIndex < content.length) {
    const remainingText = content.slice(lastIndex).trim()
    if (remainingText) {
      parts.push({ type: 'text', content: remainingText })
    }
  }

  // If no diagrams found, just render as markdown
  if (parts.length === 0) {
    return (
      <div className="prose prose-sm max-w-none">
        <ReactMarkdown remarkPlugins={[remarkGfm]}>
          {content || '...'}
        </ReactMarkdown>
      </div>
    )
  }

  return (
    <div className="space-y-4">
      {parts.map((part, idx) => {
        if (part.type === 'diagram') {
          return (
            <div
              key={idx}
              className="bg-gray-50 rounded-lg p-4 border-2 border-orange-200 flex justify-center"
              dangerouslySetInnerHTML={{ __html: part.content }}
            />
          )
        } else {
          return (
            <div key={idx} className="prose prose-sm max-w-none">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>
                {part.content}
              </ReactMarkdown>
            </div>
          )
        }
      })}
    </div>
  )
}

export default function Home() {
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [status, setStatus] = useState<any>(null)
  const [suggestions, setSuggestions] = useState<SuggestedQuestion[]>([])
  const messagesEndRef = useRef<HTMLDivElement>(null)

  // Fetch status and suggestions on mount
  useEffect(() => {
    fetch(`${API_URL}/api/status`)
      .then(res => res.json())
      .then(setStatus)
      .catch(console.error)

    fetch(`${API_URL}/api/suggested-questions`)
      .then(res => res.json())
      .then(data => setSuggestions(data.questions || []))
      .catch(console.error)
  }, [])

  // Scroll to bottom on new messages
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const sendMessage = async (text: string) => {
    if (!text.trim() || isLoading) return

    const userMessage: Message = { role: 'user', content: text }
    setMessages(prev => [...prev, userMessage])
    setInput('')
    setIsLoading(true)

    try {
      const response = await fetch(`${API_URL}/api/chat/stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: text }),
      })

      const reader = response.body?.getReader()
      const decoder = new TextDecoder()
      let assistantContent = ''

      setMessages(prev => [...prev, { role: 'assistant', content: '' }])

      while (reader) {
        const { done, value } = await reader.read()
        if (done) break

        const chunk = decoder.decode(value)
        const lines = chunk.split('\n')

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            const data = line.slice(6)
            if (data === '[DONE]') continue

            try {
              const parsed = JSON.parse(data)
              if (parsed.type === 'text') {
                assistantContent += parsed.content
                setMessages(prev => {
                  const newMessages = [...prev]
                  newMessages[newMessages.length - 1] = {
                    role: 'assistant',
                    content: assistantContent,
                  }
                  return newMessages
                })
              }
            } catch (e) {
              // Ignore parse errors
            }
          }
        }
      }
    } catch (error) {
      console.error('Error:', error)
      setMessages(prev => [
        ...prev,
        {
          role: 'assistant',
          content: 'Sorry, I encountered an error. Please make sure the backend server is running and your API key is configured.',
        },
      ])
    } finally {
      setIsLoading(false)
    }
  }

  const clearChat = async () => {
    setMessages([])
    await fetch(`${API_URL}/api/clear-history`, { method: 'POST' })
  }

  return (
    <main className="flex min-h-screen flex-col bg-gray-50">
      {/* Header */}
      <header className="bg-orange-600 text-white p-4 shadow-lg">
        <div className="max-w-4xl mx-auto flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Wrench className="w-8 h-8" />
            <div>
              <h1 className="text-xl font-bold">Vulcan OmniPro 220 Assistant</h1>
              <p className="text-sm text-orange-100">AI-powered welding support</p>
            </div>
          </div>
          <div className="flex items-center gap-4">
            {status?.agent_ready ? (
              <span className="text-sm bg-green-500 px-2 py-1 rounded">Online</span>
            ) : (
              <span className="text-sm bg-red-500 px-2 py-1 rounded">Offline</span>
            )}
            <button
              onClick={clearChat}
              className="p-2 hover:bg-orange-700 rounded-full transition-colors"
              title="Clear chat"
            >
              <Trash2 className="w-5 h-5" />
            </button>
          </div>
        </div>
      </header>

      {/* Chat area */}
      <div className="flex-1 overflow-y-auto p-4 max-w-4xl mx-auto w-full">
        {messages.length === 0 ? (
          <div className="space-y-6">
            <div className="text-center py-8">
              <h2 className="text-2xl font-bold text-gray-800 mb-2">
                Welcome to the Vulcan OmniPro 220 Assistant
              </h2>
              <p className="text-gray-600">
                Ask me anything about your welding machine - setup, settings, troubleshooting, and more.
              </p>
            </div>

            {/* Suggested questions */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {suggestions.map((category, idx) => (
                <div key={idx} className="bg-white rounded-lg shadow p-4">
                  <h3 className="font-semibold text-orange-600 mb-2">{category.category}</h3>
                  <ul className="space-y-2">
                    {category.questions.slice(0, 3).map((q, qIdx) => (
                      <li key={qIdx}>
                        <button
                          onClick={() => sendMessage(q)}
                          className="text-left text-sm text-gray-700 hover:text-orange-600 hover:underline"
                        >
                          {q}
                        </button>
                      </li>
                    ))}
                  </ul>
                </div>
              ))}
            </div>
          </div>
        ) : (
          <div className="space-y-4">
            {messages.map((msg, idx) => (
              <div
                key={idx}
                className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
              >
                <div
                  className={`max-w-[85%] rounded-lg p-4 ${
                    msg.role === 'user'
                      ? 'bg-orange-600 text-white'
                      : 'bg-white shadow border'
                  }`}
                >
                  {msg.role === 'assistant' ? (
                    <MessageContent content={msg.content || '...'} />
                  ) : (
                    <p>{msg.content}</p>
                  )}
                </div>
              </div>
            ))}
            <div ref={messagesEndRef} />
          </div>
        )}
      </div>

      {/* Input area */}
      <div className="border-t bg-white p-4">
        <div className="max-w-4xl mx-auto">
          <form
            onSubmit={(e) => {
              e.preventDefault()
              sendMessage(input)
            }}
            className="flex gap-2"
          >
            <input
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Ask about your Vulcan OmniPro 220..."
              className="flex-1 border rounded-lg px-4 py-2 focus:outline-none focus:ring-2 focus:ring-orange-500"
              disabled={isLoading}
            />
            <button
              type="submit"
              disabled={isLoading || !input.trim()}
              className="bg-orange-600 text-white px-4 py-2 rounded-lg hover:bg-orange-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              {isLoading ? (
                <Loader2 className="w-5 h-5 animate-spin" />
              ) : (
                <Send className="w-5 h-5" />
              )}
            </button>
          </form>
        </div>
      </div>
    </main>
  )
}
