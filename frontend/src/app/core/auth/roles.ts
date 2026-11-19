/**
 * Entra app roles of amc-platform-api assigned to people (LLD, Entra app registrations).
 * The Automation role belongs to n8n and never reaches the portal.
 */
export const APP_ROLES = ['Maker', 'Checker', 'MLRO', 'Admin', 'Auditor'] as const;
export type AppRole = (typeof APP_ROLES)[number];

export function isAppRole(value: string): value is AppRole {
  return (APP_ROLES as readonly string[]).includes(value);
}

/** What each role may do in the portal (LLD, Portal roles: card actions by app role). */
export const ROLE_INFO: Record<AppRole, { summary: string; can: string[] }> = {
  Maker: {
    summary: 'Prepares work for your team',
    can: [
      'Review, correct and approve statement lines, then submit the statement',
      'Add evidence and propose corrections',
      'Return a card to the AI with an instruction',
    ],
  },
  Checker: {
    summary: 'Second pair of eyes for your team',
    can: [
      'Approve or reject the cards you own, unless you prepared them',
      'Delegate a card to another Checker in the team',
      'Return a card to the AI with an instruction',
      'Approve non-AML ruleset versions of your team',
    ],
  },
  MLRO: {
    summary: 'Money Laundering Reporting Officer',
    can: [
      'Decide MLRO escalations and other AML cards',
      'Approve aml.* ruleset versions',
      'Read the AML part of the audit trail',
    ],
  },
  Admin: {
    summary: 'Platform administration under change control',
    can: [
      'Draft ruleset versions',
      'Manage card types, SLAs and data scope',
      'No card decisions, so configuration and approval stay separate',
    ],
  },
  Auditor: {
    summary: 'Read-only oversight',
    can: ['Read cards, decisions and evidence', 'Search the full audit trail'],
  },
};
