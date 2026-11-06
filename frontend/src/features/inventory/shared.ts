import { useQuery } from '@tanstack/react-query';

import { api } from '../../lib/api/client';
import { unwrap } from '../../lib/api/errors';
import { useWorkspace } from '../workspace/hooks';

export function formatQuantity(value: string, locale: string | undefined): string {
  return new Intl.NumberFormat(locale, { maximumFractionDigits: 4 }).format(Number(value));
}

export function useList<T>(key: string, load: () => Promise<T>) {
  const { membership } = useWorkspace();
  return useQuery({ queryKey: [membership.tenant_id, key], queryFn: load });
}

export function useUnits() {
  return useList('units', () => unwrap(api.GET('/api/inventory/units/')));
}

export function useWarehouses() {
  return useList('warehouses', () => unwrap(api.GET('/api/inventory/warehouses/')));
}
