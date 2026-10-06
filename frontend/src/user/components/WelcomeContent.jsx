import { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import Sidebar from './Sidebar';
import TopBar from './TopBar';
import ChatInput from './ChatInput';
import EmptyState from './EmptyState';
import ResultsPanel from './ResultsPanel';
import apiFetch, { clearToken } from '../../lib/api';
import { ANSWER_STATUS, answerStatusOf } from '../lib/answerFormat';

// The backend's MAX_QUERY_CHARS; checked here too so a long description gets
// a clear message instead of a validation error.
const MAX_QUERY_CHARS = 4000;

/** The `detail` of an error response, when it is a plain string. */
const errorDetail = async (res) => {
  try {
    const body = await res.json();
    return typeof body?.detail === 'string' ? body.detail : '';
  } catch {
    return '';
  }
};

const WelcomeContent = () => {
  const navigate = useNavigate();
  const currentUser = JSON.parse(localStorage.getItem('currentUser') || 'null');
  
  const [activeTab, setActiveTab] = useState('case');
  const [chatHistory, setChatHistory] = useState([]);
  const [isSearching, setIsSearching] = useState(false);
  const chatEndRef = useRef(null);

  // Authenticate user
  useEffect(() => {
    if (!currentUser) {
      navigate('/login');
    }
  }, [currentUser, navigate]);

  // Scroll to bottom on new message
  useEffect(() => {
    if (chatEndRef.current) {
      chatEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [chatHistory, isSearching]);

  if (!currentUser) {
    return null;
  }

  const userEmail = currentUser?.email || currentUser?.user?.email || '';

  const handleLogout = () => {
    clearToken();
    localStorage.removeItem('currentUser');
    navigate('/login');
  };

  const handleNewQuery = () => {
    setChatHistory([]);
    setActiveTab('case');
  };

  const handleSendQuery = async (queryText) => {
    if (!queryText.trim()) return;

    // Add user message
    const userMessage = { sender: 'user', text: queryText };
    setChatHistory((prev) => [...prev, userMessage]);

    if (queryText.length > MAX_QUERY_CHARS) {
      setChatHistory((prev) => [
        ...prev,
        {
          sender: 'ai',
          text: `Your description is ${queryText.length} characters long; please shorten it to ${MAX_QUERY_CHARS} or fewer. The facts, what each side claims and what the courts decided are what matter most.`,
        },
      ]);
      return;
    }

    setIsSearching(true);

    try {
      const res = await apiFetch('/query/search', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          query: queryText,
          top_k_judgments: 3,
          top_k_sections: 3,
          mode: 'answer',
        }),
      });

      if (!res.ok) {
        const detail = await errorDetail(res);
        console.error('Search API returned status', res.status, detail);
        // 429 is a rate limit (per user, or the shared service): say "busy",
        // with the server's own explanation when it gave one.
        const text =
          res.status === 429
            ? detail || 'The service is busy right now. Please try again in a minute.'
            : res.status === 401
              ? 'Your session has expired. Please sign in again.'
              : `The search service returned an error (${res.status}). Please try again.`;
        setChatHistory((prev) => [...prev, { sender: 'ai', text }]);
        return;
      }

      const data = await res.json();
      const citations = data.judgments || [];

      // The backend decides whether anything in the archive answers the
      // query. When it says nothing does, that verdict is shown as-is: no
      // judgments, no downloads, no answer. Presenting an unrelated case with
      // a relevance score attached is what this replaced.
      if (data.no_results || citations.length === 0) {
        setChatHistory((prev) => [
          ...prev,
          {
            sender: 'ai',
            noResults: true,
            text:
              data.message ||
              'No relevant case is available in our data centre for this query.',
          },
        ]);
        return;
      }

      // Each result renders its own state (ready / on demand / busy / error)
      // inside the panel. Only when every result failed outright is that worth
      // a sentence up front.
      const allFailed = citations.every((c) => answerStatusOf(c) === ANSWER_STATUS.ERROR);

      setChatHistory((prev) => [
        ...prev,
        {
          sender: 'ai',
          citations,
          // The query as typed: "Analyse this case" and retries send it back
          // to POST /query/answer for that result.
          query: queryText,
          latencyMs: data.latency_ms,
          // Set when a broad query was answered with a category browse.
          notice: data.notice || '',
          text: allFailed
            ? 'I found matching judgments but could not draft an analysis from them. The authorities are listed below.'
            : '',
        },
      ]);
    } catch (error) {
      console.error('Query pipeline error:', error);
      const errorText = `Unable to reach the backend search service. Make sure the FastAPI server is running.`;
      setChatHistory((prev) => [...prev, { sender: 'ai', text: errorText }]);
    } finally {
      setIsSearching(false);
    }
  };

  const handleSelectCard = (prompt) => {
    handleSendQuery(prompt);
  };

  const renderContent = () => {
    if (activeTab !== 'case') {
      // Premium placeholder views for non-chat screens
      const tabTitles = {
        statutes: 'Legal Statutes Database',
        history: 'Case History Logs',
        drafts: 'Drafting Workspace',
        saved: 'Saved Research Briefs',
        settings: 'Verdict AI Workgroup Settings',
        support: 'Technical Support & Helpdesk',
      };

      return (
        <div className="flex-grow flex flex-col items-center justify-center p-12 text-center animate-[fadeIn_0.4s_ease-out]">
          <span className="material-symbols-outlined text-brand-500 text-6xl mb-4 select-none">
            {activeTab === 'settings' ? 'settings' : activeTab === 'support' ? 'help_outline' : 'folder_open'}
          </span>
          <h2 className="font-display text-3xl text-ash-900 mb-2">
            {tabTitles[activeTab] || 'Workspace Section'}
          </h2>
          <p className="text-ash-600 max-w-md text-sm font-prose leading-relaxed">
            This module is being structured for high-stakes integration. Dynamic search results, file ingestion pipelines, and audit trails remain active in the <strong>Current Case</strong> tab.
          </p>
          <button
            onClick={() => setActiveTab('case')}
            className="mt-6 grad-btn rounded-full px-7 py-3 font-ui text-[13px] font-bold text-white shadow-glow transition-all duration-300 hover:-translate-y-0.5 hover:shadow-glow-lg"
          >
            Return to Case Chat
          </button>
        </div>
      );
    }

    if (chatHistory.length === 0) {
      return <EmptyState onSelectCard={handleSelectCard} />;
    }

    return (
      <div className="flex-grow w-full max-w-4xl mx-auto px-8 pt-24 pb-44 overflow-y-auto">
        <div className="flex flex-col gap-6">
          {chatHistory.map((message, index) => (
            <div
              key={index}
              className={`flex ${message.sender === 'user' ? 'justify-end' : 'justify-start'} animate-[fadeIn_0.3s_ease-out]`}
            >
              {message.sender === 'user' ? (
                <div className="max-w-[75%] rounded-2xl rounded-tr-md border border-brand-100 bg-brand-50 px-6 py-4 text-ash-900">
                  <p className="font-prose text-sm leading-relaxed whitespace-pre-wrap">{message.text}</p>
                </div>
              ) : (
                <div className="max-w-[85%] flex gap-4">
                  <span className="material-symbols-outlined text-brand-500 text-2xl mt-1 select-none flex-shrink-0">
                    gavel
                  </span>
                  <div className="flex flex-col gap-2">
                    <span className="font-display text-base font-semibold text-ash-900">Verdict AI</span>
                    <div className="font-prose text-sm text-ash-900 leading-relaxed">
                      <ResultsPanel message={message} />
                    </div>
                  </div>
                </div>
              )}
            </div>
          ))}

          {isSearching && (
            <div className="flex justify-start animate-pulse">
              <div className="max-w-[85%] flex gap-4">
                <span className="material-symbols-outlined text-brand-500 text-2xl mt-1 select-none flex-shrink-0 animate-spin">
                  progress_activity
                </span>
                <div className="flex flex-col gap-2">
                  <span className="font-display text-base font-semibold text-ash-900">Verdict AI</span>
                  <p className="font-prose text-sm text-ash-600 italic">
                    Retrieving matched semantic nodes and precedents...
                  </p>
                </div>
              </div>
            </div>
          )}
          <div ref={chatEndRef} />
        </div>
      </div>
    );
  };

  return (
    <div className="flex min-h-screen w-full bg-white text-ash-900">
      {/* Sidebar Navigation */}
      <Sidebar
        activeTab={activeTab}
        setActiveTab={setActiveTab}
        onNewQuery={handleNewQuery}
        userEmail={userEmail}
      />

      {/* Main Workspace Area */}
      <main className="flex-1 ml-72 flex flex-col min-h-screen relative overflow-hidden">
        {/* Top AppBar */}
        <TopBar onLogout={handleLogout} userEmail={userEmail} />

        {/* Dynamic Content Frame */}
        {renderContent()}

        {/* Floating Input Area (only on Current Case chat tab) */}
        {activeTab === 'case' && (
          <ChatInput onSend={handleSendQuery} loading={isSearching} />
        )}
      </main>

      {/* Ambient Decorative Blurs */}
      <div className="fixed top-20 right-20 w-96 h-96 bg-brand-50 rounded-full blur-[120px] pointer-events-none -z-10"></div>
      <div className="fixed -bottom-20 -left-20 w-[500px] h-[500px] bg-ash-50 rounded-full blur-[160px] pointer-events-none -z-10"></div>
    </div>
  );
};

export default WelcomeContent;
