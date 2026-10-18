import { useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import axios from 'axios';

const API = '';

export default function ChatSidebar({ activeSlug }) {
  const [chats, setChats] = useState([]);
  const navigate = useNavigate();
  const token = localStorage.getItem('token') || localStorage.getItem('authToken');

  const [currentUser, setCurrentUser] = useState(() => {
    try {
      const stored = localStorage.getItem('currentUser');
      return stored ? JSON.parse(stored) : null;
    } catch {
      return null;
    }
  });

  const handleLogout = () => {
    localStorage.removeItem('token');
    localStorage.removeItem('authToken');
    localStorage.removeItem('currentUser');
    setCurrentUser(null);
    navigate('/login');
  };

  const loadChats = async () => {
    if (!token) return;
    try {
      const res = await axios.get(`${API}/api/chats`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      setChats(res.data || []);
    } catch (err) {
      console.error('Load chats failed', err);
    }
  };

  useEffect(() => {
    loadChats();
  }, [activeSlug]);

  const handleNewChat = () => {
    navigate('/chat/new');
  };

  const handleDelete = async (e, slugToDelete) => {
    e.preventDefault();
    e.stopPropagation();
    if (!window.confirm('Delete this chat?')) return;

    try {
      await axios.delete(`${API}/api/chats/${slugToDelete}`, {
        headers: { Authorization: `Bearer ${token}` },
      });

      // If deleting the active chat → redirect to /chat/new
      if (slugToDelete === activeSlug) {
        navigate('/chat/new', { replace: true });
      }
      setChats(prev => prev.filter(c => c.slug !== slugToDelete));
    } catch (err) {
      console.error('Delete failed', err);
    }
  };

  return (
    <aside className="sidebar">
      <div className="sidebar-header">
        <Link to="/" className="brand-link">
          <span className="brand-icon">⚖️</span>
          <span className="brand-name">Verdict<strong>AI</strong></span>
        </Link>
      </div>

      <button className="new-chat-btn" onClick={handleNewChat}>
        <span className="btn-plus">+</span>
        <span>New Chat</span>
      </button>

      <div className="chat-list">
        {chats.length === 0 && <p className="empty">No chats yet.</p>}
        {chats.map(chat => (
          <Link
            key={chat.slug}
            to={`/chat/${chat.slug}`}
            className={`chat-item ${chat.slug === activeSlug ? 'active' : ''}`}
          >
            <span className="title" title={chat.title}>{chat.title}</span>
            <button
              type="button"
              className="delete-btn"
              title="Delete chat"
              onClick={(e) => handleDelete(e, chat.slug)}
            >
              ×
            </button>
          </Link>
        ))}
      </div>

      <div className="sidebar-footer">
        {currentUser ? (
          <div className="user-profile-badge">
            <div className="user-info">
              <span className="user-email" title={currentUser.email || currentUser.name}>
                {currentUser.email || currentUser.name || 'User'}
              </span>
              <span className="user-plan-tag">
                {currentUser.plan || 'Free'} Plan
              </span>
            </div>
            <div className="sidebar-footer-actions">
              <Link to="/pricing" className="footer-action-link" title="View Pricing & Plans">
                💎 Upgrade
              </Link>
              <button type="button" onClick={handleLogout} className="logout-btn" title="Sign Out">
                Sign Out
              </button>
            </div>
          </div>
        ) : (
          <Link to="/login" className="login-prompt-btn">
            Sign In
          </Link>
        )}
      </div>
    </aside>
  );
}
