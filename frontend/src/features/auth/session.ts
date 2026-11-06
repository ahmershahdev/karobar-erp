import { useQuery, useQueryClient } from '@tanstack/react-query';

import { api } from '../../lib/api/client';
import { unwrap } from '../../lib/api/errors';
import type { Me, Membership } from '../../lib/api/types';

export const sessionKeys = {
  me: ['me'] as const,
  tenants: ['tenants'] as const,
};

export async function ensureCsrf(): Promise<void> {
  await api.GET('/api/accounts/csrf/');
}

export function useMe() {
  return useQuery({
    queryKey: sessionKeys.me,
    queryFn: async (): Promise<Me | null> => (await unwrap(api.GET('/api/accounts/session/'))).user,
    staleTime: 60_000,
  });
}

export function useMemberships(enabled = true) {
  return useQuery({
    queryKey: sessionKeys.tenants,
    queryFn: async () => (await unwrap(api.GET('/api/tenants/'))) as Membership[],
    enabled,
  });
}

export function useSignOut() {
  const client = useQueryClient();
  return async () => {
    await ensureCsrf();
    await api.POST('/api/accounts/logout/');
    client.clear();
  };
}
