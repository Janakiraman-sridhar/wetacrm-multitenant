import { Navigate, Route, Routes } from "react-router-dom";

import { PageSpinner } from "@/components/ui";
import { useAuth } from "@/context/AuthContext";
import { AppLayout } from "@/layouts/AppLayout";
import CalendarPage from "@/pages/CalendarPage";
import Companies from "@/pages/Companies";
import Contacts from "@/pages/Contacts";
import Dashboard from "@/pages/Dashboard";
import Deals from "@/pages/Deals";
import ForgotPassword from "@/pages/ForgotPassword";
import Invoices from "@/pages/Invoices";
import Leads from "@/pages/Leads";
import Loans from "@/pages/Loans";
import Login from "@/pages/Login";
import ResetPassword from "@/pages/ResetPassword";
import Pipeline from "@/pages/Pipeline";
import Policies from "@/pages/Policies";
import PosterStudio from "@/pages/PosterStudio";
import Products from "@/pages/Products";
import Projects from "@/pages/Projects";
import Quotations from "@/pages/Quotations";
import Reports from "@/pages/Reports";
import SettingsPage from "@/pages/SettingsPage";
import Support from "@/pages/Support";
import Tasks from "@/pages/Tasks";
import { PlatformLayout } from "@/platform/PlatformLayout";
import TenantDetail from "@/platform/TenantDetail";
import Tenants from "@/platform/Tenants";
import TemplateEditor from "@/platform/TemplateEditor";
import Templates from "@/platform/Templates";

function Protected({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth();
  if (loading) return <PageSpinner />;
  if (!user) return <Navigate to="/login" replace />;
  return <>{children}</>;
}

/**
 * The Super Admin console. A platform admin has no tenant of their own, so the CRM
 * routes have nothing to show them — they are sent here instead. There is no way in
 * to a client's workspace: the console manages a tenant from the outside.
 */
function PlatformOnly({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth();
  if (loading) return <PageSpinner />;
  if (!user) return <Navigate to="/login" replace />;
  if (!user.is_platform_admin) return <Navigate to="/" replace />;
  return <>{children}</>;
}

/** Keeps a platform admin out of the tenant CRM. The API refuses them too. */
function TenantOnly({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth();
  if (loading) return <PageSpinner />;
  if (!user) return <Navigate to="/login" replace />;
  if (user.is_platform_admin) return <Navigate to="/platform" replace />;
  return <>{children}</>;
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/forgot-password" element={<ForgotPassword />} />
      <Route path="/reset-password" element={<ResetPassword />} />

      <Route
        path="/platform"
        element={
          <PlatformOnly>
            <PlatformLayout />
          </PlatformOnly>
        }
      >
        <Route index element={<Tenants />} />
        <Route path="tenants/:tenantId" element={<TenantDetail />} />
        <Route path="templates" element={<Templates />} />
        <Route path="templates/:templateKey" element={<TemplateEditor />} />
      </Route>

      <Route
        path="/"
        element={
          <Protected>
            <TenantOnly>
              <AppLayout />
            </TenantOnly>
          </Protected>
        }
      >
        <Route index element={<Dashboard />} />
        <Route path="companies" element={<Companies />} />
        <Route path="contacts" element={<Contacts />} />
        <Route path="leads" element={<Leads />} />
        <Route path="deals" element={<Deals />} />
        <Route path="policies" element={<Policies />} />
        <Route path="poster" element={<PosterStudio />} />
        <Route path="loans" element={<Loans />} />
        <Route path="pipeline" element={<Pipeline />} />
        <Route path="calendar" element={<CalendarPage />} />
        <Route path="tasks" element={<Tasks />} />
        <Route path="projects" element={<Projects />} />
        <Route path="products" element={<Products />} />
        <Route path="quotations" element={<Quotations />} />
        <Route path="invoices" element={<Invoices />} />
        <Route path="support" element={<Support />} />
        <Route path="reports" element={<Reports />} />
        <Route path="settings" element={<SettingsPage />} />
      </Route>

      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
