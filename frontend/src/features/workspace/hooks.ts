import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useOutletContext } from 'react-router';

import { ApiError } from '../../lib/api/errors';
import { ensureCsrf } from '../auth/session';
import type { WorkspaceContext } from './WorkspaceLayout';

export function errorText(error: unknown, fallback: string): string {
  return error instanceof ApiError && error.status < 500 ? error.message : fallback;
}

export function useWorkspace() {
  return useOutletContext<WorkspaceContext>();
}

export function useTenantAction(invalidate: string[]) {
  const client = useQueryClient();
  const { membership } = useWorkspace();
  return useMutation({
    mutationFn: async (call: () => Promise<unknown>) => {
      await ensureCsrf();
      return call();
    },
    onSuccess: () =>
      Promise.all(
        invalidate.map((key) =>
          client.invalidateQueries({ queryKey: [membership.tenant_id, key] }),
        ),
      ),
  });
}
