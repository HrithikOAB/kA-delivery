import { NavLink, Outlet, useNavigate } from 'react-router-dom';
import { useAuth } from '@/auth/AuthContext';
import { AppHeader } from '@/components/AppHeader';
import { api } from '@/api/client';
import { useAsync } from '@/hooks/useAsync';
import {
  IconDashboard,
  IconEarnings,
  IconOrders,
  IconPartners,
  IconReports,
  IconSettings,
  IconTestOrders,
  IconTracking,
  IconVerification,
  IconWithdrawals,
} from '@/components/NavIcons';

const NAV = [
  { to: '/', label: 'Dashboard', Icon: IconDashboard, end: true },
  { to: '/orders', label: 'Orders', Icon: IconOrders },
  { to: '/partners', label: 'Delivery Partners', Icon: IconPartners },
  { to: '/operations', label: 'Live Tracking', Icon: IconTracking },
  { to: '/verification', label: 'Partner Verification', Icon: IconVerification },
  { to: '/earnings', label: 'Earnings & Payments', Icon: IconEarnings },
  { to: '/withdrawals', label: 'Withdrawal Requests', Icon: IconWithdrawals },
  { to: '/test-orders', label: 'Test Orders', Icon: IconTestOrders },
  { to: '/reports', label: 'Reports', Icon: IconReports },
  { to: '/settings', label: 'Settings', Icon: IconSettings },
];

export function Layout() {
  const { logout } = useAuth();
  const navigate = useNavigate();
  const { data: overview } = useAsync(() => api.overview(), [], 30000);
  const ordersToday = overview?.metrics.orders_today ?? 0;
  const goalTarget = 120;
  const goalPct = Math.min(100, Math.round((ordersToday / goalTarget) * 100));

  return (
    <div className="app">
      <aside className="sidebar">
        <div className="brand">
          <span className="brand-mark" aria-hidden />
          <span className="brand-text">Khana<span>Delivery</span></span>
        </div>
        <nav className="nav">
          {NAV.map(({ to, label, Icon, end }) => (
            <NavLink key={to} to={to} end={end} className={({ isActive }) => `navlink${isActive ? ' active' : ''}`}>
              <span className="nav-icon"><Icon /></span>
              {label}
            </NavLink>
          ))}
        </nav>
        <div className="sidebar-goal">
          <div className="goal-head">
            <span>Daily Goal</span>
            <strong>{goalPct}%</strong>
          </div>
          <div className="goal-track sidebar-goal-track">
            <div className="goal-fill" style={{ width: `${goalPct}%` }} />
          </div>
          <p className="goal-caption">{ordersToday} / {goalTarget} orders today</p>
        </div>
        <button
          className="btn ghost sm sidebar-logout"
          type="button"
          onClick={() => {
            logout();
            navigate('/login');
          }}
        >
          Sign out
        </button>
      </aside>
      <div className="main">
        <AppHeader pendingCount={overview?.metrics.pending_applications ?? 0} />
        <Outlet />
      </div>
    </div>
  );
}

export function Page({ title, action, children }: { title: string; action?: React.ReactNode; children: React.ReactNode }) {
  return (
    <div className="content">
      <div className="pageheader">
        <h1 className="page-title">{title}</h1>
        {action}
      </div>
      {children}
    </div>
  );
}
