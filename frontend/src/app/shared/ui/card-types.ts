/** The use cases of the programme (RFP use-case briefing; UC6 is defined in week 18). */
export interface UseCase {
  id: 'UC1' | 'UC2' | 'UC3' | 'UC4' | 'UC5';
  name: string;
  short: string;
  icon: string;
}

export const USE_CASES: UseCase[] = [
  {
    id: 'UC1',
    name: 'Bank Statement Processing',
    short: 'Bank statements',
    icon: 'account_balance',
  },
  {
    id: 'UC2',
    name: 'Transaction Monitoring (AML)',
    short: 'Transaction monitoring',
    icon: 'policy',
  },
  { id: 'UC3', name: 'NAV Statement Validation', short: 'NAV statements', icon: 'show_chart' },
  {
    id: 'UC4',
    name: 'Data Validation & Inconsistency',
    short: 'Data validation',
    icon: 'fact_check',
  },
  { id: 'UC5', name: 'Violation-Triggered Work Cards', short: 'Policy violations', icon: 'report' },
];

export interface CardTypeInfo {
  label: string;
  useCase: UseCase;
}

const LABELS: Record<string, [string, UseCase['id']]> = {
  'uc1.statement-validation': ['Statement validation', 'UC1'],
  'uc1.extraction-exception': ['Extraction exception', 'UC1'],
  'aml.compliance-decision': ['Compliance decision', 'UC2'],
  'aml.mlro-escalation': ['MLRO escalation', 'UC2'],
  'aml.profile-update': ['Client profile update', 'UC2'],
  'aml.gate-exception': ['Gate exception', 'UC2'],
  'aml.kyc-chase': ['KYC document chase', 'UC2'],
  'nav.approval': ['NAV approval', 'UC3'],
  'nav.exception': ['NAV exception', 'UC3'],
  'nav.extraction-exception': ['NAV extraction exception', 'UC3'],
  'uc4.discrepancy': ['Data discrepancy', 'UC4'],
  'uc5.violation': ['Policy violation', 'UC5'],
};

const PREFIX_USE_CASE: Record<string, UseCase['id']> = {
  uc1: 'UC1',
  aml: 'UC2',
  nav: 'UC3',
  uc4: 'UC4',
  uc5: 'UC5',
};

/** Human label and use case for a card type key such as "aml.compliance-decision". */
export function cardTypeInfo(type: string): CardTypeInfo {
  const [label, uc] = LABELS[type] ?? [
    type.split('.').pop()?.replace(/-/g, ' ') ?? type,
    PREFIX_USE_CASE[type.split('.')[0]] ?? 'UC4',
  ];
  return { label, useCase: USE_CASES.find((u) => u.id === uc)! };
}

/** Card types grouped by use case, for filters. */
export function cardTypesByUseCase(): {
  useCase: UseCase;
  types: { key: string; label: string }[];
}[] {
  return USE_CASES.map((useCase) => ({
    useCase,
    types: Object.entries(LABELS)
      .filter(([, [, uc]]) => uc === useCase.id)
      .map(([key, [label]]) => ({ key, label })),
  }));
}
