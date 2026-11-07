import { useId, useRef, type ComponentProps } from 'react';
import { useTranslation } from 'react-i18next';

import { Button } from './form';

/** A delete button that asks first. Cancel takes the focus, so a stray Enter deletes nothing. */
export function ConfirmButton({
  onConfirm,
  message,
  children,
  ...props
}: { onConfirm: () => void; message?: string } & Omit<
  ComponentProps<typeof Button>,
  'onClick' | 'variant'
>) {
  const { t } = useTranslation();
  const dialog = useRef<HTMLDialogElement>(null);
  const title = useId();
  return (
    <>
      <Button variant="danger" {...props} onClick={() => dialog.current?.showModal()}>
        {children}
      </Button>
      <dialog
        ref={dialog}
        aria-labelledby={title}
        className="m-auto w-[min(24rem,calc(100vw-2rem))] rounded-2xl border border-line bg-canvas p-6 text-start text-ink shadow-[var(--shadow-float)] backdrop:bg-ink/40"
      >
        <h2 id={title} className="text-lg">
          {t('confirm.title')}
        </h2>
        <p className="mt-2 text-sm text-muted">{message ?? t('confirm.body')}</p>
        <div className="mt-6 flex flex-wrap justify-end gap-3">
          <Button variant="ghost" autoFocus onClick={() => dialog.current?.close()}>
            {t('workspace.cancel')}
          </Button>
          <Button
            variant="danger"
            onClick={() => {
              dialog.current?.close();
              onConfirm();
            }}
          >
            {children}
          </Button>
        </div>
      </dialog>
    </>
  );
}
