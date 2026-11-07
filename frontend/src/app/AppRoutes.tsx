import { Suspense, lazy, type ReactNode } from 'react';
import { Navigate, Route, Routes, useLocation } from 'react-router';

import { useTranslation } from 'react-i18next';

import { Alert } from '../components/form';
import { OfflineScreen } from '../components/OfflineScreen';
import {
  AcceptInvitePage,
  ConfirmEmailPage,
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
import { TaxRatesPage } from '../features/accounting/TaxRates';
import { useMe } from '../features/auth/session';
import { PosPage } from '../features/pos/PosPage';
import {
  BalanceSheetPage,
  CashFlowPage,
  ProfitLossPage,
  SalesTaxPage,
} from '../features/reports/pages';
import {
  CustomersPage,
  InvoicesPage,
  OrdersPage as SalesOrdersPage,
  ReceiptsPage as MoneyReceivedPage,
  ReturnsPage,
} from '../features/sales/pages';
import { PayablesPage, ReceivablesPage } from '../features/sales/ledgers';
import {
  AlertsPage,
  InventorySetupPage,
  ProductsPage,
  StockEntriesPage,
  StockOnHandPage,
} from '../features/inventory/pages';
import {
  BillsPage,
  OrdersPage,
  PaymentsPage,
  ReceiptsPage,
  SuppliersPage,
} from '../features/purchasing/pages';
import { AccountPage } from '../features/workspace/AccountPage';
import { BillDesignPage } from '../features/workspace/BillDesignPage';
import { WorkspaceLayout } from '../features/workspace/WorkspaceLayout';
import {
  AuditPage,
  MembersPage,
  NewBusinessPage,
  OverviewPage,
  RolesPage,
} from '../features/workspace/pages';
import type { Me } from '../lib/api/types';
import type { AuthPath } from '../lib/paths';

const DashboardPage = lazy(() => import('../features/reports/Dashboard'));

function RequireUser({ children }: { children: (me: Me) => ReactNode }) {
  const { t } = useTranslation();
  const me = useMe();
  const location = useLocation();
  if (me.fetchStatus === 'paused') return <OfflineScreen />;
  if (me.isPending) return <div className="min-h-[100svh]" />;
  if (me.isError) {
    return (
      <div className="p-8">
        <Alert tone="error">{t('signIn.unavailable')}</Alert>
      </div>
    );
  }
  if (!me.data) {
    const next = encodeURIComponent(location.pathname + location.search);
    return <Navigate to={`/login?next=${next}`} replace />;
  }
  return children(me.data);
}

function GuestOnly({ children }: { children: ReactNode }) {
  const me = useMe();
  if (me.fetchStatus === 'paused') return <OfflineScreen />;
  if (me.isPending) return <div className="min-h-[100svh]" />;
  return me.data ? <Navigate to="/app" replace /> : children;
}

const AUTH_PAGES: Record<AuthPath, ReactNode> = {
  '/login': (
    <GuestOnly>
      <SignInPage />
    </GuestOnly>
  ),
  '/signup': (
    <GuestOnly>
      <SignUpPage />
    </GuestOnly>
  ),
  '/forgot-password': <ForgotPasswordPage />,
  '/reset-password': <ResetPasswordPage />,
  '/verify-email': <VerifyEmailPage />,
  '/confirm-email': <ConfirmEmailPage />,
  '/accept-invite': <AcceptInvitePage />,
  '/new-business': <RequireUser>{(me) => <NewBusinessPage me={me} />}</RequireUser>,
};

export function AuthPage({ path }: { path: AuthPath }) {
  return AUTH_PAGES[path];
}

// Addresses from before the move. Emails already sent still point at these, so they must keep
// working, with their tokens.
const MOVED = [
  ['sign-in', '/login'],
  ['sign-up', '/signup'],
  ['forgot-password', '/forgot-password'],
  ['reset-password', '/reset-password'],
  ['verify-email', '/verify-email'],
  ['accept-invite', '/accept-invite'],
  ['new-business', '/new-business'],
] as const;

function Moved({ to }: { to: string }) {
  const { search } = useLocation();
  return <Navigate to={`${to}${search}`} replace />;
}

function MovedBusiness() {
  const { pathname, search } = useLocation();
  return <Navigate to={`${pathname.replace('/app/t/', '/app/')}${search}`} replace />;
}

export default function AppRoutes() {
  return (
    <Routes>
      {MOVED.map(([from, to]) => (
        <Route key={from} path={from} element={<Moved to={to} />} />
      ))}
      <Route path="t/*" element={<MovedBusiness />} />
      <Route
        path=":business"
        element={<RequireUser>{(me) => <WorkspaceLayout me={me} />}</RequireUser>}
      >
        <Route index element={<OverviewPage />} />
        <Route path="account" element={<AccountPage />} />
        <Route path="members" element={<MembersPage />} />
        <Route path="bill-design" element={<BillDesignPage />} />
        <Route path="roles" element={<RolesPage />} />
        <Route path="audit" element={<AuditPage />} />
        <Route path="accounting/journal" element={<JournalPage />} />
        <Route path="accounting/chart" element={<ChartPage />} />
        <Route path="accounting/trial-balance" element={<TrialBalancePage />} />
        <Route path="accounting/ledger" element={<LedgerPage />} />
        <Route path="accounting/periods" element={<PeriodsPage />} />
        <Route path="accounting/tax-rates" element={<TaxRatesPage />} />
        <Route path="inventory/products" element={<ProductsPage />} />
        <Route path="inventory/entries" element={<StockEntriesPage />} />
        <Route path="inventory/on-hand" element={<StockOnHandPage />} />
        <Route path="inventory/alerts" element={<AlertsPage />} />
        <Route path="inventory/setup" element={<InventorySetupPage />} />
        <Route
          path="reports/dashboard"
          element={
            <Suspense fallback={null}>
              <DashboardPage />
            </Suspense>
          }
        />
        <Route path="reports/profit-loss" element={<ProfitLossPage />} />
        <Route path="reports/balance-sheet" element={<BalanceSheetPage />} />
        <Route path="reports/cash-flow" element={<CashFlowPage />} />
        <Route path="reports/sales-tax" element={<SalesTaxPage />} />
        <Route path="counter" element={<PosPage />} />
        <Route path="sales/invoices" element={<InvoicesPage />} />
        <Route path="sales/receipts" element={<MoneyReceivedPage />} />
        <Route path="sales/customers" element={<CustomersPage />} />
        <Route path="sales/orders" element={<SalesOrdersPage />} />
        <Route path="sales/returns" element={<ReturnsPage />} />
        <Route path="sales/owed-to-me" element={<ReceivablesPage />} />
        <Route path="purchasing/owed-by-me" element={<PayablesPage />} />
        <Route path="purchasing/suppliers" element={<SuppliersPage />} />
        <Route path="purchasing/orders" element={<OrdersPage />} />
        <Route path="purchasing/receipts" element={<ReceiptsPage />} />
        <Route path="purchasing/bills" element={<BillsPage />} />
        <Route path="purchasing/payments" element={<PaymentsPage />} />
      </Route>
      <Route path="*" element={<RequireUser>{(me) => <WorkspaceLayout me={me} />}</RequireUser>} />
    </Routes>
  );
}
