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
