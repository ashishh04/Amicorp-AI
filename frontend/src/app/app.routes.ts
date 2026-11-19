import { ResolveFn, Routes } from '@angular/router';

import { authGuard, signedOutGuard } from './core/auth/auth.guard';
import { roleGuard } from './core/auth/role.guard';
import { pendingChangesGuard } from './core/layout/pending-changes.guard';
import { ShellComponent } from './core/layout/shell.component';

const cardTitle: ResolveFn<string> = (route) => `Card ${route.paramMap.get('id')}`;
const statementTitle: ResolveFn<string> = (route) => `Statement ${route.paramMap.get('id')}`;

// Routes and guards from the LLD (Portal Build: Routes and guards), plus the overview page.
// Guards only shape the UI; the API enforces every rule again. The menu is core/layout/nav-items.ts.
export const routes: Routes = [
  // Sign-in pages sit outside the shell. /logout ends the session itself, so the account menu
  // and the idle timeout simply go there.
  {
    path: 'login',
    title: 'Sign in',
    canActivate: [signedOutGuard],
    loadComponent: () => import('./features/auth/login.page'),
  },
  {
    path: 'logout',
    title: 'Signed out',
    loadComponent: () => import('./features/auth/logout.page'),
  },
  // Entra returns here; MSAL then goes back to the page the sign-in started from.
  {
    path: 'auth/callback',
    title: 'Signing in',
    loadComponent: () => import('./features/auth/callback.page'),
  },
  {
    path: '',
    component: ShellComponent,
    canActivate: [authGuard],
    children: [
      { path: '', pathMatch: 'full', redirectTo: 'home' },
      {
        path: 'home',
        title: 'Overview',
        canActivate: [roleGuard('Maker', 'Checker', 'MLRO', 'Admin', 'Auditor')],
        loadComponent: () => import('./features/home/home.page'),
      },
      {
        path: 'inbox',
        title: 'Inbox',
        canActivate: [roleGuard('Maker', 'Checker', 'MLRO')],
        loadComponent: () => import('./features/inbox/inbox.page'),
      },
      {
        path: 'cards/:id',
        title: cardTitle,
        canActivate: [roleGuard('Maker', 'Checker', 'MLRO', 'Auditor')],
        loadComponent: () => import('./features/card-detail/card-detail.page'),
      },
      {
        path: 'statements/:id',
        title: statementTitle,
        canActivate: [roleGuard('Maker', 'Checker', 'Auditor')],
        loadComponent: () => import('./features/validation-workspace/validation-workspace.page'),
      },
      {
        path: 'admin/rulesets',
        title: 'Rulesets',
        canActivate: [roleGuard('Admin', 'Checker', 'MLRO')],
        canDeactivate: [pendingChangesGuard],
        loadComponent: () => import('./features/admin/rulesets/rulesets.page'),
      },
      {
        path: 'admin/settings',
        title: 'Settings',
        canActivate: [roleGuard('Admin')],
        loadComponent: () => import('./features/admin/settings/settings.page'),
      },
      {
        path: 'audit',
        title: 'Audit trail',
        canActivate: [roleGuard('Auditor', 'MLRO')],
        loadComponent: () => import('./features/audit/audit.page'),
      },
      {
        path: 'kpis',
        title: 'Operational KPIs',
        canActivate: [roleGuard('Checker', 'MLRO', 'Admin')],
        loadComponent: () => import('./features/ops-kpis/ops-kpis.page'),
      },
      {
        path: 'forbidden',
        title: 'No access',
        loadComponent: () => import('./core/errors/forbidden.component'),
      },
      { path: '_reload', loadComponent: () => import('./core/layout/reload.component') },
      {
        path: '**',
        title: 'Not found',
        loadComponent: () => import('./core/errors/not-found.component'),
      },
    ],
  },
];
