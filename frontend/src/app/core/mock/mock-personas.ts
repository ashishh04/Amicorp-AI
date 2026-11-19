import { Injectable, signal } from '@angular/core';

import { CurrentUser } from '../auth/current-user.store';

export type Persona = CurrentUser & { teams: string[]; calendar: 'HK' | 'EU' };

/**
 * Sample officers, one or more per owning team (LLD: Entra groups AMC-IPA-<role>-<team>).
 * Pick one on the sign-in page, or switch in the user menu, to see what each role and team may do.
 */
export const PERSONAS: Persona[] = [
  {
    id: 'u-chan',
    displayName: 'Chan Tai Man',
    email: 'tm.chan@amicorp.example',
    roles: ['Maker'],
    teams: ['Operations'],
    calendar: 'HK',
    dataScope: ['HK client book'],
  },
  {
    id: 'u-priya',
    displayName: 'Priya Lam',
    email: 'p.lam@amicorp.example',
    roles: ['Checker'],
    teams: ['Operations'],
    calendar: 'HK',
    dataScope: ['HK client book'],
  },
  {
    id: 'u-ahmed',
    displayName: 'Ahmed Khan',
    email: 'a.khan@amicorp.example',
    roles: ['Checker'],
    teams: ['Operations'],
    calendar: 'HK',
    dataScope: ['HK client book'],
  },
  {
    id: 'u-kenneth',
    displayName: 'Kenneth Ho',
    email: 'k.ho@amicorp.example',
    roles: ['Checker'],
    teams: ['Compliance'],
    calendar: 'HK',
    dataScope: ['All AML-monitored clients'],
  },
  {
    id: 'u-ava',
    displayName: 'Ava Leung',
    email: 'a.leung@amicorp.example',
    roles: ['Checker'],
    teams: ['Compliance'],
    calendar: 'HK',
    dataScope: ['All AML-monitored clients'],
  },
  {
    id: 'u-daniel',
    displayName: 'Daniel Wong',
    email: 'd.wong@amicorp.example',
    roles: ['MLRO'],
    teams: ['MLRO office'],
    calendar: 'HK',
    dataScope: ['All AML-monitored clients'],
  },
  {
    id: 'u-sofia',
    displayName: 'Sofia Rossi',
    email: 's.rossi@amicorp.example',
    roles: ['Maker'],
    teams: ['Fund accounting'],
    calendar: 'EU',
    dataScope: ['Administered funds'],
  },
  {
    id: 'u-lars',
    displayName: 'Lars Jansen',
    email: 'l.jansen@amicorp.example',
    roles: ['Checker'],
    teams: ['Fund accounting'],
    calendar: 'EU',
    dataScope: ['Administered funds'],
  },
  {
    id: 'u-meiling',
    displayName: 'Mei Ling Tan',
    email: 'ml.tan@amicorp.example',
    roles: ['Maker', 'Checker'],
    teams: ['Data team'],
    calendar: 'HK',
    dataScope: ['All entities (data stewardship)'],
  },
  {
    id: 'u-ravi',
    displayName: 'Ravi Menon',
    email: 'r.menon@amicorp.example',
    roles: ['Checker'],
    teams: ['Data team'],
    calendar: 'HK',
    dataScope: ['All entities (data stewardship)'],
  },
  {
    id: 'u-grace',
    displayName: 'Grace Lee',
    email: 'g.lee@amicorp.example',
    roles: ['Admin'],
    teams: ['Platform'],
    calendar: 'HK',
    dataScope: [],
  },
  {
    id: 'u-martin',
    displayName: 'Martin de Vries',
    email: 'm.devries@amicorp.example',
    roles: ['Auditor'],
    teams: ['Internal audit'],
    calendar: 'EU',
    dataScope: ['All entities (read only)'],
  },
];

const KEY = 'amc.mock.persona';

/**
 * The user signed in to this browser tab. ?as=u-kenneth on any URL signs in as that demo user
 * (handy for demos and screenshots).
 */
function stored(): string | null {
  try {
    const requested = new URLSearchParams(window.location.search).get('as');
    if (requested && PERSONAS.some((p) => p.id === requested)) {
      sessionStorage.setItem(KEY, requested);
      return requested;
    }
    return sessionStorage.getItem(KEY);
  } catch {
    return null;
  }
}

/**
 * The session when Entra sign-in is off: who the mock API treats as the caller (stands in for
 * the token's oid and roles claim), or null when no one is signed in.
 */
@Injectable({ providedIn: 'root' })
export class MockSession {
  readonly personaId = signal<string | null>(stored());

  persona(): Persona | undefined {
    return PERSONAS.find((p) => p.id === this.personaId());
  }

  use(id: string): void {
    try {
      sessionStorage.setItem(KEY, id);
    } catch {
      // Private mode: the choice lasts until reload.
    }
    this.personaId.set(id);
  }

  clear(): void {
    try {
      sessionStorage.removeItem(KEY);
    } catch {
      // Private mode: nothing was stored.
    }
    this.personaId.set(null);
  }
}
