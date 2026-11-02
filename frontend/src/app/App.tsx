import { Suspense, lazy } from 'react';
import { useTranslation } from 'react-i18next';
import { Outlet, Route, Routes } from 'react-router';

import { Footer } from '../components/Footer';
import { Header } from '../components/Header';
import { PageTransition } from '../components/PageTransition';
import HomePage from '../pages/HomePage';

const ModulesPage = lazy(() => import('../pages/ModulesPage'));
const SecurityPage = lazy(() => import('../pages/SecurityPage'));
const NotFoundPage = lazy(() => import('../pages/NotFoundPage'));
const AppRoutes = lazy(() => import('./AppRoutes'));

function PublicLayout() {
  return (
    <>
      <Header />
      <Outlet />
      <Footer />
    </>
  );
}

export function App() {
  const { t } = useTranslation();
  return (
    <div className="grain">
      <a
        href="#main"
        className="fixed start-4 top-4 z-[70] -translate-y-24 rounded-full bg-cream px-4 py-2 text-black focus:translate-y-0"
      >
        {t('nav.skip')}
      </a>
      <div id="main">
        <PageTransition>
          {(location) => (
            <Suspense fallback={<div className="min-h-[100svh]" />}>
              <Routes location={location}>
                <Route element={<PublicLayout />}>
                  <Route path="/" element={<HomePage />} />
                  <Route path="/modules" element={<ModulesPage />} />
                  <Route path="/security" element={<SecurityPage />} />
                  <Route path="*" element={<NotFoundPage />} />
                </Route>
                <Route path="/app/*" element={<AppRoutes />} />
              </Routes>
            </Suspense>
          )}
        </PageTransition>
      </div>
    </div>
  );
}
