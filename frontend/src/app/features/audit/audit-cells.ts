import { Component, computed, inject, signal } from '@angular/core';
import { Params, RouterLink } from '@angular/router';
import { ICellRendererAngularComp } from 'ag-grid-angular';
import { ICellRendererParams } from 'ag-grid-community';

import { AuditEvent } from '../../core/api/portal.models';
import { CurrentUserStore } from '../../core/auth/current-user.store';
import { AppRole } from '../../core/auth/roles';
import { AvatarComponent } from '../../shared/ui';

/** Actor with a small avatar; automation actors get the system avatar. */
@Component({
  selector: 'amc-audit-actor-cell',
  imports: [AvatarComponent],
  template: `
    <span class="amc-cell-center">
      <amc-avatar [name]="name()" [size]="22" />
      <span class="amc-truncate">{{ name() }}</span>
    </span>
  `,
})
export class AuditActorCellComponent implements ICellRendererAngularComp {
  protected readonly name = signal('');

  agInit(params: ICellRendererParams<AuditEvent>): void {
    this.name.set(params.data?.actor ?? '');
  }

  refresh(params: ICellRendererParams<AuditEvent>): boolean {
    this.agInit(params);
    return true;
  }
}

const ENTITY: Record<string, { label: string; roles: AppRole[] }> = {
  card: { label: 'Card', roles: ['Maker', 'Checker', 'MLRO', 'Auditor'] },
  statement: { label: 'Statement', roles: ['Maker', 'Checker', 'Auditor'] },
  ruleset: { label: 'Ruleset', roles: ['Admin', 'Checker', 'MLRO'] },
  transaction: { label: 'Transaction', roles: [] },
  scan: { label: 'Scan', roles: [] },
};

/**
 * The entity and its ID. Cards, statements and rulesets link to their page when the user's
 * roles open it (the routes' guards); other IDs are plain text.
 */
@Component({
  selector: 'amc-audit-entity-cell',
  imports: [RouterLink],
  template: `
    @if (event(); as e) {
      <span class="amc-cell-center">
        <span class="kind">{{ kind() }}</span>
        @if (link(); as l) {
          <a class="amc-mono" [routerLink]="l.commands" [queryParams]="l.query">{{ e.entityId }}</a>
        } @else {
          <span class="amc-mono">{{ e.entityId }}</span>
        }
      </span>
    }
  `,
  styles: `
    .kind {
      color: var(--amc-muted);
    }
  `,
})
export class AuditEntityCellComponent implements ICellRendererAngularComp {
  private readonly user = inject(CurrentUserStore);
  protected readonly event = signal<AuditEvent | null>(null);

  protected readonly kind = computed(() => {
    const e = this.event();
    return e ? (ENTITY[e.entity]?.label ?? e.entity) : '';
  });

  protected readonly link = computed<{ commands: unknown[]; query: Params | null } | null>(() => {
    const e = this.event();
    const def = e && ENTITY[e.entity];
    if (!e || !def?.roles.length || !this.user.hasAnyRole(def.roles)) return null;
    switch (e.entity) {
      case 'card':
        return { commands: ['/cards', e.entityId], query: null };
      case 'statement':
        return { commands: ['/statements', e.entityId], query: null };
      case 'ruleset':
        return { commands: ['/admin/rulesets'], query: { key: e.entityId } };
      default:
        return null;
    }
  });

  agInit(params: ICellRendererParams<AuditEvent>): void {
    this.event.set(params.data ?? null);
  }

  refresh(params: ICellRendererParams<AuditEvent>): boolean {
    this.agInit(params);
    return true;
  }
}
