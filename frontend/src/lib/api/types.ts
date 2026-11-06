import type { components } from './schema';

type Schemas = components['schemas'];

export type Me = Schemas['Me'];
export type Membership = Omit<Schemas['Membership'], 'permissions'> & {
  permissions: Record<string, string[]>;
};
export type Member = Schemas['Member'];
export type Role = Omit<Schemas['Role'], 'permissions'> & { permissions: Record<string, string[]> };
export type Invitation = Schemas['Invitation'];
export type AuditEvent = Schemas['AuditEvent'];
export type Account = Schemas['Account'];
export type JournalEntry = Schemas['JournalEntry'];
export type JournalLine = Schemas['JournalLine'];
export type FiscalYear = Schemas['FiscalYear'];
export type TrialBalance = Schemas['TrialBalance'];
export type Ledger = Schemas['Ledger'];
export type Product = Schemas['Product'];
export type Unit = Schemas['Unit'];
export type Warehouse = Schemas['Warehouse'];
export type Category = Schemas['Category'];
export type StockEntry = Schemas['StockEntry'];
export type StockLevel = Schemas['StockLevel'];
export type Supplier = Schemas['Supplier'];
export type PurchaseOrder = Schemas['PurchaseOrder'];
export type GoodsReceipt = Schemas['GoodsReceipt'];
export type Bill = Schemas['Bill'];
export type SupplierPayment = Schemas['SupplierPayment'];
export type Customer = Schemas['Customer'];
export type SalesOrder = Schemas['SalesOrder'];
export type Invoice = Schemas['Invoice'];
export type CustomerReceipt = Schemas['CustomerReceipt'];
export type CreditNote = Schemas['CreditNote'];

export const MODULES: Record<string, readonly string[]> = {
  members: ['view', 'create', 'update', 'delete'],
  roles: ['view', 'create', 'update', 'delete'],
  audit: ['view'],
  accounting: ['view', 'create', 'update', 'delete', 'post'],
  inventory: ['view', 'create', 'update', 'delete', 'post'],
  purchasing: ['view', 'create', 'update', 'delete', 'post'],
  sales: ['view', 'create', 'update', 'delete', 'post'],
  pos: ['view', 'create', 'update', 'delete', 'post'],
  hr: ['view', 'create', 'update', 'delete', 'post'],
  payroll: ['view', 'create', 'update', 'delete', 'post'],
  reports: ['view'],
};

export function can(membership: Membership | undefined, module: string, action: string): boolean {
  if (!membership) return false;
  return membership.is_owner || (membership.permissions[module] ?? []).includes(action);
}
