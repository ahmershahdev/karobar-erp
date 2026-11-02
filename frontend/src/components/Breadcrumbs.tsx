import { useTranslation } from 'react-i18next';
import { Link } from 'react-router';

interface Crumb {
  label: string;
  to: string;
}

export function Breadcrumbs({ trail }: { trail: Crumb[] }) {
  const { t } = useTranslation();
  return (
    <nav aria-label={t('nav.breadcrumb')}>
      <ol className="label flex flex-wrap items-center gap-3">
        {trail.map((crumb, index) => {
          const last = index === trail.length - 1;
          return (
            <li key={crumb.to} className="flex items-center gap-3">
              {last ? (
                <span aria-current="page" className="!text-ink">
                  {crumb.label}
                </span>
              ) : (
                <>
                  <Link to={crumb.to} className="transition-colors hover:!text-gold">
                    {crumb.label}
                  </Link>
                  <span aria-hidden="true" className="text-gold/60">
                    /
                  </span>
                </>
              )}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
