import { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import Sidebar from './Sidebar';
import TopBar from './TopBar';
import ChatInput from './ChatInput';
import EmptyState from './EmptyState';

// The responder is asked for these five headings. Models wrap them
// inconsistently ("[LEGAL ISSUE]", "**[LEGAL ISSUE]**", "**LEGAL ISSUE**"),
// so match the label and ignore the decoration around it.
const HEADING_RE = /^\s*\**\s*\[?\s*(RELEVANT FACTS|LEGAL ISSUE|COURT REASONING|FINAL DECISION|KEY PRINCIPLE)\s*\]?\s*\**\s*:?\s*$/i;

const stripEmphasis = (line) => line.replace(/\*\*/g, '').trimEnd();

// Split a generated answer into { heading, body } blocks. An answer that
// arrives without recognisable headings is returned as one unlabelled block.
const parseAnswer = (answer) => {
  const sections = [];
  let current = null;

  for (const rawLine of (answer || '').split('\n')) {
    const match = rawLine.match(HEADING_RE);
    if (match) {
      current = { heading: match[1].toUpperCase(), lines: [] };
      sections.push(current);
    } else if (current) {
      current.lines.push(stripEmphasis(rawLine));
    } else if (rawLine.trim()) {
      current = { heading: null, lines: [stripEmphasis(rawLine)] };
      sections.push(current);
    }
  }

  return sections
    .map((s) => ({ heading: s.heading, body: s.lines.join('\n').trim() }))
    .filter((s) => s.heading || s.body);
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
    setIsSearching(true);

    try {
      const res = await fetch('/query/search', {
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
        const detail = await res.text();
        console.error('Search API returned status', res.status, detail);
        setChatHistory((prev) => [
          ...prev,
          { sender: 'ai', text: `The search service returned an error (${res.status}). Please try again.` },
        ]);
        return;
      }

      const data = await res.json();
      const answer = data.top_judgment_answer || '';
      const citations = data.judgments || [];

      if (citations.length === 0) {
        setChatHistory((prev) => [
          ...prev,
          { sender: 'ai', text: 'No judgments in the archive matched your query. Try broader legal terms.' },
        ]);
        return;
      }

      // The pipeline returns this sentinel when the LLM call itself failed;
      // the retrieved judgments are still worth showing.
      if (!answer || answer.startsWith('Error:')) {
        setChatHistory((prev) => [
          ...prev,
          {
            sender: 'ai',
            text: 'I found matching judgments but could not draft an answer from them. The retrieved authorities are listed below.',
            citations,
            latencyMs: data.latency_ms,
          },
        ]);
        return;
      }

      setChatHistory((prev) => [
        ...prev,
        {
          sender: 'ai',
          sections: parseAnswer(answer),
          citations,
          latencyMs: data.latency_ms,
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
        settings: 'Atelier Workgroup Settings',
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
                    <span className="font-display text-base font-semibold text-ash-900">Atelier AI</span>
                    <div className="font-prose text-sm text-ash-900 leading-relaxed">
                      {message.text && (
                        <p className="whitespace-pre-line">{message.text}</p>
                      )}

                      {message.sections?.map((section, sIdx) => (
                        <div key={sIdx} className={sIdx > 0 ? 'mt-5' : ''}>
                          {section.heading && (
                            <h3 className="font-display text-xs font-semibold uppercase tracking-wider text-brand-500 mb-1.5">
                              {section.heading}
                            </h3>
                          )}
                          <p className="whitespace-pre-line">{section.body}</p>
                        </div>
                      ))}

                      {message.citations?.length > 0 && (
                        <div className="mt-6 pt-4 border-t border-ash-200">
                          <h3 className="font-display text-xs font-semibold uppercase tracking-wider text-brand-500 mb-3 flex items-center justify-between">
                            <span>Authorities Retrieved ({message.citations.length})</span>
                            <span className="text-[11px] font-normal text-ash-400">Google Drive Storage</span>
                          </h3>
                          <div className="flex flex-col gap-2.5">
                            {message.citations.map((cite) => (
                              <div
                                key={cite.judgment_id}
                                className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 p-3 rounded-xl border border-ash-200 bg-ash-50/70 hover:bg-ash-50 hover:border-brand-300 transition-all shadow-xs"
                              >
                                <div className="flex items-start gap-2.5 min-w-0">
                                  <div className="w-8 h-8 rounded-lg bg-brand-100 text-brand-700 flex items-center justify-center flex-shrink-0 mt-0.5">
                                    <span className="material-symbols-outlined text-[18px]">picture_as_pdf</span>
                                  </div>
                                  <div className="min-w-0">
                                    <div className="flex items-center gap-2 flex-wrap">
                                      <span className="font-medium text-sm text-ash-900 truncate max-w-xs md:max-w-md" title={cite.filename}>
                                        {cite.filename}
                                      </span>
                                      <span className="px-2 py-0.5 rounded-full text-[10px] font-semibold bg-brand-100 text-brand-800">
                                        Relevance {(cite.similarity_score * 100).toFixed(0)}%
                                      </span>
                                    </div>
                                    {cite.sections_retrieved?.length > 0 && (
                                      <p className="text-xs text-ash-500 mt-0.5 truncate">
                                        Sections: {cite.sections_retrieved.map((s) => s.replace(/_/g, ' ').toLowerCase()).join(', ')}
                                      </p>
                                    )}
                                  </div>
                                </div>
                                <div className="flex items-center gap-2 self-end sm:self-center flex-shrink-0">
                                  <a
                                    href={cite.download_url || `/api/admin/judgments/${cite.judgment_id}/download`}
                                    target="_blank"
                                    rel="noopener noreferrer"
                                    download={cite.filename || "judgment.pdf"}
                                    className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-[#261900] text-white hover:bg-brand-600 transition-all shadow-xs hover:shadow-md hover:-translate-y-0.5 cursor-pointer"
                                    title={`Download ${cite.filename} from Google Drive`}
                                  >
                                    <span className="material-symbols-outlined text-[15px]">download</span>
                                    <span>Download PDF</span>
                                  </a>
                                </div>
                              </div>
                            ))}
                          </div>
                          {message.latencyMs != null && (
                            <p className="mt-3 text-xs text-ash-500">
                              Retrieved in {(message.latencyMs / 1000).toFixed(1)}s
                            </p>
                          )}
                        </div>
                      )}
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
                  <span className="font-display text-base font-semibold text-ash-900">Atelier AI</span>
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
