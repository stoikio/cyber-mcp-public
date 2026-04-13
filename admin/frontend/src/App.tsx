import { Navigate, Route, Routes } from 'react-router-dom';
import { useAuthStore } from './store/auth';
import Layout from './components/Layout';
import Login from './pages/Login';
import Dashboard from './pages/Dashboard';
import Policies from './pages/Policies';
import PolicyEdit from './pages/PolicyEdit';
import ApiKeys from './pages/ApiKeys';
import AuditLogs from './pages/AuditLogs';
import OAuthClients from './pages/OAuthClients';
import SlackChannels from './pages/SlackChannels';
import Integrations from './pages/Integrations';
import BlockedEmails from './pages/BlockedEmails';

function RequireAuth({ children }: { children: React.ReactNode }) {
  const token = useAuthStore((s) => s.token);
  if (!token) return <Navigate to="/login" replace />;
  return <>{children}</>;
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route
        element={
          <RequireAuth>
            <Layout />
          </RequireAuth>
        }
      >
        <Route index element={<Dashboard />} />
        <Route path="policies" element={<Policies />} />
        <Route path="policies/new" element={<PolicyEdit />} />
        <Route path="policies/:id" element={<PolicyEdit />} />
        <Route path="blocked-emails" element={<BlockedEmails />} />
        <Route path="api-keys" element={<ApiKeys />} />
        <Route path="slack-channels" element={<SlackChannels />} />
        <Route path="integrations" element={<Integrations />} />
        <Route path="audit" element={<AuditLogs />} />
        <Route path="oauth-clients" element={<OAuthClients />} />
      </Route>
    </Routes>
  );
}
