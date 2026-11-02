import type { ReactNode } from 'react';
import { Navigate, Route, Routes, useLocation } from 'react-router';

import { Alert } from '../components/form';
import {
  AcceptInvitePage,
  ForgotPasswordPage,
  ResetPasswordPage,
  SignInPage,
  SignUpPage,
  VerifyEmailPage,
} from '../features/auth/pages';
import {
  ChartPage,
  JournalPage,
  LedgerPage,
  PeriodsPage,
  TrialBalancePage,
} from '../features/accounting/pages';
import { useMe } from '../features/auth/session';
import { WorkspaceLayout } from '../features/workspace/WorkspaceLayout';
import {
  AuditPage,
  MembersPage,
  NewBusinessPage,
  OverviewPage,
  RolesPage,
} from '../features/workspace/pages';
import type { Me } from '../lib/api/types';

function RequireUser({ children }: { children: (me: Me) => ReactNode }) {
  const me = useMe();
  const location = useLocation();
  if (me.isPending) return <div className="min-h-[100svh]" />;
  if (me.isError) {
    return (
      <div className="p-8">
        <Alert tone="error">The server could not be reached. Try again in a moment.</Alert>
      </div>
    );
  }
  if (!me.data) {
    const next = encodeURIComponent(location.pathname + location.search);
    return <Navigate to={`/app/sign-in?next=${next}`} replace />;
  }
  return children(me.data);
}

function GuestOnly({ children }: { children: ReactNode }) {
  const me = useMe();
  if (me.isPending) return <div className="min-h-[100svh]" />;
  return me.data ? <Navigate to="/app" replace /> : children;
}

export default function AppRoutes() {
  return (
    <Routes>
      <Route
        path="sign-in"
        element={
          <GuestOnly>
            <SignInPage />
          </GuestOnly>
        }
      />
      <Route
        path="sign-up"
        element={
          <GuestOnly>
            <SignUpPage />
          </GuestOnly>
        }
      />
      <Route path="forgot-password" element={<ForgotPasswordPage />} />
      <Route path="reset-password" element={<ResetPasswordPage />} />
      <Route path="verify-email" element={<VerifyEmailPage />} />
      <Route path="accept-invite" element={<AcceptInvitePage />} />
      <Route
        path="new-business"
        element={<RequireUser>{(me) => <NewBusinessPage me={me} />}</RequireUser>}
      />
      <Route
        path="t/:tenantId"
        element={<RequireUser>{(me) => <WorkspaceLayout me={me} />}</RequireUser>}
      >
        <Route index element={<OverviewPage />} />
        <Route path="members" element={<MembersPage />} />
        <Route path="roles" element={<RolesPage />} />
        <Route path="audit" element={<AuditPage />} />
        <Route path="accounting/journal" element={<JournalPage />} />
        <Route path="accounting/chart" element={<ChartPage />} />
        <Route path="accounting/trial-balance" element={<TrialBalancePage />} />
        <Route path="accounting/ledger" element={<LedgerPage />} />
        <Route path="accounting/periods" element={<PeriodsPage />} />
      </Route>
      <Route path="*" element={<RequireUser>{(me) => <WorkspaceLayout me={me} />}</RequireUser>} />
    </Routes>
  );
}
