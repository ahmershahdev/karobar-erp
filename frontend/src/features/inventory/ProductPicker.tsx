import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { api } from '../../lib/api/client';
import { unwrap } from '../../lib/api/errors';
import type { Product } from '../../lib/api/types';
import { useWorkspace } from '../workspace/hooks';
import { CELL_INPUT } from '../workspace/table';

// Searches as you type and resolves scanned barcodes, so it works the same for 20 products or
// 20,000. A barcode also picks the pack it belongs to (scan a carton, get the carton unit).
export function ProductPicker({
  value,
  onPick,
}: {
  value: Product | undefined;
  onPick: (product: Product, unit: number) => void;
}) {
  const { t } = useTranslation();
  const { membership } = useWorkspace();
  const [term, setTerm] = useState('');
  const [open, setOpen] = useState(false);
  const query = term.trim();
  const results = useQuery({
    queryKey: [membership.tenant_id, 'product-search', query],
    enabled: open && query.length > 0,
    queryFn: () =>
      unwrap(
        api.GET('/api/inventory/products/', {
          params: { query: { q: query, page_size: 8 } as never },
        }),
      ),
  });
  const pick = (product: Product) => {
    // The database compares barcodes without case, so this has to as well, or a pack found by
    // its barcode would fall back to the base unit.
    const code = query.toLowerCase();
    const pack = product.packs?.find((item) => item.barcode?.toLowerCase() === code);
    onPick(product, pack?.unit ?? product.unit);
    setTerm('');
    setOpen(false);
  };
  // Enter after a scan takes the product that owns the barcode, even when another product has
  // the same digits in its name or SKU, or the owner fell outside the first page of results.
  const pickExact = async () => {
    const scanned = await unwrap(
      api.GET('/api/inventory/products/', { params: { query: { barcode: query } as never } }),
    ).catch(() => null);
    const product = scanned?.results[0] ?? results.data?.results[0];
    if (product) pick(product);
  };
  return (
    <div className="relative">
      <input
        aria-label={t('inv.product')}
        placeholder={value ? `${value.sku} ${value.name}` : t('inv.search')}
        className={`${CELL_INPUT} ${value ? 'placeholder:text-ink' : ''}`}
        value={term}
        onFocus={() => setOpen(true)}
        onBlur={() => setTimeout(() => setOpen(false), 150)}
        onChange={(e) => {
          setTerm(e.target.value.slice(0, 80));
          setOpen(true);
        }}
        onKeyDown={(e) => {
          if (e.key === 'Enter' && query) {
            e.preventDefault();
            void pickExact();
          }
        }}
      />
      {open && query && (
        <ul
          className="absolute inset-x-0 top-full z-20 mt-1 max-h-64 overflow-y-auto rounded-xl border border-line bg-raised shadow-xl"
          data-lenis-prevent
        >
          {results.data?.results.length === 0 && (
            <li className="px-3 py-2 text-sm text-muted">{t('workspace.none')}</li>
          )}
          {results.data?.results.map((product) => (
            <li key={product.id}>
              <button
                type="button"
                className="w-full px-3 py-2 text-start text-sm hover:bg-raised"
                onMouseDown={(e) => e.preventDefault()}
                onClick={() => pick(product)}
              >
                <span className="font-mono text-xs text-gold">{product.sku}</span> {product.name}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
