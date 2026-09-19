
const Sidebar = ({ activeTab, setActiveTab, onNewQuery, userEmail }) => {
  const navItems = [
    { id: 'case', label: 'Current Case', icon: 'gavel' },
    { id: 'statutes', label: 'Legal Statutes', icon: 'balance' },
    { id: 'history', label: 'Case History', icon: 'history' },
    { id: 'drafts', label: 'Drafts', icon: 'description' },
    { id: 'saved', label: 'Saved Research', icon: 'bookmarks' },
  ];

  const footerItems = [
    { id: 'settings', label: 'Settings', icon: 'settings' },
    { id: 'support', label: 'Support', icon: 'help_outline' },
  ];

  return (
    <aside className="h-full w-72 fixed left-0 top-0 bg-ash-100 flex flex-col p-6 gap-y-4 z-40 border-r border-ash-200/70">
      <div className="mb-8 px-2">
        <h1 className="font-display text-lg font-semibold text-ash-900">Atelier Research</h1>
        <p className="text-xs font-ui uppercase tracking-widest text-ash-600 mt-1">
          {userEmail ? userEmail.split('@')[0] : 'Senior Counsel'}
        </p>
      </div>

      {/* CTA */}
      <button
        onClick={onNewQuery}
        className="grad-btn flex w-full items-center justify-center gap-2 rounded-xl px-4 py-3 font-ui text-sm font-semibold text-white shadow-glow transition-all duration-300 hover:-translate-y-0.5 hover:shadow-glow-lg active:translate-y-0"
        style={{ animationDuration: '3s' }}
      >
        <span className="material-symbols-outlined">add</span>
        New Research Query
      </button>

      {/* Navigation Tabs */}
      <nav className="mt-4 flex flex-col gap-y-1 flex-1">
        {navItems.map((item) => {
          const isActive = activeTab === item.id;
          return isActive ? (
            <div
              key={item.id}
              className="flex cursor-default items-center gap-3 rounded-xl rounded-l-none border-l-[3px] border-brand-500 bg-white px-4 py-3 font-medium text-ash-900 shadow-soft"
            >
              <span
                className="material-symbols-outlined"
                style={{ fontVariationSettings: "'FILL' 1" }}
              >
                {item.icon}
              </span>
              <span className="font-ui text-sm tracking-wide">{item.label}</span>
            </div>
          ) : (
            <button
              key={item.id}
              onClick={() => setActiveTab(item.id)}
              className="text-left text-ash-600 hover:bg-ash-100 transition-all duration-200 flex items-center gap-3 px-4 py-3 rounded-lg hover:translate-x-1 w-full"
            >
              <span className="material-symbols-outlined">{item.icon}</span>
              <span className="font-ui text-sm tracking-wide">{item.label}</span>
            </button>
          );
        })}
      </nav>

      {/* Footer Tabs */}
      <div className="mt-auto border-t border-ash-200 pt-4 flex flex-col gap-y-1">
        {footerItems.map((item) => {
          const isActive = activeTab === item.id;
          return isActive ? (
            <div
              key={item.id}
              className="flex cursor-default items-center gap-3 rounded-xl rounded-l-none border-l-[3px] border-brand-500 bg-white px-4 py-3 font-medium text-ash-900 shadow-soft"
            >
              <span
                className="material-symbols-outlined"
                style={{ fontVariationSettings: "'FILL' 1" }}
              >
                {item.icon}
              </span>
              <span className="font-ui text-sm tracking-wide">{item.label}</span>
            </div>
          ) : (
            <button
              key={item.id}
              onClick={() => setActiveTab(item.id)}
              className="text-left text-ash-600 hover:bg-ash-100 transition-all duration-200 flex items-center gap-3 px-4 py-2 rounded-lg w-full"
            >
              <span className="material-symbols-outlined">{item.icon}</span>
              <span className="font-ui text-sm tracking-wide">{item.label}</span>
            </button>
          );
        })}
      </div>
    </aside>
  );
};

export default Sidebar;
