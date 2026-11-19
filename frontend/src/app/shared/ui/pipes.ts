import { Pipe, PipeTransform, inject } from '@angular/core';

import { Money } from '../../core/api/portal.models';
import { CurrentUserStore } from '../../core/auth/current-user.store';
import { TimeFormat, formatMoney, formatTime, relativeTime, stateLabel } from './format';

/** ISO time in the signed-in user's business-hours zone (HK or EU), or relative ("in 3 h"). */
@Pipe({ name: 'amcTime' })
export class AmcTimePipe implements PipeTransform {
  private readonly user = inject(CurrentUserStore);

  transform(value: string | null | undefined, format: TimeFormat | 'relative' = 'short'): string {
    if (!value) return '—';
    return format === 'relative'
      ? relativeTime(value)
      : formatTime(value, format, this.user.calendar());
  }
}

@Pipe({ name: 'amcMoney' })
export class AmcMoneyPipe implements PipeTransform {
  transform(value: Money | null | undefined, compact = false): string {
    return formatMoney(value, compact);
  }
}

/** Enum-like API values for display: "AWAITING_DECISION" -> "Awaiting decision". */
@Pipe({ name: 'amcLabel' })
export class AmcLabelPipe implements PipeTransform {
  transform(value: string | null | undefined): string {
    return value ? stateLabel(value) : '';
  }
}
