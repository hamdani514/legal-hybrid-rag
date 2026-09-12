import React, { useState, useEffect, useRef } from 'react';
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
          <span className="material-symbols-outlined text-tertiary-fixed-dim text-6xl mb-4 select-none">
            {activeTab === 'settings' ? 'settings' : activeTab === 'support' ? 'help_outline' : 'folder_open'}
          </span>
          <h2 className="font-headline text-3xl text-primary-container mb-2">
            {tabTitles[activeTab] || 'Workspace Section'}
          </h2>
          <p className="text-on-surface-variant max-w-md text-sm font-body leading-relaxed">
            This module is being structured for high-stakes integration. Dynamic search results, file ingestion pipelines, and audit trails remain active in the <strong>Current Case</strong> tab.
          </p>
          <button
            onClick={() => setActiveTab('case')}
            className="mt-6 bg-[#0D1C32] text-white px-6 py-2.5 rounded-lg font-body text-xs font-semibold uppercase tracking-wider hover:opacity-90 transition-opacity"
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
                <div className="max-w-[75%] bg-surface-container-high text-primary-container px-6 py-4 rounded-xl border border-outline-variant/10 shadow-sm">
                  <p className="font-body text-sm leading-relaxed whitespace-pre-wrap">{message.text}</p>
                </div>
              ) : (
                <div className="max-w-[85%] flex gap-4">
                  <span className="material-symbols-outlined text-tertiary-fixed-dim text-2xl mt-1 select-none flex-shrink-0">
                    gavel
                  </span>
                  <div className="flex flex-col gap-2">
                    <span className="font-headline text-base font-semibold text-primary-container">Atelier AI</span>
                    <div className="font-body text-sm text-on-surface leading-relaxed">
                      {message.text && (
                        <p className="whitespace-pre-line">{message.text}</p>
                      )}

                      {message.sections?.map((section, sIdx) => (
                        <div key={sIdx} className={sIdx > 0 ? 'mt-5' : ''}>
                          {section.heading && (
                            <h3 className="font-headline text-xs font-semibold uppercase tracking-wider text-tertiary-fixed-dim mb-1.5">
                              {section.heading}
                            </h3>
                          )}
                          <p className="whitespace-pre-line">{section.body}</p>
                        </div>
                      ))}

                      {message.citations?.length > 0 && (
                        <div className="mt-6 pt-4 border-t border-outline-variant/20">
                          <h3 className="font-headline text-xs font-semibold uppercase tracking-wider text-tertiary-fixed-dim mb-3">
                            Authorities Retrieved
                          </h3>
                          <ol className="flex flex-col gap-2.5">
                            {message.citations.map((cite) => (
                              <li key={cite.judgment_id} className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
                                <span className="font-medium text-primary-container">{cite.filename}</span>
                                <span className="text-xs text-on-surface-variant">
                                  relevance {cite.similarity_score.toFixed(3)}
                                </span>
                                {cite.sections_retrieved?.length > 0 && (
                                  <span className="text-xs text-on-surface-variant">
                                    &middot; {cite.sections_retrieved.map((s) => s.replace(/_/g, ' ').toLowerCase()).join(', ')}
                                  </span>
                                )}
                              </li>
                            ))}
                          </ol>
                          {message.latencyMs != null && (
                            <p className="mt-3 text-xs text-on-surface-variant/70">
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
                <span className="material-symbols-outlined text-tertiary-fixed-dim text-2xl mt-1 select-none flex-shrink-0 animate-spin">
                  progress_activity
                </span>
                <div className="flex flex-col gap-2">
                  <span className="font-headline text-base font-semibold text-primary-container">Atelier AI</span>
                  <p className="font-body text-sm text-on-surface-variant italic">
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
    <div className="flex min-h-screen w-full bg-surface text-on-surface">
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
      <div className="fixed top-20 right-20 w-96 h-96 bg-tertiary-fixed/5 rounded-full blur-[120px] pointer-events-none -z-10"></div>
      <div className="fixed -bottom-20 -left-20 w-[500px] h-[500px] bg-primary-container/5 rounded-full blur-[160px] pointer-events-none -z-10"></div>
    </div>
  );
};

export default WelcomeContent;
