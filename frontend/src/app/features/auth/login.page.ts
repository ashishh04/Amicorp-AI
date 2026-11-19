import {
  Component,
  ElementRef,
  Injector,
  afterNextRender,
  computed,
  inject,
  input,
  signal,
  viewChild,
  viewChildren,
} from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';

import { AuthService } from '../../core/auth/auth.service';
import { LocalAccount } from '../../core/auth/local-sign-in';
import { APP_ROLES, AppRole } from '../../core/auth/roles';
import { PERSONAS } from '../../core/mock/mock-personas';
import { AvatarComponent } from '../../shared/ui';
import { AuthFrameComponent } from './auth-frame.component';

interface Account {
  id: string;
  name: string;
  meta: string;
}

type Person = Pick<LocalAccount, 'id' | 'displayName' | 'roles' | 'teams'>;

const mainRole = (p: Person) => APP_ROLES.indexOf(p.roles[p.roles.length - 1] as AppRole);

/** People to pick from, in the order of the LLD roles table. */
function toAccounts(people: Person[]): Account[] {
  return [...people]
    .sort((a, b) => mainRole(a) - mainRole(b))
    .map((p) => ({
      id: p.id,
      name: p.displayName,
      meta: `${p.roles.join(' + ')} · ${p.teams.join(', ')}`,
    }));
}

/**
 * Sign-in page. With Entra ID it sends the user to Microsoft, where MFA and conditional access
 * apply; the portal never sees a password. Without Entra a list of sample users stands in for
 * Microsoft's account picker: the mock's, or the local Platform API's sample officers.
 */
@Component({
  selector: 'amc-login',
  imports: [
    AuthFrameComponent,
    AvatarComponent,
    MatButtonModule,
    MatIconModule,
    MatProgressSpinnerModule,
  ],
  templateUrl: './login.page.html',
  styleUrl: './login.page.scss',
})
export default class LoginPage {
  /** Bound from the query string: where to go afterwards, and why the user is here. */
  readonly returnUrl = input<string>();
  readonly reason = input<string>();

  protected readonly auth = inject(AuthService);
  private readonly injector = inject(Injector);
  protected readonly accounts = signal<Account[]>(
    this.auth.mode === 'mock' ? toAccounts(PERSONAS) : [],
  );

  /** Showing the sample users (mock and local sign-in). */
  protected readonly picking = signal(false);
  /**
   * 'sso' while the redirect to Microsoft starts, 'accounts' while the local sample officers
   * load, or the sample user being signed in.
   */
  protected readonly busy = signal<string | null>(null);

  // The same words in every mode: clients see this page in demos too.
  protected readonly lead = computed(() =>
    this.picking() ? 'Select your account to continue.' : 'Use your Amicorp work account.',
  );

  private readonly signInButton = viewChild<unknown, ElementRef<HTMLElement>>('signIn', {
    read: ElementRef,
  });
  private readonly accountButtons = viewChildren<ElementRef<HTMLElement>>('account');

  protected start(): void {
    if (this.auth.mode === 'mock') {
      this.showAccounts(true);
      return;
    }
    if (this.auth.mode === 'local') {
      this.busy.set('accounts');
      void this.auth.localAccounts().then(
        (people) => {
          // Ready before the list shows, so its buttons are enabled from the first frame.
          this.busy.set(null);
          this.accounts.set(toAccounts(people));
          this.showAccounts(true);
        },
        () => this.busy.set(null), // AuthService shows the problem on this page
      );
      return;
    }
    this.busy.set('sso');
    // Entra leaves the page; the button only comes back if the redirect could not start.
    void this.auth.signIn(this.returnUrl()).finally(() => this.busy.set(null));
  }

  protected pick(id: string): void {
    this.busy.set(id);
    void this.auth.signIn(this.returnUrl(), id).finally(() => this.busy.set(null));
  }

  /** Swaps the card's content and keeps keyboard focus on it. */
  protected showAccounts(show: boolean): void {
    this.picking.set(show);
    afterNextRender(
      () =>
        (show ? this.accountButtons()[0] : this.signInButton())?.nativeElement.focus({
          preventScroll: true,
        }),
      { injector: this.injector },
    );
  }
}
