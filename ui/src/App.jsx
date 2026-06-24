import { useState, useRef, useEffect } from 'react'
import './App.css'

const API = ''

// ─── Small components ──────────────────────────────────────────────────────

function TypingDots() {
  return (
    <div className="bubble bubble-ai bubble-typing">
      <span className="dot" /><span className="dot" /><span className="dot" />
    </div>
  )
}

function Message({ msg }) {
  const isUser = msg.role === 'user'
  return (
    <div className={`msg-row ${isUser ? 'msg-user' : 'msg-ai'}`}>
      {!isUser && <div className="avatar">BZB</div>}
      <div className={`bubble ${isUser ? 'bubble-user' : 'bubble-ai'}`}>
        {msg.content}
      </div>
      {isUser && <div className="avatar avatar-you">You</div>}
    </div>
  )
}

function Chip({ label, onClick, disabled }) {
  return (
    <button className="chip" onClick={() => onClick(label)} disabled={disabled}>
      {label}
    </button>
  )
}

// ─── Session state panel ────────────────────────────────────────────────────

const STATE_LABELS = {
  venue_type:     { label: 'Venue',      icon: '🏢' },
  num_inputs:     { label: 'Sources',    icon: '📥' },
  num_outputs:    { label: 'Displays',   icon: '📺' },
  resolution:     { label: 'Resolution', icon: '🖼' },
  hdr_required:   { label: 'HDR',        icon: '✨' },
  max_distance_m: { label: 'Distance',   icon: '📏' },
  signal_type:    { label: 'Signal',     icon: '🔌' },
  category_hint:  { label: 'Category',   icon: '📦' },
}

function StatePanel({ session }) {
  if (!session) return null
  const entries = Object.entries(STATE_LABELS)
    .map(([key, meta]) => ({ key, ...meta, value: session[key] }))
    .filter(e => e.value !== null && e.value !== undefined)

  if (entries.length === 0) return null

  return (
    <div className="state-panel">
      <div className="state-panel-title">Collected so far</div>
      <div className="state-items">
        {entries.map(e => (
          <div key={e.key} className="state-item">
            <span className="state-icon">{e.icon}</span>
            <span className="state-label">{e.label}</span>
            <span className="state-value">
              {e.key === 'hdr_required' ? (e.value ? 'Yes' : 'No') :
               e.key === 'max_distance_m' ? `${e.value}m` :
               String(e.value).replace(/_/g, ' ')}
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}

// ─── Recommendation card ─────────────────────────────────────────────────────

function ProductTag({ product }) {
  return (
    <div className="product-tag">
      <span className="ptag-id">{product.id}</span>
      <span className="ptag-cat">{product.category.replace(/_/g, ' ')}</span>
      {product.inputs && product.outputs &&
        <span className="ptag-spec">{product.inputs}×{product.outputs}</span>}
      {product.max_distance_m &&
        <span className="ptag-spec">{product.max_distance_m}m</span>}
      {product.resolutions?.[0] &&
        <span className="ptag-res">{product.resolutions.slice(0,2).join(' / ')}</span>}
    </div>
  )
}

function Recommendation({ text, candidates }) {
  const [expanded, setExpanded] = useState(true)

  return (
    <div className="rec-card">
      <div className="rec-header" onClick={() => setExpanded(e => !e)}>
        <span className="rec-badge">✦ Recommendation</span>
        <span className="rec-toggle">{expanded ? '▲' : '▼'}</span>
      </div>

      {expanded && (
        <>
          <div className="rec-body">
            {text.split('\n').map((line, i) => {
              if (!line.trim()) return <div key={i} className="rec-spacer" />
              if (line.startsWith('## ')) return <h3 key={i} className="rec-h2">{line.slice(3)}</h3>
              if (line.startsWith('### ')) return <h4 key={i} className="rec-h3">{line.slice(4)}</h4>
              if (line.startsWith('**') && line.endsWith('**'))
                return <p key={i} className="rec-bold">{line.slice(2,-2)}</p>
              if (line.startsWith('- ') || line.startsWith('• '))
                return <p key={i} className="rec-li">• {line.slice(2)}</p>
              if (/^\d+\./.test(line))
                return <p key={i} className="rec-li">{line}</p>
              return <p key={i} className="rec-p">{line}</p>
            })}
          </div>

          {candidates?.length > 0 && (
            <div className="rec-products">
              <div className="rec-products-label">Matched products</div>
              <div className="rec-products-grid">
                {candidates.map(p => <ProductTag key={p.id} product={p} />)}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  )
}

// ─── Main App ─────────────────────────────────────────────────────────────────

export default function App() {
  const [messages, setMessages]     = useState([])
  const [chips, setChips]           = useState([])
  const [input, setInput]           = useState('')
  const [sessionId, setSessionId]   = useState(null)
  const [session, setSession]       = useState(null)
  const [loading, setLoading]       = useState(false)
  const [recommendation, setRec]    = useState(null)
  const [candidates, setCandidates] = useState([])
  const [started, setStarted]       = useState(false)
  const bottomRef = useRef(null)
  const inputRef  = useRef(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, loading, recommendation])

  async function startChat() {
    setLoading(true)
    setStarted(true)
    try {
      const res  = await fetch(`${API}/chat/start`, { method: 'POST' })
      const data = await res.json()
      setSessionId(data.session?.session_id)
      setSession(data.session)
      setMessages([{ role: 'ai', content: data.message }])
      setChips(data.chips || [])
    } catch {
      setMessages([{ role: 'ai', content: 'Cannot connect to the API server (port 8000). Make sure it is running.' }])
    }
    setLoading(false)
    setTimeout(() => inputRef.current?.focus(), 100)
  }

  async function sendMessage(text) {
    if (!text.trim() || loading) return
    // If session lost, restart
    if (!sessionId) { startChat(); return }
    const msg = text.trim()
    setInput('')
    setChips([])
    setMessages(prev => [...prev, { role: 'user', content: msg }])
    setLoading(true)

    try {
      const res  = await fetch(`${API}/chat/message`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: sessionId, message: msg }),
      })
      const data = await res.json()

      setSession(data.session)
      setMessages(prev => [...prev, { role: 'ai', content: data.message }])
      setChips(data.chips || [])

      if (data.ready_to_search) {
        setRec(data.recommendation)
        setCandidates(data.candidates || [])
        setChips(['Refine search', 'Different category', 'Start over'])
      }
    } catch {
      setMessages(prev => [...prev, { role: 'ai', content: 'Connection error — please try again.' }])
    }

    setLoading(false)
    setTimeout(() => inputRef.current?.focus(), 50)
  }

  function handleChip(label) {
    if (label === 'Start over') {
      setMessages([]); setChips([]); setSessionId(null)
      setSession(null); setRec(null); setCandidates([])
      setStarted(false)
      return
    }
    sendMessage(label)
  }

  // ── Welcome ──
  if (!started) {
    return (
      <div className="app">
        <Header />
        <div className="welcome-wrap">
          <div className="welcome">
            <div className="welcome-icon">📡</div>
            <h2>AV Equipment Advisor</h2>
            <p>
              Describe your installation — display systems, camera setups, signal distribution,
              streaming, or anything AV — and we'll find compatible BZB Gear products
              verified from the actual product manuals.
            </p>
            <button className="start-btn" onClick={startChat}>Start Consultation →</button>
          </div>
        </div>
      </div>
    )
  }

  // ── Chat ──
  return (
    <div className="app">
      <Header />
      <div className="chat-root">

        {/* Left: messages */}
        <div className="chat-col">
          <div className="messages-list">
            {messages.map((m, i) => <Message key={i} msg={m} />)}

            {loading && (
              <div className="msg-row msg-ai">
                <div className="avatar">BZB</div>
                <TypingDots />
              </div>
            )}

            {recommendation && (
              <div className="msg-row msg-ai rec-row">
                <div className="avatar">BZB</div>
                <Recommendation text={recommendation} candidates={candidates} />
              </div>
            )}

            <div ref={bottomRef} />
          </div>

          {/* Input area */}
          <div className="input-zone">
            {chips.length > 0 && (
              <div className="chips-row">
                {chips.map(c => (
                  <Chip key={c} label={c} onClick={handleChip} disabled={loading} />
                ))}
              </div>
            )}
            <div className="input-row">
              <input
                ref={inputRef}
                className="text-input"
                value={input}
                onChange={e => setInput(e.target.value)}
                onKeyDown={e => {
                  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(input) }
                }}
                placeholder="Type your answer or pick a chip above…"
                disabled={loading && !!sessionId}
              />
              <button
                className="send-btn"
                onClick={() => sendMessage(input)}
                disabled={loading || !input.trim()}
              >↑</button>
            </div>
          </div>
        </div>

        {/* Right: state panel */}
        <div className="side-col">
          <StatePanel session={session} />
        </div>

      </div>
    </div>
  )
}

function Header() {
  return (
    <header className="header">
      <span className="logo-bzb">BZB</span>
      <span className="logo-gear">GEAR</span>
      <span className="header-sep">|</span>
      <span className="header-title">AI Equipment Advisor</span>
    </header>
  )
}
