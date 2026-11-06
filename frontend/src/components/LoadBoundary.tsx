import { Component, type ReactNode } from 'react';

import { OfflineScreen } from './OfflineScreen';

const CHUNK_FAILED = /dynamically imported|importing a module|loading chunk|failed to fetch/i;

// A lazy page that can't be downloaded rejects during render. Without this the screen goes blank.
// Any other error is a real bug and is rethrown rather than blamed on the connection.
export class LoadBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  override state = { failed: false };

  static getDerivedStateFromError(error: unknown): { failed: boolean } {
    const message = error instanceof Error ? error.message : '';
    if (navigator.onLine && !CHUNK_FAILED.test(message)) throw error;
    return { failed: true };
  }

  override render() {
    return this.state.failed ? <OfflineScreen /> : this.props.children;
  }
}
