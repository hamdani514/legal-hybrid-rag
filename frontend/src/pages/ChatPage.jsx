import { useEffect, useState, useRef, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import axios from 'axios';
import ChatSidebar from '../components/ChatSidebar';
import './ChatPage.css';

const API = '';

export default function ChatPage() {
  const { slug } = useParams();
  const navigate = useNavigate();
  const isNewChat = !slug;

  const [messages, setMessages] = useState([]);
  const [chatTitle, setChatTitle] = useState('New Chat');
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(!isNewChat);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState('');
  const messagesEndRef = useRef(null);

  // ✅ Unmount safety — prevents state updates on unmounted component
  const isMountedRef = useRef(true);
  useEffect(() => {
    isMountedRef.current = true;
    return () => {
      isMountedRef.current = false;
    };
  }, []);

  const token = localStorage.getItem('token') || localStorage.getItem('authToken');
  const authHeader = token ? { Authorization: `Bearer ${token}` } : {};

  // Auto-scroll to bottom of messages
  useEffect(() => {
    if (messagesEndRef.current) {
      messagesEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [messages, sending]);

  // ============================================================
  // HYDRATE EXISTING CHAT
  // ============================================================
  useEffect(() => {
    if (isNewChat) {
      setMessages([]);
      setChatTitle('New Chat');
      setLoading(false);
      setError('');
      return;
    }

    const controller = new AbortController();

    (async () => {
      setLoading(true);
      setError('');
      try {
        const res = await axios.get(`${API}/api/chats/${slug}`, {
          headers: authHeader,
          signal: controller.signal,
        });
        if (!isMountedRef.current) return;
        setMessages(res.data.messages || []);
        setChatTitle(res.data.title || 'Chat');
      } catch (err) {
        if (axios.isCancel(err)) return;
        if (!isMountedRef.current) return;
        if (err.response?.status === 404) {
          setError("Chat not found or you don't have access.");
        } else {
          setError('Failed to load chat.');
        }
      } finally {
        if (isMountedRef.current) setLoading(false);
      }
    })();

    return () => controller.abort();
  }, [slug, isNewChat]);

  // ============================================================
  // SEND MESSAGE
  // ============================================================
  const handleSend = useCallback(async () => {
    const text = input.trim();
    if (!text || sending) return;

    if (!token) {
      navigate('/login');
      return;
    }

    setInput('');
    setSending(true);

    // Optimistically add user message
    setMessages((prev) => [...prev, { role: 'user', content: text }]);

    try {
      if (isNewChat) {
        // =====================================================
        // FIRST MESSAGE → backend creates chat + slug
        // =====================================================
        const res = await axios.post(
          `${API}/api/chats`,
          { firstMessage: text },
          { headers: authHeader }
        );

        if (!isMountedRef.current) return;

        // ✅ Silent URL transition — replace (not push)
        navigate(`/chat/${res.data.slug}`, { replace: true });

        // Add assistant message
        setMessages((prev) => [
          ...prev,
          {
            role: 'assistant',
            content: res.data.answer,
            sources: res.data.sources,
          },
        ]);
        setChatTitle(res.data.title);
      } else {
        // =====================================================
        // SUBSEQUENT MESSAGE — append to existing chat
        // =====================================================

        // 1. Save user message
        await axios.post(
          `${API}/api/chats/${slug}/messages`,
          { role: 'user', content: text },
          { headers: authHeader }
        );

        // 2. Run RAG
        const ragRes = await axios.post(
          `${API}/api/query`,
          { query: text, slug },
          { headers: authHeader }
        );

        if (!isMountedRef.current) return;

        // 3. Show + save assistant message
        setMessages((prev) => [
          ...prev,
          {
            role: 'assistant',
            content: ragRes.data.answer,
            sources: ragRes.data.sources,
          },
        ]);

        await axios.post(
          `${API}/api/chats/${slug}/messages`,
          {
            role: 'assistant',
            content: ragRes.data.answer,
            sources: ragRes.data.sources,
          },
          { headers: authHeader }
        );
      }
    } catch (err) {
      console.error("Chat send error:", err);
      if (!isMountedRef.current) return;

      if (err.response?.status === 403) {
        const errorDetail = err.response.data.detail;
        const msgText =
          (typeof errorDetail === 'object' ? errorDetail.message : errorDetail) ||
          'Daily limit reached. Upgrade to Standard for more queries.';
        setMessages((prev) => [
          ...prev,
          {
            role: 'assistant',
            content: msgText,
          },
        ]);
      } else {
        const detail = err.response?.data?.detail;
        const errMsg = typeof detail === 'string' ? detail : (detail?.message || err.message || 'Something went wrong. Try again.');
        setMessages((prev) => [
          ...prev,
          { role: 'assistant', content: `⚠️ ${errMsg}` },
        ]);
      }
    } finally {
      if (isMountedRef.current) setSending(false);
    }
  }, [input, sending, isNewChat, slug, navigate, token]);

  // ============================================================
  // RENDER
  // ============================================================
  return (
    <div className="chat-layout">
      <ChatSidebar activeSlug={slug} />

      <main className="chat-main">
        <header className="chat-header">
          <h2>{chatTitle}</h2>
          {slug && <code className="slug-badge">/{slug}</code>}
        </header>

        {loading && <div className="loading">Loading conversation...</div>}

        {error && (
          <div className="error-state">
            <p>{error}</p>
            <button onClick={() => navigate('/chat/new')}>Start New Chat</button>
          </div>
        )}

        {!loading && !error && (
          <>
            <div className="messages">
              {messages.length === 0 && (
                <div className="empty-state">
                  <h3>Ask Verdict AI</h3>
                  <p>Search Pakistan Supreme Court judgments with verified legal authority.</p>
                  <p className="plan-hint">
                    Free: 1 query/day · Standard: 20 queries/day
                  </p>
                </div>
              )}
              {messages.map((m, i) => (
                <div key={i} className={`message ${m.role}`}>
                  <div className="bubble">{m.content}</div>
                  {m.sources && m.sources.length > 0 && (
                    <div className="sources">
                      {m.sources.map((s, j) => (
                        <span key={j} className="source-chip" title={s.filename || ''}>
                          {s.docId} {s.sectionType ? `· ${s.sectionType}` : ''}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              ))}
              {sending && <div className="typing">Verdict AI is thinking…</div>}
              <div ref={messagesEndRef} />
            </div>

            <div className="input-bar">
              <input
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) =>
                  e.key === 'Enter' && !e.shiftKey && handleSend()
                }
                placeholder="Ask a legal question…"
                disabled={sending}
              />
              <button onClick={handleSend} disabled={sending || !input.trim()}>
                Send
              </button>
            </div>
          </>
        )}
      </main>
    </div>
  );
}
