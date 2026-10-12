import { useNavigate } from 'react-router-dom';
import { useAuth } from '@/auth/AuthContext';
import { IconSearch } from '@/components/NavIcons';

export function AppHeader({ pendingCount = 0 }: { pendingCount?: number }) {
  const { me } = useAuth();
  const navigate = useNavigate();
  const role = (me?.admin_role ?? 'operations_admin').replace(/_/g, ' ');

  return (
    <header className="app-header">
      <div className="header-left">
        <nav className="header-breadcrumb" aria-label="Breadcrumb">
          <span className="breadcrumb-root">/</span>
          <span className="breadcrumb-current">Console</span>
        </nav>
        <div className="ops-status">
          <span className="ops-dot" />
          Operations Active
        </div>
      </div>

      <form
        className="header-search"
        onSubmit={(e) => {
          e.preventDefault();
          const q = new FormData(e.currentTarget).get('q')?.toString().trim();
          if (q) navigate(`/orders?q=${encodeURIComponent(q)}`);
        }}
      >
        <IconSearch className="search-icon-svg" />
        <input name="q" placeholder="Search orders, riders, payouts…" aria-label="Search" />
      </form>

      <div className="header-actions">
        <button
          type="button"
          className="header-payouts"
          onClick={() => navigate('/verification')}
        >
          {pendingCount} pending verifications
        </button>
        <button type="button" className="header-user" onClick={() => navigate('/settings')}>
          <span className="avatar">{me?.full_name?.charAt(0) ?? 'A'}</span>
          <span className="user-meta">
            <strong>{me?.full_name ?? 'Admin'}</strong>
            <small>{role}</small>
          </span>
        </button>
      </div>
    </header>
  );
}
