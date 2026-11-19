import { Injectable, inject } from '@angular/core';
import { Title } from '@angular/platform-browser';
import { RouterStateSnapshot, TitleStrategy } from '@angular/router';

const PRODUCT = 'Work Card Portal';

/** "Inbox · Work Card Portal": every page has a unique title (WCAG 2.4.2). */
@Injectable({ providedIn: 'root' })
export class AmcTitleStrategy extends TitleStrategy {
  private readonly title = inject(Title);

  override updateTitle(snapshot: RouterStateSnapshot): void {
    const page = this.buildTitle(snapshot);
    this.title.setTitle(page ? `${page} · ${PRODUCT}` : PRODUCT);
  }
}
