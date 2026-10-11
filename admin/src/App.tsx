import { Navigate, Route, Routes } from 'react-router-dom';
import { useAuth } from '@/auth/AuthContext';
import { Layout } from '@/components/Layout';
import { Loading } from '@/ui/kit';
import { Login } from '@/pages/Login';
import { Overview } from '@/pages/Overview';
import { Verification } from '@/pages/Verification';
import { Partners } from '@/pages/Partners';
import { PartnerProfile } from '@/pages/PartnerProfile';
import { PartnerEdit } from '@/pages/PartnerEdit';
import { Operations } from '@/pages/Operations';
import { Orders } from '@/pages/Orders';
import { OrderDetailPage } from '@/pages/OrderDetail';
import { TestOrders } from '@/pages/TestOrders';
import { Placeholder } from '@/pages/Placeholder';
import { Withdrawals } from '@/pages/Withdrawals';
import { WithdrawalDetail } from '@/pages/WithdrawalDetail';
import type { ReactNode } from 'react';

function Protected({ children }: { children: ReactNode }) {
  const { me, loading } = useAuth();
  if (loading) return <Loading label="Starting…" />;
  if (!me) return <Navigate to="/login" replace />;
  return <>{children}</>;
}

export function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route
        element={
          <Protected>
            <Layout />
          </Protected>
        }
      >
        <Route path="/" element={<Overview />} />
        <Route path="/orders" element={<Orders />} />
        <Route path="/orders/:orderId" element={<OrderDetailPage />} />
        <Route path="/partners" element={<Partners />} />
        <Route path="/partners/:riderId/edit" element={<PartnerEdit />} />
        <Route path="/partners/:riderId" element={<PartnerProfile />} />
        <Route path="/operations" element={<Operations />} />
        <Route path="/verification" element={<Verification />} />
        <Route path="/earnings" element={<Placeholder title="Earnings & Payments" subtitle="Partner earnings, commission splits, and settlement history will appear here." />} />
        <Route path="/withdrawals" element={<Withdrawals />} />
        <Route path="/withdrawals/:id" element={<WithdrawalDetail />} />
        <Route path="/test-orders" element={<TestOrders />} />
        <Route path="/reports" element={<Placeholder title="Reports" subtitle="Operational and financial reports are coming soon." />} />
        <Route path="/settings" element={<Placeholder title="Settings" subtitle="Admin preferences and team access controls will be configured here." />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
