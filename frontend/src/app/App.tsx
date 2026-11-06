import { Suspense, lazy, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Outlet, Route, Routes } from 'react-router';

import { ConnectionNotice } from '../components/ConnectionNotice';
import { Footer } from '../components/Footer';
import { Header } from '../components/Header';
import { LoadBoundary } from '../components/LoadBoundary';
import { OfflineScreen } from '../components/OfflineScreen';
import { PageTransition } from '../components/PageTransition';
import { Preloader } from '../components/Preloader';
import { ScrollTopButton } from '../components/ScrollTopButton';
import { AUTH_PATHS } from '../lib/paths';
import HomePage from '../pages/HomePage';

const ModulesPage = lazy(() => import('../pages/ModulesPage'));
const SecurityPage = lazy(() => import('../pages/SecurityPage'));
const NotFoundPage = lazy(() => import('../pages/NotFoundPage'));
const AppRoutes = lazy(() => import('./AppRoutes'));
const AuthPage = lazy(() => import('./AppRoutes').then((module) => ({ default: module.AuthPage })));

function PublicLayout() {
  return (
    <>
      <Header />
      <main id="main">
        <Outlet />
      </main>
      <Footer />
      <ScrollTopButton />
    </>
  );
}

export function App() {
  const { t } = useTranslation();
  // Opened with no connection: the service worker supplied this shell, but no page can load.
  const [startedOffline] = useState(() => !navigator.onLine);
  if (startedOffline) return <OfflineScreen />;
  return (
    <div className="relative isolate">
      <a
        href="#main"
        className="fixed start-4 top-4 z-[100] -translate-y-24 rounded-full bg-ink px-4 py-2 text-canvas focus:translate-y-0"
      >
        {t('nav.skip')}
      </a>
      <Preloader />
      <ConnectionNotice />
      <PageTransition>
        {(location) => (
          <LoadBoundary>
            <Suspense fallback={<div className="min-h-[100svh]" />}>
              <Routes location={location}>
                <Route element={<PublicLayout />}>
                  <Route path="/" element={<HomePage />} />
                  <Route path="/modules" element={<ModulesPage />} />
                  <Route path="/security" element={<SecurityPage />} />
                  <Route path="*" element={<NotFoundPage />} />
                </Route>
                {AUTH_PATHS.map((path) => (
                  <Route key={path} path={path} element={<AuthPage path={path} />} />
                ))}
                <Route path="/app/*" element={<AppRoutes />} />
              </Routes>
            </Suspense>
          </LoadBoundary>
        )}
      </PageTransition>
    </div>
  );
}
