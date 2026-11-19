import { AppRole } from '../auth/roles';
import { InboxView } from '../api/portal.models';

/** Navigation entries; the shell shows only those the user's roles allow. */
export interface NavItem {
  path: string;
  label: string;
  icon: string;
  roles: AppRole[];
  /** Shows the count of this inbox view as a badge. */
  badge?: InboxView;
  /** Words the global search matches besides the label. */
  keywords?: string;
}

export interface NavGroup {
  label: string;
  items: NavItem[];
}

const EVERYONE: AppRole[] = ['Maker', 'Checker', 'MLRO', 'Admin', 'Auditor'];

// Mirrors the role guards in app.routes.ts (LLD, Portal Build: Routes and guards).
export const NAV_GROUPS: NavGroup[] = [
  {
    label: 'Work',
    items: [
      {
        path: 'home',
        label: 'Overview',
        icon: 'space_dashboard',
        roles: EVERYONE,
        keywords: 'home start',
      },
      {
        path: 'inbox',
        label: 'Inbox',
        icon: 'inbox',
        roles: ['Maker', 'Checker', 'MLRO'],
        badge: 'mine',
        keywords: 'cards queue work',
      },
    ],
  },
  {
    label: 'Insight',
    items: [
      {
        path: 'kpis',
        label: 'Operational KPIs',
        icon: 'insights',
        roles: ['Checker', 'MLRO', 'Admin'],
        keywords: 'dashboard sla metrics',
      },
      {
        path: 'audit',
        label: 'Audit trail',
        icon: 'manage_search',
        roles: ['Auditor', 'MLRO'],
        keywords: 'history log events',
      },
    ],
  },
  {
    label: 'Governance',
    items: [
      {
        path: 'admin/rulesets',
        label: 'Rulesets',
        icon: 'rule',
        roles: ['Admin', 'Checker', 'MLRO'],
        keywords: 'rules gates versions',
      },
      {
        path: 'admin/settings',
        label: 'Settings',
        icon: 'settings',
        roles: ['Admin'],
        keywords: 'card types data scope sla',
      },
    ],
  },
];

export const NAV_ITEMS: NavItem[] = NAV_GROUPS.flatMap((g) => g.items);
