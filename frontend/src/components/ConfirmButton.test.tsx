import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { ConfirmButton } from './ConfirmButton';

beforeEach(() => {
  HTMLDialogElement.prototype.showModal = function showModal(this: HTMLDialogElement) {
    this.setAttribute('open', '');
  };
  HTMLDialogElement.prototype.close = function close(this: HTMLDialogElement) {
    this.removeAttribute('open');
  };
});

afterEach(cleanup);

function open(onConfirm: () => void, message?: string) {
  render(
    <ConfirmButton onConfirm={onConfirm} {...(message ? { message } : {})}>
      Remove
    </ConfirmButton>,
  );
  const first = screen.getAllByText('Remove')[0];
  if (!first) throw new Error('no button');
  fireEvent.click(first);
}

describe('a delete button', () => {
  it('deletes nothing on the first click', () => {
    const onConfirm = vi.fn();
    open(onConfirm);
    expect(onConfirm).not.toHaveBeenCalled();
    expect(document.querySelector('dialog')?.hasAttribute('open')).toBe(true);
  });

  it('deletes nothing when cancelled', () => {
    const onConfirm = vi.fn();
    open(onConfirm);
    fireEvent.click(screen.getByText('workspace.cancel'));
    expect(onConfirm).not.toHaveBeenCalled();
    expect(document.querySelector('dialog')?.hasAttribute('open')).toBe(false);
  });

  it('deletes once when confirmed', () => {
    const onConfirm = vi.fn();
    open(onConfirm);
    const confirm = screen.getAllByText('Remove')[1];
    if (!confirm) throw new Error('no confirm button');
    fireEvent.click(confirm);
    expect(onConfirm).toHaveBeenCalledTimes(1);
    expect(document.querySelector('dialog')?.hasAttribute('open')).toBe(false);
  });

  it('shows a specific warning when given one', () => {
    open(vi.fn(), 'They lose access');
    expect(screen.getByText('They lose access')).toBeTruthy();
  });
});
