import { Component, inject } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import {
  MAT_DIALOG_DATA,
  MatDialog,
  MatDialogActions,
  MatDialogClose,
  MatDialogContent,
  MatDialogTitle,
} from '@angular/material/dialog';
import { firstValueFrom } from 'rxjs';

export interface ConfirmData {
  title: string;
  message: string;
  confirm: string;
  cancel?: string;
  danger?: boolean;
}

/** A yes/no question before something that cannot be undone. */
@Component({
  selector: 'amc-confirm-dialog',
  imports: [MatButtonModule, MatDialogActions, MatDialogClose, MatDialogContent, MatDialogTitle],
  template: `
    <h2 mat-dialog-title>{{ data.title }}</h2>
    <mat-dialog-content>
      <p>{{ data.message }}</p>
    </mat-dialog-content>
    <mat-dialog-actions align="end">
      <button mat-button [mat-dialog-close]="false">{{ data.cancel ?? 'Cancel' }}</button>
      <button
        mat-flat-button
        [class.amc-btn-danger]="data.danger"
        [mat-dialog-close]="true"
        cdkFocusInitial
      >
        {{ data.confirm }}
      </button>
    </mat-dialog-actions>
  `,
  styles: `
    p {
      max-width: 440px;
    }
  `,
})
export class ConfirmDialogComponent {
  protected readonly data = inject<ConfirmData>(MAT_DIALOG_DATA);
}

/** Opens the confirm dialog and resolves to true when the person confirms. */
export async function confirm(dialog: MatDialog, data: ConfirmData): Promise<boolean> {
  const ref = dialog.open<ConfirmDialogComponent, ConfirmData, boolean>(ConfirmDialogComponent, {
    data,
    width: '480px',
    maxWidth: 'calc(100vw - 32px)',
  });
  return (await firstValueFrom(ref.afterClosed())) === true;
}
