import {
  AuditEvent,
  CardDetail,
  CardState,
  PersonRef,
  CardType,
  DataScopeGroup,
  LookupEntry,
  Ruleset,
  RulesetVersion,
  StatementHeader,
  StatementLine,
} from '../api/portal.models';

/**
 * Sample data for the mock API. Times are relative to page load so SLAs look live. Names,
 * accounts, amounts and documents are invented; card types, SLAs, escalation roles and gate
 * rulesets follow the LLD (Card type registry, Rules engine).
 */

const h = (hours: number) => new Date(Date.now() + hours * 3_600_000).toISOString();
const LLM = 'deepseek-v4-flash';
const OCR = 'PP-OCRv4 + PP-Structure';

const N8N = { id: 'svc-n8n', name: 'n8n (Automation)' };
const CHAN = { id: 'u-chan', name: 'Chan Tai Man' };
const PRIYA = { id: 'u-priya', name: 'Priya Lam' };
const AHMED = { id: 'u-ahmed', name: 'Ahmed Khan' };
const KENNETH = { id: 'u-kenneth', name: 'Kenneth Ho' };
const AVA = { id: 'u-ava', name: 'Ava Leung' };
const DANIEL = { id: 'u-daniel', name: 'Daniel Wong' };
const SOFIA = { id: 'u-sofia', name: 'Sofia Rossi' };
const LARS = { id: 'u-lars', name: 'Lars Jansen' };
const MEILING = { id: 'u-meiling', name: 'Mei Ling Tan' };
const RAVI = { id: 'u-ravi', name: 'Ravi Menon' };
const GRACE = { id: 'u-grace', name: 'Grace Lee' };

// ---------------------------------------------------------------- card types (LLD registry)

export const CARD_TYPES: CardType[] = [
  {
    type: 'uc1.statement-validation',
    version: 2,
    team: 'Operations',
    severity: 'medium',
    sla: '2 business days',
    escalationRole: 'Operations Lead',
    onApproval:
      'Output files for the core systems, status write-back, post-facto lines to transaction monitoring',
    decidedBy: 'Checker',
  },
  {
    type: 'uc1.extraction-exception',
    version: 1,
    team: 'Operations',
    severity: 'medium',
    sla: '1 business day',
    escalationRole: 'Operations Lead',
    onApproval: 'Reprocess or manual capture',
    decidedBy: 'Checker',
  },
  {
    type: 'aml.compliance-decision',
    version: 3,
    team: 'Compliance',
    severity: 'high',
    sla: '4 business hours',
    escalationRole: 'MLRO',
    onApproval: 'Release the payment hold; CARE audit stamp',
    decidedBy: 'Checker',
  },
  {
    type: 'aml.mlro-escalation',
    version: 2,
    team: 'MLRO office',
    severity: 'critical',
    sla: '4 business hours',
    escalationRole: 'Deputy MLRO',
    onApproval: 'Incident, STR pack, freeze or return of funds',
    decidedBy: 'MLRO',
  },
  {
    type: 'aml.profile-update',
    version: 1,
    team: 'Compliance',
    severity: 'high',
    sla: '1 business day',
    escalationRole: 'MLRO',
    onApproval: 'Profile write-back; re-validate from gate 2',
    decidedBy: 'Checker',
  },
  {
    type: 'aml.gate-exception',
    version: 1,
    team: 'Compliance',
    severity: 'high',
    sla: '2 business hours',
    escalationRole: 'MLRO',
    onApproval: 'Manual gate decision or re-run',
    decidedBy: 'Checker',
  },
  {
    type: 'nav.approval',
    version: 1,
    team: 'Fund accounting',
    severity: 'medium',
    sla: '1 business day',
    escalationRole: 'Head of Fund Accounting',
    onApproval: 'Publish the NAV to Valuefy',
    decidedBy: 'Checker',
  },
  {
    type: 'nav.exception',
    version: 1,
    team: 'Fund accounting',
    severity: 'high',
    sla: '1 business day',
    escalationRole: 'Head of Fund Accounting',
    onApproval: 'Correct, or accept with rationale',
    decidedBy: 'Checker',
  },
  {
    type: 'nav.extraction-exception',
    version: 1,
    team: 'Fund accounting',
    severity: 'medium',
    sla: '1 business day',
    escalationRole: 'Head of Fund Accounting',
    onApproval: 'Reprocess or manual capture',
    decidedBy: 'Checker',
  },
  {
    type: 'uc4.discrepancy',
    version: 2,
    team: 'Data team',
    severity: 'low',
    sla: '5 business days',
    escalationRole: 'Head of Data',
    onApproval: 'Correction written back where approved',
    decidedBy: 'Checker',
  },
  {
    type: 'uc5.violation',
    version: 1,
    team: 'Data team',
    severity: 'by policy',
    sla: 'by policy',
    escalationRole: 'Head of Data',
    onApproval: 'Approved correction written to CARE or 5 Series',
    decidedBy: 'Checker',
  },
];

export const DATA_SCOPE: DataScopeGroup[] = [
  {
    group: 'AMC-IPA-Maker-Operations',
    team: 'Operations',
    role: 'Maker',
    calendar: 'HK',
    members: 6,
    scope: 'HK client book',
  },
  {
    group: 'AMC-IPA-Checker-Operations',
    team: 'Operations',
    role: 'Checker',
    calendar: 'HK',
    members: 3,
    scope: 'HK client book',
  },
  {
    group: 'AMC-IPA-Checker-Compliance',
    team: 'Compliance',
    role: 'Checker',
    calendar: 'HK',
    members: 4,
    scope: 'All AML-monitored clients',
  },
  {
    group: 'AMC-IPA-MLRO',
    team: 'MLRO office',
    role: 'MLRO',
    calendar: 'HK',
    members: 2,
    scope: 'All AML-monitored clients',
  },
  {
    group: 'AMC-IPA-Maker-FundAccounting',
    team: 'Fund accounting',
    role: 'Maker',
    calendar: 'EU',
    members: 5,
    scope: 'Administered funds',
  },
  {
    group: 'AMC-IPA-Checker-FundAccounting',
    team: 'Fund accounting',
    role: 'Checker',
    calendar: 'EU',
    members: 2,
    scope: 'Administered funds',
  },
  {
    group: 'AMC-IPA-Maker-DataTeam',
    team: 'Data team',
    role: 'Maker',
    calendar: 'HK',
    members: 3,
    scope: 'All entities (data stewardship)',
  },
  {
    group: 'AMC-IPA-Checker-DataTeam',
    team: 'Data team',
    role: 'Checker',
    calendar: 'HK',
    members: 2,
    scope: 'All entities (data stewardship)',
  },
  {
    group: 'AMC-IPA-Admin',
    team: 'Platform',
    role: 'Admin',
    calendar: 'HK',
    members: 2,
    scope: 'Configuration only',
  },
  {
    group: 'AMC-IPA-Auditor',
    team: 'Internal audit',
    role: 'Auditor',
    calendar: 'EU',
    members: 3,
    scope: 'All entities (read only)',
  },
];

/** Daily EN-number lookup table (read live from 5 Series in production). */
export const EN_NUMBERS: LookupEntry[] = [
  { code: 'EN-20415', name: 'Lumen Capital SPC' },
  { code: 'EN-20416', name: 'Lumen Capital SPC - Segregated Portfolio 1' },
  { code: 'EN-20417', name: 'Lumen Capital SPC - Segregated Portfolio 2' },
  { code: 'EN-20418', name: 'Lumen Capital SPC - Segregated Portfolio 3' },
  { code: 'EN-31002', name: 'Harbour Trust Ltd' },
  { code: 'EN-31007', name: 'Harbour Trust Ltd - Unit 12A' },
  { code: 'EN-40188', name: 'Seabright Holdings BV' },
  { code: 'EN-55120', name: 'Meridian Growth Fund' },
  { code: 'EN-55121', name: 'Meridian Income Fund' },
  { code: 'EN-61002', name: 'Ardent Fund SPC' },
];

// ---------------------------------------------------------------- rulesets

export type RulesetSeed = Omit<Ruleset, 'versions' | 'approvers' | 'actions'> & {
  versions: Omit<RulesetVersion, 'actions'>[];
};

export function seedRulesets(): RulesetSeed[] {
  const gate1Rules = [
    {
      id: 'G1-01',
      desc: 'Unusual-transaction flag always monitored',
      when: { '==': [{ var: 'unusualFlag' }, true] },
      then: 'monitor',
    },
    {
      id: 'G1-02',
      desc: 'Exclusion list (e.g. internal transfers)',
      when: { inList: ['exclusion', { var: 'counterpartyId' }] },
      then: 'below-threshold',
    },
    {
      id: 'G1-03',
      desc: 'Single payment at or above USD 10,000',
      when: { '>=': [{ var: 'amountUsd' }, 10000] },
      then: 'monitor',
    },
    {
      id: 'G1-04',
      desc: 'Related payments aggregate to USD 10,000 within 7 days',
      when: { '>=': [{ sumWindow: ['amountUsd', 7, 'entityKey'] }, 10000] },
      then: 'monitor',
    },
    {
      id: 'G1-05',
      desc: 'Local country requirement: high-risk beneficiary country',
      when: { '==': [{ countryRisk: [{ var: 'beneficiaryCtry' }] }, 'high'] },
      then: 'monitor',
    },
    { id: 'G1-99', desc: 'Below every threshold', when: true, then: 'below-threshold' },
  ];
  const gate1Draft = [
    ...gate1Rules.slice(0, 5),
    {
      id: 'G1-06',
      desc: 'Structuring: 3 or more payments of USD 9,000-9,999 within 7 days',
      when: { '>=': [{ var: 'nearThresholdCount7d' }, 3] },
      then: 'monitor',
    },
    gate1Rules[5],
  ];

  // Gates 2 and 3 as platform-api seeds them (backend/scripts/seed.py).
  const g2 = {
    profileVerdict: 'match',
    amountUsd: 48000,
    profileMaxAmountUsd: 60000,
    countryInProfile: true,
  };
  const g3 = { screeningHit: false, screeningScore: 0, riskScore: 35, pepFlag: false };

  return [
    {
      key: 'aml.gate1-entry',
      name: 'AML gate 1: entry thresholds',
      owner: 'Compliance',
      useCase: 'UC2',
      description:
        'Decides whether a payment enters AML monitoring at all. Payments below every threshold are filed without a card.',
      outcomes: ['monitor', 'below-threshold'],
      sampleInputs: {
        unusualFlag: false,
        counterpartyId: 'CP-88120',
        amountUsd: 7200,
        amountUsdSum7d: 12850,
        beneficiaryCtry: 'SG',
        nearThresholdCount7d: 0,
      },
      regressionCases: [
        {
          name: 'Large single payment',
          inputs: { amountUsd: 48000, amountUsdSum7d: 48000, beneficiaryCtry: 'HK' },
          expected: 'monitor',
        },
        {
          name: 'Internal transfer is excluded',
          inputs: { counterpartyId: 'CP-00001-INTERNAL', amountUsd: 250000 },
          expected: 'below-threshold',
        },
        {
          name: 'Split payments over 7 days',
          inputs: { amountUsd: 4000, amountUsdSum7d: 11500, beneficiaryCtry: 'HK' },
          expected: 'monitor',
        },
        {
          name: 'High-risk country, small amount',
          inputs: { amountUsd: 900, amountUsdSum7d: 900, beneficiaryCtry: 'IR' },
          expected: 'monitor',
        },
        {
          name: 'Ordinary small payment',
          inputs: { amountUsd: 1200, amountUsdSum7d: 3100, beneficiaryCtry: 'SG' },
          expected: 'below-threshold',
        },
        {
          name: 'Structuring pattern (needs v4)',
          inputs: {
            amountUsd: 9500,
            amountUsdSum7d: 9500,
            beneficiaryCtry: 'HK',
            nearThresholdCount7d: 3,
          },
          expected: 'monitor',
        },
      ],
      versions: [
        {
          version: 4,
          status: 'draft',
          effectiveFrom: null,
          draftedBy: GRACE,
          draftedAt: h(-28),
          approvedBy: null,
          note: 'Adds G1-06 for structuring just below the threshold (Compliance request CR-118).',
          rules: gate1Draft,
        },
        {
          version: 3,
          status: 'approved',
          effectiveFrom: '2026-09-01T00:00:00Z',
          draftedBy: GRACE,
          draftedAt: '2026-08-25T03:00:00Z',
          approvedBy: DANIEL,
          note: 'Adds the local-country requirement G1-05.',
          rules: gate1Rules,
        },
        {
          version: 2,
          status: 'superseded',
          effectiveFrom: '2026-06-15T00:00:00Z',
          draftedBy: GRACE,
          draftedAt: '2026-06-10T03:00:00Z',
          approvedBy: DANIEL,
          note: 'Adds the 7-day aggregation rule.',
          rules: gate1Rules.filter((r) => r.id !== 'G1-05'),
        },
      ],
    },
    {
      key: 'aml.gate2-profile',
      name: 'AML gate 2: client profile',
      owner: 'Compliance',
      useCase: 'UC2',
      description:
        "The model reads the payment against the client's CARE profile. An uncertain reading counts as a mismatch, so a doubt always reaches Compliance.",
      outcomes: ['match', 'mismatch'],
      sampleInputs: { ...g2 },
      regressionCases: [
        { name: 'Fits the profile', inputs: { ...g2 }, expected: 'match' },
        {
          name: 'The model is not sure',
          inputs: { ...g2, profileVerdict: 'uncertain' },
          expected: 'mismatch',
        },
        {
          name: 'The model sees a mismatch',
          inputs: { ...g2, profileVerdict: 'mismatch' },
          expected: 'mismatch',
        },
        {
          name: "Above the profile's largest payment",
          inputs: { ...g2, amountUsd: 75000 },
          expected: 'mismatch',
        },
        {
          name: 'Country not in the profile',
          inputs: { ...g2, countryInProfile: false },
          expected: 'mismatch',
        },
      ],
      versions: [
        {
          version: 1,
          status: 'approved',
          effectiveFrom: '2026-09-01T00:00:00Z',
          draftedBy: GRACE,
          draftedAt: '2026-08-25T04:00:00Z',
          approvedBy: DANIEL,
          note: 'First version: the model reads, the rules decide.',
          rules: [
            {
              id: 'G2-01',
              desc: 'The model could not tell: treated as a mismatch',
              when: { '==': [{ var: 'profileVerdict' }, 'uncertain'] },
              then: 'mismatch',
            },
            {
              id: 'G2-02',
              desc: 'The model found the payment outside the profile',
              when: { '==': [{ var: 'profileVerdict' }, 'mismatch'] },
              then: 'mismatch',
            },
            {
              id: 'G2-03',
              desc: 'Amount above the largest payment the profile expects',
              when: { '>': [{ var: 'amountUsd' }, { var: 'profileMaxAmountUsd' }] },
              then: 'mismatch',
            },
            {
              id: 'G2-04',
              desc: "Beneficiary country not in the client's profile",
              when: { '==': [{ var: 'countryInProfile' }, false] },
              then: 'mismatch',
            },
            {
              id: 'G2-99',
              desc: "The payment fits the client's profile",
              when: true,
              then: 'match',
            },
          ],
        },
      ],
    },
    {
      key: 'aml.gate3-risk',
      name: 'AML gate 3: risk score and live screening',
      owner: 'Compliance',
      useCase: 'UC2',
      description:
        'Screens the counterparty live. A strong screening hit goes to the MLRO (alert); every other monitored payment goes to a Compliance decision (clear).',
      outcomes: ['clear', 'alert'],
      sampleInputs: { ...g3, riskScore: 64 },
      regressionCases: [
        {
          name: 'Sanctions hit goes to the MLRO',
          inputs: { ...g3, screeningHit: true, screeningScore: 92 },
          expected: 'alert',
        },
        {
          name: 'A weak hit stays with Compliance',
          inputs: { ...g3, screeningHit: true, screeningScore: 60 },
          expected: 'clear',
        },
        {
          name: 'A PEP stays with Compliance',
          inputs: { ...g3, pepFlag: true },
          expected: 'clear',
        },
        { name: 'No hit', inputs: { ...g3 }, expected: 'clear' },
      ],
      versions: [
        {
          version: 1,
          status: 'approved',
          effectiveFrom: '2026-09-01T00:00:00Z',
          draftedBy: GRACE,
          draftedAt: '2026-08-25T05:00:00Z',
          approvedBy: DANIEL,
          note: 'Outcomes as in the LLD: clear (Compliance card) or alert (MLRO card).',
          rules: [
            {
              id: 'G3-01',
              desc: 'Screening hit with score 85 or more: the MLRO decides',
              when: {
                and: [
                  { '==': [{ var: 'screeningHit' }, true] },
                  { '>=': [{ var: 'screeningScore' }, 85] },
                ],
              },
              then: 'alert',
            },
            {
              id: 'G3-99',
              desc: 'No strong screening hit: Compliance decides',
              when: true,
              then: 'clear',
            },
          ],
        },
      ],
    },
    {
      key: 'uc1.field-validation',
      name: 'Bank statement field validation',
      owner: 'Operations',
      useCase: 'UC1',
      description:
        'Runs after extraction. Low confidence becomes a human-reviewed exception, never a silent error.',
      outcomes: ['pass', 'needs-review', 'reject'],
      sampleInputs: { pages: 2, minConfidence: 0.58, balanceBreaks: 1, datesOutsidePeriod: 1 },
      regressionCases: [
        {
          name: 'Clean extraction',
          inputs: { pages: 2, minConfidence: 0.96, balanceBreaks: 0, datesOutsidePeriod: 0 },
          expected: 'pass',
        },
        {
          name: 'Low confidence field',
          inputs: { pages: 2, minConfidence: 0.61, balanceBreaks: 0, datesOutsidePeriod: 0 },
          expected: 'needs-review',
        },
        {
          name: 'Empty document',
          inputs: { pages: 0, minConfidence: 0, balanceBreaks: 0, datesOutsidePeriod: 0 },
          expected: 'reject',
        },
      ],
      versions: [
        {
          version: 3,
          status: 'draft',
          effectiveFrom: null,
          draftedBy: GRACE,
          draftedAt: h(-6),
          approvedBy: null,
          note: 'Raises the red band to 0.75 for scanned statements (Operations request CR-121).',
          rules: [
            {
              id: 'F-01',
              desc: 'No pages extracted',
              when: { '<': [{ var: 'pages' }, 1] },
              then: 'reject',
            },
            {
              id: 'F-02',
              desc: 'A field below 0.75 confidence',
              when: { '<': [{ var: 'minConfidence' }, 0.75] },
              then: 'needs-review',
            },
            {
              id: 'F-03',
              desc: 'Running balance breaks',
              when: { '>': [{ var: 'balanceBreaks' }, 0] },
              then: 'needs-review',
            },
            {
              id: 'F-04',
              desc: 'Value date outside the statement period',
              when: { '>': [{ var: 'datesOutsidePeriod' }, 0] },
              then: 'needs-review',
            },
            { id: 'F-99', desc: 'All field checks pass', when: true, then: 'pass' },
          ],
        },
        {
          version: 2,
          status: 'approved',
          effectiveFrom: '2026-09-10T00:00:00Z',
          draftedBy: GRACE,
          draftedAt: '2026-09-04T03:00:00Z',
          approvedBy: PRIYA,
          note: 'Red band lowered to 0.70.',
          rules: [
            {
              id: 'F-01',
              desc: 'No pages extracted',
              when: { '<': [{ var: 'pages' }, 1] },
              then: 'reject',
            },
            {
              id: 'F-02',
              desc: 'A field below 0.70 confidence',
              when: { '<': [{ var: 'minConfidence' }, 0.7] },
              then: 'needs-review',
            },
            {
              id: 'F-03',
              desc: 'Running balance breaks',
              when: { '>': [{ var: 'balanceBreaks' }, 0] },
              then: 'needs-review',
            },
            {
              id: 'F-04',
              desc: 'Value date outside the statement period',
              when: { '>': [{ var: 'datesOutsidePeriod' }, 0] },
              then: 'needs-review',
            },
            { id: 'F-99', desc: 'All field checks pass', when: true, then: 'pass' },
          ],
        },
      ],
    },
    {
      key: 'nav.checks',
      name: 'NAV statement checks',
      owner: 'Fund accounting',
      useCase: 'UC3',
      description:
        'Tolerance, movement, completeness and staleness checks before a NAV is published to Valuefy.',
      outcomes: ['pass', 'exception'],
      sampleInputs: {
        valuationAgeBusinessDays: 0,
        navMovePctAbs: 4.8,
        tolerancePct: 3,
        sharesReconciled: true,
      },
      regressionCases: [
        {
          name: 'Within tolerance',
          inputs: {
            valuationAgeBusinessDays: 0,
            navMovePctAbs: 1.2,
            tolerancePct: 3,
            sharesReconciled: true,
          },
          expected: 'pass',
        },
        {
          name: 'Stale valuation date',
          inputs: {
            valuationAgeBusinessDays: 3,
            navMovePctAbs: 0.4,
            tolerancePct: 3,
            sharesReconciled: true,
          },
          expected: 'exception',
        },
        {
          name: 'Move beyond tolerance',
          inputs: {
            valuationAgeBusinessDays: 0,
            navMovePctAbs: 4.8,
            tolerancePct: 3,
            sharesReconciled: true,
          },
          expected: 'exception',
        },
      ],
      versions: [
        {
          version: 1,
          status: 'approved',
          effectiveFrom: '2026-09-15T00:00:00Z',
          draftedBy: GRACE,
          draftedAt: '2026-09-08T03:00:00Z',
          approvedBy: LARS,
          note: 'First version; tolerances per fund template.',
          rules: [
            {
              id: 'N-01',
              desc: 'Valuation date more than 1 business day old',
              when: { '>': [{ var: 'valuationAgeBusinessDays' }, 1] },
              then: 'exception',
            },
            {
              id: 'N-02',
              desc: 'NAV per share moved more than the fund tolerance',
              when: { '>': [{ var: 'navMovePctAbs' }, { var: 'tolerancePct' }] },
              then: 'exception',
            },
            {
              id: 'N-03',
              desc: 'Shares in issue do not reconcile to the register',
              when: { '==': [{ var: 'sharesReconciled' }, false] },
              then: 'exception',
            },
            { id: 'N-99', desc: 'All NAV checks pass', when: true, then: 'pass' },
          ],
        },
      ],
    },
  ];
}

// ---------------------------------------------------------------- statements

type LineSeed = Omit<StatementLine, 'lineId' | 'corrected' | 'approved' | 'box' | 'etag'> & {
  approved?: boolean;
};

function lines(id: string, seeds: LineSeed[]): StatementLine[] {
  return seeds.map((s, i) => ({
    ...s,
    lineId: `${id}-L${s.lineNo}`,
    corrected: [],
    approved: s.approved ?? false,
    box: { page: i < 7 ? 1 : 2, top: 30 + (i % 7) * 9, height: 6 },
    etag: 'W/"1"',
  }));
}

const ok = {
  valueDate: 0.99,
  description: 0.97,
  debit: 0.98,
  credit: 0.98,
  balance: 0.97,
  enNumber: 0.95,
};

export type StatementSeed = Omit<StatementHeader, 'checks' | 'editable' | 'references'> & {
  references: { bankId: string; accountNo: string; entity: string };
};

export function seedStatements(): { header: StatementSeed; lines: StatementLine[] }[] {
  return [
    {
      header: {
        id: 'st-2026-1041',
        cardId: 'WC-24-1041',
        bank: 'HSBC Hong Kong',
        accountNo: '848-123456-838',
        accountName: 'Lumen Capital SPC - Segregated Portfolio 2',
        currency: 'USD',
        periodFrom: '2026-09-01',
        periodTo: '2026-09-30',
        openingBalance: 125430.55,
        closingBalance: 179529.35,
        pages: 2,
        status: 'IN_REVIEW',
        extraction: { modelId: OCR, jobId: 'job-7f21c', completedAt: h(-20), threshold: 0.7 },
        references: { bankId: 'HSBCHKHHHKH', accountNo: '848-123456-838', entity: 'EN-20417' },
      },
      lines: lines('st-2026-1041', [
        {
          lineNo: 1,
          valueDate: '2026-09-02',
          description: 'Inward TT ACME Holdings Ltd INV-2209',
          debit: null,
          credit: 48000,
          balance: 173430.55,
          enNumber: 'EN-20417',
          confidence: ok,
          approved: true,
        },
        {
          lineNo: 2,
          valueDate: '2026-09-03',
          description: 'TT charges',
          debit: 25,
          credit: null,
          balance: 173405.55,
          enNumber: 'EN-20417',
          confidence: ok,
          approved: true,
        },
        {
          lineNo: 3,
          valueDate: '2026-09-05',
          description: 'Outward TT Blue Harbour Trading',
          debit: 12500,
          credit: null,
          balance: 160905.55,
          enNumber: 'EN-20417',
          confidence: ok,
          approved: true,
        },
        {
          lineNo: 4,
          valueDate: '2026-09-08',
          description: 'Management fee Amicorp HK Q3',
          debit: 3750,
          credit: null,
          balance: 157155.55,
          enNumber: 'EN-20417',
          confidence: { ...ok, description: 0.88 },
        },
        {
          lineNo: 5,
          valueDate: '2026-09-11',
          description: 'Inward TT Lumen Capital SPC',
          debit: null,
          credit: 15250,
          balance: 172405.55,
          enNumber: null,
          confidence: { ...ok, enNumber: 0 },
        },
        {
          lineNo: 6,
          valueDate: '2026-09-15',
          description: 'Outward TT Kowloon Logistics Ltd',
          debit: 1850,
          credit: null,
          balance: 171155.55,
          enNumber: 'EN-20417',
          confidence: { ...ok, debit: 0.58 },
        },
        {
          lineNo: 7,
          valueDate: '2026-09-18',
          description: 'Credit interest September',
          debit: null,
          credit: 112.4,
          balance: 171267.95,
          enNumber: 'EN-20417',
          confidence: ok,
        },
        {
          lineNo: 8,
          valueDate: '2026-09-21',
          description: 'Outward TT Meridian Legal LLP',
          debit: 8400,
          credit: null,
          balance: 162867.95,
          enNumber: 'EN-20471',
          confidence: { ...ok, enNumber: 0.74 },
        },
        {
          lineNo: 9,
          valueDate: '2026-10-23',
          description: 'FX conversion EUR to USD',
          debit: null,
          credit: 20000,
          balance: 182867.95,
          enNumber: 'EN-20417',
          confidence: { ...ok, valueDate: 0.64 },
        },
        {
          lineNo: 10,
          valueDate: '2026-09-26',
          description: 'Outward TT Harbour Audit & Tax',
          debit: 2975,
          credit: null,
          balance: 179892.95,
          enNumber: 'EN-20417',
          confidence: ok,
        },
        {
          lineNo: 11,
          valueDate: '2026-09-29',
          description: 'Card settlemnt VISA *4471',
          debit: 318.6,
          credit: null,
          balance: 179574.35,
          enNumber: 'EN-20417',
          confidence: { ...ok, description: 0.81 },
        },
        {
          lineNo: 12,
          valueDate: '2026-09-30',
          description: 'Monthly account fee',
          debit: 45,
          credit: null,
          balance: 179529.35,
          enNumber: 'EN-20417',
          confidence: ok,
        },
      ]),
    },
    {
      header: {
        id: 'st-2026-1038',
        cardId: 'WC-24-1038',
        bank: 'DBS Bank (Hong Kong)',
        accountNo: '7710-0099-41',
        accountName: 'Harbour Trust Ltd',
        currency: 'HKD',
        periodFrom: '2026-09-01',
        periodTo: '2026-09-30',
        openingBalance: 88200,
        closingBalance: 91962.5,
        pages: 1,
        status: 'SUBMITTED',
        extraction: { modelId: OCR, jobId: 'job-7e990', completedAt: h(-30), threshold: 0.7 },
        references: { bankId: 'DHBKHKHHXXX', accountNo: '7710-0099-41', entity: 'EN-31002' },
      },
      lines: lines('st-2026-1038', [
        {
          lineNo: 1,
          valueDate: '2026-09-04',
          description: 'Rental income Unit 12A',
          debit: null,
          credit: 24000,
          balance: 112200,
          enNumber: 'EN-31007',
          confidence: ok,
          approved: true,
        },
        {
          lineNo: 2,
          valueDate: '2026-09-10',
          description: 'Building management fee',
          debit: 3150,
          credit: null,
          balance: 109050,
          enNumber: 'EN-31007',
          confidence: ok,
          approved: true,
        },
        {
          lineNo: 3,
          valueDate: '2026-09-18',
          description: 'Trustee fee Amicorp Trust',
          debit: 16500,
          credit: null,
          balance: 92550,
          enNumber: 'EN-31002',
          confidence: ok,
          approved: true,
        },
        {
          lineNo: 4,
          valueDate: '2026-09-30',
          description: 'Bank charges',
          debit: 587.5,
          credit: null,
          balance: 91962.5,
          enNumber: 'EN-31002',
          confidence: ok,
          approved: true,
        },
      ]),
    },
  ];
}

// ---------------------------------------------------------------- cards

export type CardSeed = Omit<CardDetail, 'actions' | 'statement'>;

type Seed = Pick<
  CardSeed,
  | 'id'
  | 'type'
  | 'title'
  | 'subjectId'
  | 'state'
  | 'owner'
  | 'maker'
  | 'createdAt'
  | 'dueAt'
  | 'description'
> &
  Partial<CardSeed>;

const CALENDAR: Record<string, 'HK' | 'EU'> = { 'Fund accounting': 'EU' };

function card(s: Seed): CardSeed {
  const def = CARD_TYPES.find((t) => t.type === s.type)!;
  const history = s.history ?? [];
  return {
    team: def.team,
    severity: def.severity === 'by policy' ? 'medium' : def.severity,
    sla: def.sla,
    calendar: CALENDAR[def.team] ?? 'HK',
    escalationRole: def.escalationRole,
    onApproval: def.onApproval,
    recommendation: null,
    evidence: [],
    gateRuns: [],
    mandatoryChecks: [],
    delegationChain: [],
    returns: 0,
    updatedAt: history.at(-1)?.at ?? s.createdAt,
    ...s,
    history,
  };
}

const created = (at: string, note?: string) => ({
  at,
  actor: N8N.name,
  action: 'Created',
  to: 'NEW' as const,
  note,
});
const ready = (at: string) => ({
  at,
  actor: 'platform-api',
  action: 'Evidence assembled, ready for decision',
  from: 'ASSEMBLING' as const,
  to: 'AWAITING_DECISION' as const,
});

export function seedCards(): CardSeed[] {
  return [...curatedCards(), ...generatedCards()];
}

function curatedCards(): CardSeed[] {
  return [
    // ------------------------------------------------------------ UC1 Bank statements
    card({
      id: 'WC-24-1041',
      type: 'uc1.statement-validation',
      title: 'HSBC HK statement Sep 2026 - Lumen Capital SPC SP2',
      subjectId: 'st-2026-1041',
      state: 'AWAITING_DECISION',
      owner: PRIYA,
      maker: CHAN,
      value: { amount: 179529.35, currency: 'USD' },
      createdAt: h(-20),
      dueAt: h(28),
      description:
        'Extraction finished with 3 red and 3 amber fields. Field validation returned needs-review: a Maker corrects and approves every line, then a different Checker approves the card.',
      recommendation: {
        decision: 'RETURN_TO_AI',
        confidence: 0.71,
        version: 1,
        modelId: LLM,
        generatedAt: h(-20),
        summary:
          'Line 6 debit reads 1,850.00 but the running balance only supports 1,250.00 (the 2 is likely misread as 8). Line 9 value date 2026-10-23 is outside the September period; the page shows 2026-09-23. Line 5 has no EN number and line 8 has EN-20471, which is not in the lookup table (EN-20417 is the portfolio on every other line). With those fixes the statement reconciles to the closing balance of USD 179,529.35.',
        citations: ['E1', 'E2'],
      },
      evidence: [
        {
          id: 'E1',
          kind: 'statement',
          label: 'Extracted statement (12 lines)',
          source: 'OBS raw-docs/uc1/2026/10/hsbc-848-838.pdf',
          detail: '2 pages, extraction job job-7f21c, ' + OCR,
          statementId: 'st-2026-1041',
        },
        {
          id: 'E2',
          kind: 'record',
          label: 'Prior closing balance (Aug 2026)',
          source: '5 Series GL 10200-848',
          detail: 'USD 125,430.55, matches the opening balance',
        },
      ],
      gateRuns: [
        {
          runId: 'gr-91c2',
          rulesetKey: 'uc1.field-validation',
          rulesetName: 'Bank statement field validation',
          rulesetVersion: 2,
          outcome: 'needs-review',
          matchedRule: { id: 'F-02', desc: 'A field below 0.70 confidence' },
          evaluatedAt: h(-20),
          durationMs: 38,
          inputs: [
            { name: 'pages', value: 2, source: 'extraction job-7f21c', readAt: h(-20) },
            { name: 'minConfidence', value: 0.58, source: 'extraction job-7f21c', readAt: h(-20) },
            {
              name: 'balanceBreaks',
              value: 2,
              source: 'platform-api balance check',
              readAt: h(-20),
            },
            {
              name: 'datesOutsidePeriod',
              value: 1,
              source: 'platform-api period check',
              readAt: h(-20),
            },
          ],
        },
      ],
      history: [
        created(h(-20.2), 'Bank statement processing, n8n execution 48812'),
        {
          at: h(-20.1),
          actor: 'platform-api',
          action: 'Assembling evidence',
          from: 'NEW',
          to: 'ASSEMBLING',
        },
        ready(h(-20)),
        {
          at: h(-19.9),
          actor: 'n8n',
          action: 'Owner notified in Teams',
          note: 'Adaptive card to Priya Lam and role:uc1-operations',
        },
        { at: h(-6), actor: CHAN.name, action: 'Approved lines 1-3' },
      ],
    }),
    card({
      id: 'WC-24-1038',
      type: 'uc1.statement-validation',
      title: 'DBS statement Sep 2026 - Harbour Trust Ltd',
      subjectId: 'st-2026-1038',
      state: 'AWAITING_DECISION',
      owner: PRIYA,
      maker: CHAN,
      value: { amount: 91962.5, currency: 'HKD' },
      createdAt: h(-30),
      dueAt: h(10),
      description:
        'All 4 lines extracted with high confidence, corrected where needed, approved by the Maker and submitted. Ready for the Checker.',
      recommendation: {
        decision: 'APPROVE',
        confidence: 0.96,
        version: 1,
        modelId: LLM,
        generatedAt: h(-30),
        summary:
          'Every field is above 0.95 confidence, the running balance holds on all lines, EN numbers match the trust and its property unit, and the closing balance HKD 91,962.50 matches the bank figure. Recommend approval.',
        citations: ['E1'],
      },
      evidence: [
        {
          id: 'E1',
          kind: 'statement',
          label: 'Extracted statement (4 lines)',
          source: 'OBS raw-docs/uc1/2026/10/dbs-7710.pdf',
          detail: '1 page, extraction job job-7e990, ' + OCR,
          statementId: 'st-2026-1038',
        },
      ],
      gateRuns: [
        {
          runId: 'gr-90aa',
          rulesetKey: 'uc1.field-validation',
          rulesetName: 'Bank statement field validation',
          rulesetVersion: 2,
          outcome: 'pass',
          matchedRule: { id: 'F-99', desc: 'All field checks pass' },
          evaluatedAt: h(-30),
          durationMs: 22,
          inputs: [
            { name: 'pages', value: 1, source: 'extraction job-7e990', readAt: h(-30) },
            { name: 'minConfidence', value: 0.97, source: 'extraction job-7e990', readAt: h(-30) },
            {
              name: 'balanceBreaks',
              value: 0,
              source: 'platform-api balance check',
              readAt: h(-30),
            },
            {
              name: 'datesOutsidePeriod',
              value: 0,
              source: 'platform-api period check',
              readAt: h(-30),
            },
          ],
        },
      ],
      history: [
        created(h(-30)),
        ready(h(-30)),
        {
          at: h(-4),
          actor: CHAN.name,
          action: 'Submitted statement',
          note: 'All requirements-before-save gates passed',
        },
      ],
    }),
    card({
      id: 'WC-24-1046',
      type: 'uc1.extraction-exception',
      title: 'Scanned statement unreadable - BOC HK Aug 2026',
      subjectId: 'doc-55a1',
      state: 'AWAITING_DECISION',
      owner: AHMED,
      maker: N8N,
      createdAt: h(-14),
      dueAt: h(2.5),
      description:
        'Extraction failed: page 2 is rotated and scanned below 150 dpi. Return to AI to reprocess with rotation correction, or approve for manual capture.',
      recommendation: {
        decision: 'RETURN_TO_AI',
        confidence: 0.84,
        version: 1,
        modelId: LLM,
        generatedAt: h(-14),
        summary:
          'Pages 1 and 3 extract cleanly. Page 2 is rotated by 90 degrees; reprocessing with rotation correction usually recovers documents like this. Manual capture is the fallback if the second attempt fails.',
        citations: ['E1', 'E2'],
      },
      evidence: [
        {
          id: 'E1',
          kind: 'document',
          label: 'Source PDF',
          source: 'OBS raw-docs/uc1/2026/10/boc-scan-0912.pdf',
          detail: '3 pages, 96 dpi',
        },
        {
          id: 'E2',
          kind: 'record',
          label: 'Extraction error',
          source: 'extraction job-7f0b1',
          detail: 'LOW_QUALITY_IMAGE on page 2 after 3 attempts',
        },
      ],
      history: [created(h(-14), 'Extraction callback status failed'), ready(h(-14))],
    }),
    card({
      id: 'WC-24-1049',
      type: 'uc1.statement-validation',
      title: 'Standard Chartered statement Sep 2026 - Ardent Fund SPC',
      subjectId: 'st-2026-1049',
      state: 'ASSEMBLING',
      owner: AHMED,
      maker: N8N,
      value: { amount: 2_418_903.1, currency: 'USD' },
      createdAt: h(-0.1),
      dueAt: h(47),
      description: 'Extraction finished; evidence assembly and the AI summary are running.',
      history: [
        created(h(-0.1)),
        {
          at: h(-0.1),
          actor: 'platform-api',
          action: 'Assembling evidence',
          from: 'NEW',
          to: 'ASSEMBLING',
        },
      ],
    }),
    card({
      id: 'WC-24-1029',
      type: 'uc1.statement-validation',
      title: 'Standard Chartered statement Aug 2026 - Ardent Fund SPC',
      subjectId: 'st-2026-1029',
      state: 'CLOSED',
      owner: PRIYA,
      maker: CHAN,
      value: { amount: 2_301_118.4, currency: 'USD' },
      createdAt: h(-70),
      dueAt: h(-22),
      description: 'Approved and written back to 5 Series.',
      history: [
        created(h(-70)),
        ready(h(-70)),
        {
          at: h(-40),
          actor: PRIYA.name,
          action: 'Approve',
          from: 'AWAITING_DECISION',
          to: 'APPROVED',
          note: 'Lines reconcile; references checked',
        },
        {
          at: h(-40),
          actor: 'decision handler',
          action: 'Write-back started',
          from: 'APPROVED',
          to: 'WRITING_BACK',
        },
        {
          at: h(-39.9),
          actor: 'platform-api-worker',
          action: 'Write-back confirmed',
          from: 'WRITING_BACK',
          to: 'CLOSED',
        },
      ],
    }),

    // ------------------------------------------------------------ UC2 Transaction monitoring
    card({
      id: 'WC-24-2101',
      type: 'aml.compliance-decision',
      title: 'USD 48,000 inward TT from ACME Holdings Ltd',
      subjectId: 'TX-2026-1027-0042',
      state: 'AWAITING_DECISION',
      owner: KENNETH,
      maker: N8N,
      value: { amount: 48000, currency: 'USD' },
      createdAt: h(-2.5),
      dueAt: h(1.2),
      hold: 'Payment TX-2026-1027-0042 is held in CARE (hold H-3391) until this card is decided.',
      description:
        'Gate 1 put this payment under monitoring (G1-03: a single payment of USD 10,000 or more) and screening found no strong match (gate 3: clear, risk score 74). Gate 4 is this decision.',
      recommendation: {
        decision: 'APPROVE',
        confidence: 0.82,
        version: 1,
        modelId: LLM,
        generatedAt: h(-2.5),
        summary:
          'The payment matches invoice INV-2209 for consultancy services, consistent with the client profile (expected annual inflow USD 600k). The risk score comes from a new counterparty, not from screening, which is clear. Recommend releasing the hold and monitoring the next 3 payments.',
        citations: ['E1', 'E2', 'E3'],
      },
      evidence: [
        {
          id: 'E1',
          kind: 'record',
          label: 'Transaction',
          source: 'CARE payments TX-2026-1027-0042',
          detail: 'USD 48,000.00 from ACME Holdings Ltd (HK) to Lumen Capital SPC',
        },
        {
          id: 'E2',
          kind: 'document',
          label: 'Invoice INV-2209',
          source: 'CARE documents lumen/INV-2209.pdf',
          detail: 'Consultancy services Q3 2026',
        },
        {
          id: 'E3',
          kind: 'screening',
          label: 'Live screening',
          source: 'World-Check One',
          detail: 'Reference WC1-88213, outcome NO_MATCH, 10:42 HKT',
        },
      ],
      gateRuns: [
        {
          runId: 'gr-a101',
          rulesetKey: 'aml.gate1-entry',
          rulesetName: 'AML gate 1: entry thresholds',
          rulesetVersion: 3,
          outcome: 'monitor',
          matchedRule: { id: 'G1-03', desc: 'Single payment at or above USD 10,000' },
          evaluatedAt: h(-2.6),
          durationMs: 41,
          inputs: [
            { name: 'unusualFlag', value: false, source: 'CARE', readAt: h(-2.6) },
            { name: 'counterpartyId', value: 'CP-77310', source: 'CARE', readAt: h(-2.6) },
            { name: 'amountUsd', value: 48000, source: 'CARE', readAt: h(-2.6) },
            {
              name: 'amountUsdSum7d',
              value: 48000,
              source: 'lake gold.payments_7d',
              readAt: h(-2.6),
            },
            { name: 'beneficiaryCtry', value: 'HK', source: '5 Series', readAt: h(-2.6) },
          ],
        },
        {
          runId: 'gr-a102',
          rulesetKey: 'aml.gate2-profile',
          rulesetName: 'AML gate 2: client profile',
          rulesetVersion: 1,
          outcome: 'match',
          matchedRule: { id: 'G2-99', desc: "The payment fits the client's profile" },
          evaluatedAt: h(-2.6),
          durationMs: 1850,
          modelId: LLM,
          inputs: [
            {
              name: 'profileVerdict',
              value: 'match',
              source: 'LLM interpretation',
              readAt: h(-2.6),
            },
            { name: 'amountUsd', value: 48000, source: 'CARE', readAt: h(-2.6) },
            { name: 'profileMaxAmountUsd', value: 60000, source: 'CARE profile', readAt: h(-2.6) },
            { name: 'countryInProfile', value: true, source: 'CARE profile', readAt: h(-2.6) },
          ],
        },
        {
          runId: 'gr-a103',
          rulesetKey: 'aml.gate3-risk',
          rulesetName: 'AML gate 3: risk score and live screening',
          rulesetVersion: 1,
          outcome: 'clear',
          matchedRule: { id: 'G3-99', desc: 'No strong screening hit: Compliance decides' },
          evaluatedAt: h(-2.5),
          durationMs: 2210,
          inputs: [
            {
              name: 'screeningHit',
              value: false,
              source: 'World-Check One WC1-88213',
              readAt: h(-2.5),
            },
            {
              name: 'screeningScore',
              value: 0,
              source: 'World-Check One WC1-88213',
              readAt: h(-2.5),
            },
            { name: 'riskScore', value: 74, source: 'risk model v5', readAt: h(-2.5) },
            { name: 'pepFlag', value: false, source: '5 Series', readAt: h(-2.5) },
          ],
        },
      ],
      mandatoryChecks: [
        {
          id: 'screening',
          desc: 'Live screening completed for this payment (never cached)',
          met: true,
        },
      ],
      history: [
        created(h(-2.6), 'Transaction monitoring, n8n execution 51207'),
        ready(h(-2.5)),
        {
          at: h(-2.5),
          actor: 'platform-api',
          action: 'Payment hold placed',
          note: 'CARE hold H-3391',
        },
        {
          at: h(-2.5),
          actor: 'n8n',
          action: 'Owner notified in Teams',
          note: 'Adaptive card to Kenneth Ho',
        },
        {
          at: h(-0.3),
          actor: 'SLA sweep',
          action: 'Reminder at 75 % of the SLA',
          note: 'Teams message to Kenneth Ho',
        },
      ],
    }),
    card({
      id: 'WC-24-2107',
      type: 'aml.mlro-escalation',
      title: 'Possible sanctions match - Seabright Marine FZE',
      subjectId: 'TX-2026-1027-0311',
      state: 'AWAITING_DECISION',
      owner: DANIEL,
      maker: N8N,
      value: { amount: 9400, currency: 'USD' },
      createdAt: h(-1),
      dueAt: h(3),
      hold: 'Funds for TX-2026-1027-0311 are frozen until the MLRO decides.',
      description:
        'Live screening returned a possible match (score 91) for the beneficiary. Only the MLRO can decide this card.',
      recommendation: {
        decision: 'REJECT',
        confidence: 0.77,
        version: 1,
        modelId: LLM,
        generatedAt: h(-1),
        summary:
          'The beneficiary name, country (AE) and activity are consistent with the possible match; the registration number differs by one digit. Treat it as a true match until proven otherwise: reject, keep the funds frozen and prepare the STR pack.',
        citations: ['E1', 'E2'],
      },
      evidence: [
        {
          id: 'E1',
          kind: 'screening',
          label: 'Live screening',
          source: 'World-Check One',
          detail: 'Reference WC1-88290, outcome POSSIBLE_MATCH (score 91), 13:05 HKT',
        },
        {
          id: 'E2',
          kind: 'record',
          label: 'Transaction',
          source: 'CARE payments TX-2026-1027-0311',
          detail: 'USD 9,400.00 outward to Seabright Marine FZE, AE',
        },
      ],
      gateRuns: [
        {
          runId: 'gr-a201',
          rulesetKey: 'aml.gate3-risk',
          rulesetName: 'AML gate 3: risk score and live screening',
          rulesetVersion: 1,
          outcome: 'alert',
          matchedRule: {
            id: 'G3-01',
            desc: 'Screening hit with score 85 or more: the MLRO decides',
          },
          evaluatedAt: h(-1),
          durationMs: 2480,
          inputs: [
            {
              name: 'screeningHit',
              value: true,
              source: 'World-Check One WC1-88290',
              readAt: h(-1),
            },
            {
              name: 'screeningScore',
              value: 91,
              source: 'World-Check One WC1-88290',
              readAt: h(-1),
            },
            { name: 'riskScore', value: 58, source: 'risk model v5', readAt: h(-1) },
            { name: 'pepFlag', value: false, source: '5 Series', readAt: h(-1) },
          ],
        },
      ],
      mandatoryChecks: [
        {
          id: 'screening',
          desc: 'Live screening completed for this payment (never cached)',
          met: true,
        },
      ],
      history: [
        created(h(-1)),
        ready(h(-1)),
        { at: h(-1), actor: 'platform-api', action: 'Funds frozen', note: 'CARE hold H-3402' },
      ],
    }),
    card({
      id: 'WC-24-2110',
      type: 'aml.gate-exception',
      title: 'Gate 3 screening timed out - TX-2026-1026-0188',
      subjectId: 'TX-2026-1026-0188',
      state: 'ESCALATED',
      owner: KENNETH,
      maker: N8N,
      value: { amount: 15500, currency: 'USD' },
      createdAt: h(-4),
      dueAt: h(-2),
      hold: 'The payment is held, not released, until a compliance decision is recorded.',
      description:
        'The screening provider timed out 5 times. The 2-business-hour SLA passed and the card was escalated to the MLRO.',
      evidence: [
        {
          id: 'E1',
          kind: 'record',
          label: 'Incident',
          source: 'platform-api incidents INC-0442',
          detail: 'failedAt: Gate 3 Risk and screening, HTTP 504',
        },
      ],
      history: [
        created(h(-4)),
        ready(h(-4)),
        {
          at: h(-3.5),
          actor: 'SLA sweep',
          action: 'Reminder at 75 % of the SLA',
          note: 'Teams message to Kenneth Ho',
        },
        {
          at: h(-2),
          actor: 'SLA sweep',
          action: 'Escalated',
          from: 'AWAITING_DECISION',
          to: 'ESCALATED',
          note: 'Escalated to the MLRO',
        },
      ],
    }),
    card({
      id: 'WC-24-2112',
      type: 'aml.profile-update',
      title: 'UBO details missing - Harbour Trust Ltd',
      subjectId: 'ENT-40188',
      state: 'AWAITING_DECISION',
      owner: AVA,
      maker: N8N,
      createdAt: h(-5),
      dueAt: h(9),
      hold: 'Transaction TX-2026-1027-0097 is blocked until the profile is updated and gate 2 passes again.',
      description:
        'Gate 2 could not match the payment to the client profile: one UBO has no verified ID document on file, so the model was uncertain (G2-01).',
      recommendation: {
        decision: 'APPROVE',
        confidence: 0.88,
        version: 1,
        modelId: LLM,
        generatedAt: h(-5),
        summary:
          'The passport for UBO Leung K. W. arrived by email on 24 Oct and is valid to 2031. Approve the profile update; gate 2 then re-runs automatically.',
        citations: ['E1', 'E2'],
      },
      evidence: [
        {
          id: 'E1',
          kind: 'record',
          label: 'Client profile',
          source: '5 Series ENT-40188',
          detail: '2 of 3 UBOs verified',
        },
        {
          id: 'E2',
          kind: 'document',
          label: 'Passport (UBO 3)',
          source: 'CARE documents harbour/ubo3-passport.pdf',
          detail: 'Received 24 Oct 2026',
        },
      ],
      gateRuns: [
        {
          runId: 'gr-a301',
          rulesetKey: 'aml.gate2-profile',
          rulesetName: 'AML gate 2: client profile',
          rulesetVersion: 1,
          outcome: 'mismatch',
          matchedRule: { id: 'G2-01', desc: 'The model could not tell: treated as a mismatch' },
          evaluatedAt: h(-5),
          durationMs: 1630,
          modelId: LLM,
          inputs: [
            {
              name: 'profileVerdict',
              value: 'uncertain',
              source: 'LLM interpretation',
              readAt: h(-5),
            },
            { name: 'amountUsd', value: 18500, source: 'CARE', readAt: h(-5) },
            { name: 'profileMaxAmountUsd', value: 60000, source: 'CARE profile', readAt: h(-5) },
            { name: 'countryInProfile', value: true, source: 'CARE profile', readAt: h(-5) },
          ],
        },
      ],
      history: [created(h(-5)), ready(h(-5))],
    }),
    card({
      id: 'WC-24-2115',
      type: 'aml.compliance-decision',
      title: 'USD 22,400 outward TT to Zurich Precision AG',
      subjectId: 'TX-2026-1027-0144',
      state: 'AWAITING_DECISION',
      owner: AVA,
      maker: N8N,
      value: { amount: 22400, currency: 'USD' },
      createdAt: h(-1.5),
      dueAt: h(3.4),
      hold: 'Payment TX-2026-1027-0144 is held in CARE until this card is decided.',
      description:
        'A politically exposed person is a director of the paying entity. Screening found no strong match, so gate 3 sent the payment to Compliance (G3-99).',
      recommendation: {
        decision: 'APPROVE',
        confidence: 0.79,
        version: 1,
        modelId: LLM,
        generatedAt: h(-1.5),
        summary:
          'The PEP status is already recorded in the profile with enhanced due diligence completed in June. The payment matches a supplier contract on file. Recommend approval with a note to the next periodic review.',
        citations: ['E1', 'E2'],
      },
      evidence: [
        {
          id: 'E1',
          kind: 'record',
          label: 'Client profile',
          source: '5 Series ENT-30552',
          detail: 'PEP: director; EDD completed 12 Jun 2026',
        },
        {
          id: 'E2',
          kind: 'document',
          label: 'Supplier contract',
          source: 'CARE documents zurich-precision/contract-2026.pdf',
          detail: 'Precision parts supply, signed 3 Feb 2026',
        },
        {
          id: 'E3',
          kind: 'screening',
          label: 'Live screening',
          source: 'World-Check One',
          detail: 'Reference WC1-88301, outcome PEP_KNOWN, 14:12 HKT',
        },
      ],
      gateRuns: [
        {
          runId: 'gr-a144',
          rulesetKey: 'aml.gate3-risk',
          rulesetName: 'AML gate 3: risk score and live screening',
          rulesetVersion: 1,
          outcome: 'clear',
          matchedRule: { id: 'G3-99', desc: 'No strong screening hit: Compliance decides' },
          evaluatedAt: h(-1.5),
          durationMs: 1980,
          inputs: [
            {
              name: 'screeningHit',
              value: false,
              source: 'World-Check One WC1-88301',
              readAt: h(-1.5),
            },
            {
              name: 'screeningScore',
              value: 0,
              source: 'World-Check One WC1-88301',
              readAt: h(-1.5),
            },
            { name: 'riskScore', value: 41, source: 'risk model v5', readAt: h(-1.5) },
            { name: 'pepFlag', value: true, source: '5 Series', readAt: h(-1.5) },
          ],
        },
      ],
      mandatoryChecks: [
        {
          id: 'screening',
          desc: 'Live screening completed for this payment (never cached)',
          met: true,
        },
      ],
      history: [created(h(-1.5)), ready(h(-1.5))],
    }),
    card({
      id: 'WC-24-2098',
      type: 'aml.compliance-decision',
      title: 'USD 15,500 outward TT to Kestrel Imports Ltd',
      subjectId: 'TX-2026-1025-0090',
      state: 'CLOSED',
      owner: KENNETH,
      maker: N8N,
      value: { amount: 15500, currency: 'USD' },
      createdAt: h(-60),
      dueAt: h(-56),
      description: 'Rejected: the supporting invoice did not match the goods description.',
      history: [
        created(h(-60)),
        ready(h(-60)),
        {
          at: h(-58),
          actor: KENNETH.name,
          action: 'Reject',
          from: 'AWAITING_DECISION',
          to: 'REJECTED',
          note: 'Invoice does not support the payment',
        },
        { at: h(-58), actor: 'decision handler', action: 'Closed', from: 'REJECTED', to: 'CLOSED' },
      ],
    }),

    // ------------------------------------------------------------ UC3 NAV statements
    card({
      id: 'WC-24-3005',
      type: 'nav.approval',
      title: 'NAV 30 Sep 2026 - Meridian Growth Fund Class A',
      subjectId: 'nav-2026-0930-MGF-A',
      state: 'AWAITING_DECISION',
      owner: LARS,
      maker: SOFIA,
      value: { amount: 48_200_000, currency: 'USD' },
      createdAt: h(-7),
      dueAt: h(17),
      description: 'All four NAV checks passed. NAV per share USD 12.4187 (+1.2 % on the month).',
      recommendation: {
        decision: 'APPROVE',
        confidence: 0.94,
        version: 1,
        modelId: LLM,
        generatedAt: h(-7),
        summary:
          'The valuation date is current, the 1.2 % move is within the 3 % tolerance and shares in issue reconcile to the register. Recommend publishing to Valuefy.',
        citations: ['E1'],
      },
      evidence: [
        {
          id: 'E1',
          kind: 'document',
          label: 'Administrator NAV statement',
          source: 'OBS raw-docs/uc3/2026/10/mgf-a.pdf',
          detail: 'NAV USD 48.2m, 3,881,204 shares',
        },
      ],
      gateRuns: [
        {
          runId: 'gr-n301',
          rulesetKey: 'nav.checks',
          rulesetName: 'NAV statement checks',
          rulesetVersion: 1,
          outcome: 'pass',
          matchedRule: { id: 'N-99', desc: 'All NAV checks pass' },
          evaluatedAt: h(-7),
          durationMs: 30,
          inputs: [
            { name: 'valuationAgeBusinessDays', value: 0, source: 'extraction', readAt: h(-7) },
            { name: 'navMovePctAbs', value: 1.2, source: 'Valuefy prior NAV', readAt: h(-7) },
            { name: 'tolerancePct', value: 3, source: 'fund template MGF', readAt: h(-7) },
            { name: 'sharesReconciled', value: true, source: 'register', readAt: h(-7) },
          ],
        },
      ],
      history: [
        created(h(-7)),
        ready(h(-7)),
        {
          at: h(-5),
          actor: SOFIA.name,
          action: 'Reviewed the NAV pack',
          note: 'Ready for approval',
        },
      ],
    }),
    card({
      id: 'WC-24-3009',
      type: 'nav.exception',
      title: 'NAV move 4.8 % over tolerance - Meridian Income Fund Class B',
      subjectId: 'nav-2026-0930-MIF-B',
      state: 'AWAITING_DECISION',
      owner: LARS,
      maker: SOFIA,
      value: { amount: 12_640_000, currency: 'USD' },
      createdAt: h(-6),
      dueAt: h(4),
      description: 'NAV per share fell 4.8 %, beyond the 3 % tolerance for this share class.',
      recommendation: {
        decision: 'APPROVE',
        confidence: 0.69,
        version: 1,
        modelId: LLM,
        generatedAt: h(-6),
        summary:
          'The administrator notes a 5.1 % write-down of a bond holding on 28 Sep, which explains the move. Accept it with that rationale, or Return-to-AI to reconcile against the custody report.',
        citations: ['E1', 'E2'],
      },
      evidence: [
        {
          id: 'E1',
          kind: 'document',
          label: 'Administrator NAV statement',
          source: 'OBS raw-docs/uc3/2026/10/mif-b.pdf',
          detail: 'NAV per share USD 9.8820',
        },
        {
          id: 'E2',
          kind: 'document',
          label: 'Administrator commentary',
          source: 'OBS raw-docs/uc3/2026/10/mif-b-notes.pdf',
          detail: 'Bond write-down on 28 Sep 2026',
        },
      ],
      gateRuns: [
        {
          runId: 'gr-n309',
          rulesetKey: 'nav.checks',
          rulesetName: 'NAV statement checks',
          rulesetVersion: 1,
          outcome: 'exception',
          matchedRule: { id: 'N-02', desc: 'NAV per share moved more than the fund tolerance' },
          evaluatedAt: h(-6),
          durationMs: 27,
          inputs: [
            { name: 'valuationAgeBusinessDays', value: 0, source: 'extraction', readAt: h(-6) },
            { name: 'navMovePctAbs', value: 4.8, source: 'Valuefy prior NAV', readAt: h(-6) },
            { name: 'tolerancePct', value: 3, source: 'fund template MIF', readAt: h(-6) },
            { name: 'sharesReconciled', value: true, source: 'register', readAt: h(-6) },
          ],
        },
      ],
      history: [created(h(-6)), ready(h(-6))],
    }),
    card({
      id: 'WC-24-3011',
      type: 'nav.extraction-exception',
      title: 'NAV statement password-protected - Ardent Fund SPC Class C',
      subjectId: 'doc-61c9',
      state: 'AWAITING_DECISION',
      owner: LARS,
      maker: N8N,
      createdAt: h(-3),
      dueAt: h(21),
      description:
        'The administrator sent an encrypted PDF. Request an unprotected copy, or capture the NAV manually.',
      evidence: [
        {
          id: 'E1',
          kind: 'document',
          label: 'Source PDF',
          source: 'OBS raw-docs/uc3/2026/10/ardent-c.pdf',
          detail: 'Encrypted, 4 pages',
        },
      ],
      history: [
        created(h(-3), 'Extraction callback status failed: ENCRYPTED_DOCUMENT'),
        ready(h(-3)),
      ],
    }),

    // ------------------------------------------------------------ UC4 Data validation
    card({
      id: 'WC-24-4120',
      type: 'uc4.discrepancy',
      title: 'Registered address differs CARE vs 5 Series - ENT-55120',
      subjectId: 'ENT-55120',
      state: 'AWAITING_DECISION',
      owner: MEILING,
      maker: MEILING,
      createdAt: h(-26),
      dueAt: h(70),
      description:
        'Mei Ling Tan prepared the correction as Maker, so maker-checker stops her approving it even though she also holds Checker. She can delegate it to Ravi Menon.',
      recommendation: {
        decision: 'APPROVE',
        confidence: 0.9,
        version: 1,
        modelId: LLM,
        generatedAt: h(-26),
        summary:
          'The 5 Series address matches the Companies Registry extract of 12 Oct 2026. Update CARE to "Unit 2201, 22/F, Lippo Centre Tower 1, 89 Queensway, Admiralty".',
        citations: ['E1', 'E2'],
      },
      evidence: [
        {
          id: 'E1',
          kind: 'lake-row',
          label: 'Discrepancy finding',
          source: 'lake bronze.uc4_findings F-88120',
          detail: 'CARE: "Unit 2201 Lippo Ctr"; 5 Series: full address',
        },
        {
          id: 'E2',
          kind: 'document',
          label: 'Companies Registry extract',
          source: 'CARE documents ENT-55120/cr-2026-10-12.pdf',
          detail: 'Registered office updated 1 Oct 2026',
        },
      ],
      gateRuns: [
        {
          runId: 'gr-d412',
          rulesetKey: 'uc4.discrepancy-catalogue',
          rulesetName: 'Discrepancy catalogue',
          rulesetVersion: 3,
          outcome: 'discrepancy',
          matchedRule: { id: 'D-07', desc: 'Registered address differs between CARE and 5 Series' },
          evaluatedAt: h(-26),
          durationMs: 12,
          inputs: [
            { name: 'care.address', value: 'Unit 2201 Lippo Ctr', source: 'CARE', readAt: h(-26) },
            {
              name: 'series5.address',
              value: 'Unit 2201, 22/F, Lippo Centre Tower 1, 89 Queensway',
              source: '5 Series',
              readAt: h(-26),
            },
          ],
        },
      ],
      history: [
        created(h(-26), 'Scan uc4:2026-10-26'),
        ready(h(-25.9)),
        {
          at: h(-3),
          actor: MEILING.name,
          action: 'Proposed correction',
          note: 'Accepted the proposed CARE address',
        },
      ],
    }),
    card({
      id: 'WC-24-4127',
      type: 'uc4.discrepancy',
      title: 'Director date of birth differs CARE vs Pega - ENT-30077',
      subjectId: 'ENT-30077',
      state: 'AWAITING_DECISION',
      owner: RAVI,
      maker: N8N,
      createdAt: h(-30),
      dueAt: h(62),
      description:
        'The date of birth for director J. Visser differs by one day between CARE and AmiPortal (Pega).',
      recommendation: {
        decision: 'APPROVE',
        confidence: 0.86,
        version: 1,
        modelId: LLM,
        generatedAt: h(-30),
        summary:
          'The passport copy in CARE shows 14 Mar 1979, matching Pega. CARE has 15 Mar 1979, likely a time-zone conversion error at import. Correct CARE.',
        citations: ['E1', 'E2'],
      },
      evidence: [
        {
          id: 'E1',
          kind: 'lake-row',
          label: 'Discrepancy finding',
          source: 'lake bronze.uc4_findings F-88127',
          detail: 'CARE 1979-03-15; Pega 1979-03-14',
        },
        {
          id: 'E2',
          kind: 'document',
          label: 'Passport copy',
          source: 'CARE documents ENT-30077/director-visser-passport.pdf',
          detail: 'Page 2, date of birth',
        },
      ],
      history: [created(h(-30), 'Scan uc4:2026-10-26'), ready(h(-29.9))],
    }),
    card({
      id: 'WC-24-4133',
      type: 'uc4.discrepancy',
      title: 'Possible duplicate entity - ENT-61002 / ENT-61027',
      subjectId: 'ENT-61002',
      state: 'ASSEMBLING',
      owner: RAVI,
      maker: N8N,
      createdAt: h(-0.2),
      dueAt: h(110),
      description: 'Evidence assembly and the AI summary are still running.',
      history: [
        created(h(-0.2)),
        {
          at: h(-0.2),
          actor: 'platform-api',
          action: 'Assembling evidence',
          from: 'NEW',
          to: 'ASSEMBLING',
        },
      ],
    }),
    card({
      id: 'WC-24-4101',
      type: 'uc4.discrepancy',
      title: 'Write-back failed: phone number format - ENT-50413',
      subjectId: 'ENT-50413',
      state: 'WRITEBACK_FAILED',
      owner: RAVI,
      maker: MEILING,
      createdAt: h(-50),
      dueAt: h(40),
      description:
        'CARE rejected the write-back 5 times (phone must be E.164). Platform support retries or reverses it from the before-image.',
      history: [
        created(h(-50)),
        ready(h(-50)),
        {
          at: h(-30),
          actor: RAVI.name,
          action: 'Approve',
          from: 'AWAITING_DECISION',
          to: 'APPROVED',
          note: 'Format confirmed with the client',
        },
        {
          at: h(-30),
          actor: 'decision handler',
          action: 'Write-back started',
          from: 'APPROVED',
          to: 'WRITING_BACK',
        },
        {
          at: h(-29),
          actor: 'platform-api-worker',
          action: 'Write-back failed after 5 attempts',
          from: 'WRITING_BACK',
          to: 'WRITEBACK_FAILED',
          note: 'CARE 422: phone must be E.164',
        },
      ],
    }),

    // ------------------------------------------------------------ UC5 Violations
    card({
      id: 'WC-24-5021',
      type: 'uc5.violation',
      title: 'Fewer directors than policy minimum - Seabright Holdings BV',
      subjectId: 'ENT-40188',
      state: 'AWAITING_DECISION',
      severity: 'high',
      owner: RAVI,
      maker: N8N,
      createdAt: h(-10),
      dueAt: h(14),
      description:
        'Policy POL-GOV-03 requires at least 2 directors; the Gold layer has shown 1 since 30 Sep.',
      recommendation: {
        decision: 'DELEGATE',
        confidence: 0.63,
        version: 1,
        modelId: LLM,
        generatedAt: h(-10),
        summary:
          'A director resigned on 30 Sep with no replacement. The client relationship team must appoint a director; the data correction follows. Delegate to the Checker who owns the relationship.',
        citations: ['E1'],
      },
      evidence: [
        {
          id: 'E1',
          kind: 'lake-row',
          label: 'Violation finding',
          source: 'lake gold.uc5_violations V-40188-03',
          detail: 'directorCount = 1, policy minimum 2',
        },
      ],
      gateRuns: [
        {
          runId: 'gr-v502',
          rulesetKey: 'uc5.violation-catalogue',
          rulesetName: 'Violation catalogue',
          rulesetVersion: 2,
          outcome: 'violation',
          matchedRule: { id: 'POL-GOV-03', desc: 'Entity has fewer than 2 directors' },
          evaluatedAt: h(-10),
          durationMs: 9,
          inputs: [
            {
              name: 'directorCount',
              value: 1,
              source: 'lake gold.entity_officers',
              readAt: h(-10),
            },
          ],
        },
      ],
      history: [created(h(-10), 'Scan uc5:2026-W43'), ready(h(-10))],
    }),
    card({
      id: 'WC-24-5018',
      type: 'uc5.violation',
      title: 'KYC review overdue - Pacific Rim Traders Ltd',
      subjectId: 'ENT-28810',
      state: 'AWAITING_DECISION',
      severity: 'medium',
      owner: MEILING,
      maker: N8N,
      createdAt: h(-22),
      dueAt: h(50),
      description:
        'Policy POL-KYC-02: periodic KYC review is 14 days overdue for a high-risk client.',
      recommendation: {
        decision: 'APPROVE',
        confidence: 0.81,
        version: 1,
        modelId: LLM,
        generatedAt: h(-22),
        summary:
          'Approve the recommended correction: set the review status to "in progress" and open a KYC chase with the relationship manager.',
        citations: ['E1'],
      },
      evidence: [
        {
          id: 'E1',
          kind: 'lake-row',
          label: 'Violation finding',
          source: 'lake gold.uc5_violations V-28810-02',
          detail: 'nextReviewDate 2026-10-13, risk rating high',
        },
      ],
      history: [created(h(-22), 'Scan uc5:2026-W43'), ready(h(-22))],
    }),
  ];
}

/** A card the mock "creates" after page load, to show live updates (card.created over SSE). */
export function arrivingCard(): CardSeed {
  return card({
    id: 'WC-24-2121',
    type: 'aml.compliance-decision',
    title: 'USD 12,750 inward TT from Pacific Rim Traders Ltd',
    subjectId: 'TX-2026-1027-0187',
    state: 'AWAITING_DECISION',
    owner: KENNETH,
    maker: N8N,
    value: { amount: 12750, currency: 'USD' },
    createdAt: h(0),
    dueAt: h(4),
    hold: 'Payment TX-2026-1027-0187 is held in CARE until this card is decided.',
    description:
      'Gate 1 put this payment under monitoring (G1-03) and screening found no strong match (gate 3: clear). The client also has an overdue KYC review (see WC-24-5018).',
    recommendation: {
      decision: 'RETURN_TO_AI',
      confidence: 0.66,
      version: 1,
      modelId: LLM,
      generatedAt: h(0),
      summary:
        'The payment is consistent with prior trade receipts, but the KYC review is overdue. Hold until the KYC chase completes, or ask the assistant to check the latest relationship notes.',
      citations: ['E1'],
    },
    evidence: [
      {
        id: 'E1',
        kind: 'record',
        label: 'Transaction',
        source: 'CARE payments TX-2026-1027-0187',
        detail: 'USD 12,750.00 from Pacific Rim Traders Ltd',
      },
      {
        id: 'E2',
        kind: 'screening',
        label: 'Live screening',
        source: 'World-Check One',
        detail: 'Reference WC1-88342, outcome NO_MATCH',
      },
    ],
    history: [created(h(0), 'Transaction monitoring, n8n execution 51288'), ready(h(0))],
  });
}

// ---------------------------------------------------------------- audit

export function seedAudit(): AuditEvent[] {
  const rows: Omit<AuditEvent, 'id'>[] = [
    {
      at: h(-70),
      actor: 'n8n',
      actorRole: 'Automation',
      action: 'card.created',
      entity: 'card',
      entityId: 'WC-24-1029',
      detail: 'uc1.statement-validation',
      domain: 'General',
    },
    {
      at: h(-60),
      actor: 'n8n',
      actorRole: 'Automation',
      action: 'gate.evaluated',
      entity: 'transaction',
      entityId: 'TX-2026-1025-0090',
      detail: 'aml.gate3-risk v1: clear (G3-99)',
      domain: 'AML',
    },
    {
      at: h(-58),
      actor: 'Kenneth Ho',
      actorRole: 'Checker',
      action: 'card.decided',
      entity: 'card',
      entityId: 'WC-24-2098',
      detail: 'REJECT: Invoice does not support the payment',
      domain: 'AML',
    },
    {
      at: h(-50),
      actor: 'n8n',
      actorRole: 'Automation',
      action: 'card.created',
      entity: 'card',
      entityId: 'WC-24-4101',
      detail: 'uc4.discrepancy',
      domain: 'General',
    },
    {
      at: h(-40),
      actor: 'Priya Lam',
      actorRole: 'Checker',
      action: 'card.decided',
      entity: 'card',
      entityId: 'WC-24-1029',
      detail: 'APPROVE: Lines reconcile; references checked',
      domain: 'General',
    },
    {
      at: h(-39.9),
      actor: 'platform-api-worker',
      actorRole: 'Automation',
      action: 'writeback.confirmed',
      entity: 'card',
      entityId: 'WC-24-1029',
      detail: '5 Series status write-back acknowledged',
      domain: 'General',
    },
    {
      at: h(-30),
      actor: 'Ravi Menon',
      actorRole: 'Checker',
      action: 'card.decided',
      entity: 'card',
      entityId: 'WC-24-4101',
      detail: 'APPROVE: Format confirmed with the client',
      domain: 'General',
    },
    {
      at: h(-29),
      actor: 'platform-api-worker',
      actorRole: 'Automation',
      action: 'writeback.failed',
      entity: 'card',
      entityId: 'WC-24-4101',
      detail: 'CARE 422 after 5 attempts',
      domain: 'General',
    },
    {
      at: h(-28),
      actor: 'Grace Lee',
      actorRole: 'Admin',
      action: 'ruleset.drafted',
      entity: 'ruleset',
      entityId: 'aml.gate1-entry',
      detail: 'v4 draft: adds G1-06 structuring',
      domain: 'AML',
    },
    {
      at: h(-26),
      actor: 'n8n',
      actorRole: 'Automation',
      action: 'scan.completed',
      entity: 'scan',
      entityId: 'uc4:2026-10-26',
      detail: '14 findings, 3 new cards',
      domain: 'General',
    },
    {
      at: h(-20),
      actor: 'n8n',
      actorRole: 'Automation',
      action: 'gate.evaluated',
      entity: 'statement',
      entityId: 'st-2026-1041',
      detail: 'uc1.field-validation v2: needs-review (F-02)',
      domain: 'General',
    },
    {
      at: h(-10),
      actor: 'n8n',
      actorRole: 'Automation',
      action: 'scan.completed',
      entity: 'scan',
      entityId: 'uc5:2026-W43',
      detail: '6 violations, 2 new cards',
      domain: 'General',
    },
    {
      at: h(-6),
      actor: 'Chan Tai Man',
      actorRole: 'Maker',
      action: 'statement.line.approved',
      entity: 'statement',
      entityId: 'st-2026-1041',
      detail: 'Lines 1-3',
      domain: 'General',
    },
    {
      at: h(-6),
      actor: 'Grace Lee',
      actorRole: 'Admin',
      action: 'ruleset.drafted',
      entity: 'ruleset',
      entityId: 'uc1.field-validation',
      detail: 'v3 draft: red band 0.75 for scans',
      domain: 'General',
    },
    {
      at: h(-5),
      actor: 'n8n',
      actorRole: 'Automation',
      action: 'gate.evaluated',
      entity: 'transaction',
      entityId: 'TX-2026-1027-0097',
      detail: 'aml.gate2-profile v1: mismatch (G2-01)',
      domain: 'AML',
    },
    {
      at: h(-4),
      actor: 'Chan Tai Man',
      actorRole: 'Maker',
      action: 'statement.submitted',
      entity: 'statement',
      entityId: 'st-2026-1038',
      detail: 'All gates passed',
      domain: 'General',
    },
    {
      at: h(-3),
      actor: 'Mei Ling Tan',
      actorRole: 'Maker',
      action: 'card.correction.proposed',
      entity: 'card',
      entityId: 'WC-24-4120',
      detail: 'Accepted the proposed CARE address',
      domain: 'General',
    },
    {
      at: h(-2.5),
      actor: 'n8n',
      actorRole: 'Automation',
      action: 'gate.evaluated',
      entity: 'transaction',
      entityId: 'TX-2026-1027-0042',
      detail: 'aml.gate3-risk v1: clear (G3-99)',
      domain: 'AML',
    },
    {
      at: h(-2),
      actor: 'SLA sweep',
      actorRole: 'Automation',
      action: 'card.escalated',
      entity: 'card',
      entityId: 'WC-24-2110',
      detail: 'Due date passed; escalated to the MLRO',
      domain: 'AML',
    },
    {
      at: h(-1),
      actor: 'n8n',
      actorRole: 'Automation',
      action: 'screening.completed',
      entity: 'transaction',
      entityId: 'TX-2026-1027-0311',
      detail: 'World-Check One WC1-88290: POSSIBLE_MATCH',
      domain: 'AML',
    },
  ];
  return [...rows, ...generatedAudit(generatedCards())]
    .sort((a, b) => b.at.localeCompare(a.at))
    .map((r, i) => ({ ...r, id: `ae-${1000 + i}` }));
}

// ---------------------------------------------------------------- volume (history for realistic paging)

/** Deterministic pseudo-random numbers, so the demo data is the same on every load. */
function rng(seed: number): () => number {
  let s = seed >>> 0;
  return () => {
    s = (Math.imul(s, 1664525) + 1013904223) >>> 0;
    return s / 4294967296;
  };
}

function pick<T>(r: () => number, list: readonly T[]): T {
  return list[Math.floor(r() * list.length)];
}

const SLA_HOURS: Record<string, number> = {
  '2 business days': 48,
  '1 business day': 24,
  '4 business hours': 4,
  '2 business hours': 2,
  '5 business days': 120,
  'by policy': 72,
};

const NO_WRITEBACK = new Set(['uc1.extraction-exception', 'aml.gate-exception', 'nav.exception']);

const CLIENTS = [
  'Lumen Capital SPC',
  'Harbour Trust Ltd',
  'Ardent Fund SPC',
  'Northgate Ventures SPC',
  'Orchid Bay Holdings Ltd',
  'Victoria Peak Family Trust',
  'Sapphire Marine Ltd',
  'Tsim Sha Tsui Properties Ltd',
  'Kowloon Logistics Ltd',
  'Pacific Rim Traders Ltd',
];
const BANKS = [
  'HSBC HK',
  'DBS HK',
  'Standard Chartered HK',
  'BOC HK',
  'Hang Seng Bank',
  'Citibank HK',
];
const FUNDS = [
  'Meridian Growth Fund Class A',
  'Meridian Income Fund Class B',
  'Ardent Fund SPC Class C',
  'Northgate Opportunities Fund',
  'Harbour Asia Equity Fund',
];
const PERIODS = ['Jul 2026', 'Aug 2026', 'Sep 2026'];
const COUNTERPARTIES = [
  'ACME Holdings Ltd',
  'Blue Harbour Trading',
  'Zurich Precision AG',
  'Kestrel Imports Ltd',
  'Golden Bridge Consulting',
  'Marina Bay Shipping',
  'Alder & Finch LLP',
];
const DISCREPANCIES = [
  'Registered address differs CARE vs 5 Series',
  'Director date of birth differs CARE vs Pega',
  'Tax residency missing in CARE',
  'Incorporation date differs CARE vs 5 Series',
  'Duplicate contact record',
];
const VIOLATIONS = [
  'KYC review overdue',
  'Expired ID document on file',
  'Missing mandatory UBO field',
  'Fewer directors than policy minimum',
];
const APPROVE_NOTES = [
  'Evidence reviewed; consistent with the client profile',
  'Reconciles to the bank figure',
  'Within tolerance; publish',
  'Correction confirmed with the client',
  'Documents verified against the registry',
];
const REJECT_NOTES = [
  'Supporting document does not match',
  'Duplicate of an earlier card',
  'Insufficient evidence; client to resubmit',
];

interface Template {
  type: string;
  weight: number;
  owners: { closed: PersonRef[]; open: PersonRef[] };
  makers: PersonRef[];
  title: (r: () => number) => string;
  subject: (n: number) => string;
  value?: (r: () => number) => { amount: number; currency: string };
}

const TEMPLATES: Template[] = [
  {
    type: 'uc1.statement-validation',
    weight: 5,
    owners: { closed: [PRIYA, AHMED], open: [AHMED] },
    makers: [CHAN],
    title: (r) => `${pick(r, BANKS)} statement ${pick(r, PERIODS)} - ${pick(r, CLIENTS)}`,
    subject: (n) => `st-2026-${String(500 + n).padStart(4, '0')}`,
    value: (r) => ({
      amount: Math.round(50_000 + r() * 2_950_000),
      currency: r() < 0.6 ? 'USD' : 'HKD',
    }),
  },
  {
    type: 'uc1.extraction-exception',
    weight: 1,
    owners: { closed: [PRIYA, AHMED], open: [AHMED] },
    makers: [N8N],
    title: (r) => `Statement could not be read - ${pick(r, BANKS)} ${pick(r, PERIODS)}`,
    subject: (n) => `doc-${(4000 + n).toString(16)}`,
  },
  {
    type: 'aml.compliance-decision',
    weight: 4,
    owners: { closed: [KENNETH, AVA], open: [AVA] },
    makers: [N8N],
    title: (r) => {
      const amount = Math.round(10_000 + r() * 240_000);
      return `USD ${amount.toLocaleString('en-US')} ${r() < 0.5 ? 'inward' : 'outward'} TT ${r() < 0.5 ? 'from' : 'to'} ${pick(r, COUNTERPARTIES)}`;
    },
    subject: (n) =>
      `TX-2026-10${String(1 + (n % 27)).padStart(2, '0')}-${String(100 + n).padStart(4, '0')}`,
    value: (r) => ({ amount: Math.round(10_000 + r() * 240_000), currency: 'USD' }),
  },
  {
    type: 'aml.profile-update',
    weight: 1,
    owners: { closed: [KENNETH, AVA], open: [AVA] },
    makers: [N8N],
    title: (r) => `Client profile incomplete - ${pick(r, CLIENTS)}`,
    subject: (n) => `ENT-${40200 + n}`,
  },
  {
    type: 'nav.approval',
    weight: 3,
    owners: { closed: [LARS], open: [LARS] },
    makers: [SOFIA],
    title: (r) =>
      `NAV ${pick(r, ['31 Jul 2026', '31 Aug 2026', '30 Sep 2026'])} - ${pick(r, FUNDS)}`,
    subject: (n) => `nav-2026-${String(100 + n)}`,
    value: (r) => ({ amount: Math.round(5_000_000 + r() * 75_000_000), currency: 'USD' }),
  },
  {
    type: 'uc4.discrepancy',
    weight: 3,
    owners: { closed: [RAVI, MEILING], open: [RAVI] },
    makers: [MEILING, N8N],
    title: (r) => `${pick(r, DISCREPANCIES)} - ENT-${50000 + Math.floor(r() * 9999)}`,
    subject: (n) => `ENT-${51000 + n}`,
  },
  {
    type: 'uc5.violation',
    weight: 2,
    owners: { closed: [RAVI, MEILING], open: [RAVI] },
    makers: [N8N],
    title: (r) => `${pick(r, VIOLATIONS)} - ${pick(r, CLIENTS)}`,
    subject: (n) => `ENT-${30100 + n}`,
  },
];

function pickTemplate(r: () => number): Template {
  const total = TEMPLATES.reduce((s, t) => s + t.weight, 0);
  let x = r() * total;
  for (const t of TEMPLATES) {
    x -= t.weight;
    if (x < 0) return t;
  }
  return TEMPLATES[0];
}

/** About 70 decided cards from the last 30 days and a dozen open ones, across every team. */
function generatedCards(): CardSeed[] {
  const r = rng(20261027);
  const cards: CardSeed[] = [];
  for (let i = 0; i < 160; i++) {
    const t = pickTemplate(r);
    const ageH = 26 + r() * 24 * 30;
    const sla = SLA_HOURS[CARD_TYPES.find((c) => c.type === t.type)?.sla ?? '1 business day'] ?? 24;
    const decideAfter = Math.min(ageH - 1, 0.5 + r() * sla * 1.1);
    const owner = pick(r, t.owners.closed);
    const maker = pick(r, t.makers);
    const approve = r() > 0.15;
    const note = approve ? pick(r, APPROVE_NOTES) : pick(r, REJECT_NOTES);
    const decidedAt = -ageH + decideAfter;
    const closing =
      approve && !NO_WRITEBACK.has(t.type)
        ? [
            {
              at: h(decidedAt + 0.02),
              actor: 'decision handler',
              action: 'Write-back started',
              from: 'APPROVED' as const,
              to: 'WRITING_BACK' as const,
            },
            {
              at: h(decidedAt + 0.1),
              actor: 'platform-api-worker',
              action: 'Write-back confirmed',
              from: 'WRITING_BACK' as const,
              to: 'CLOSED' as const,
            },
          ]
        : [
            {
              at: h(decidedAt + 0.02),
              actor: 'decision handler',
              action: 'Closed',
              from: (approve ? 'APPROVED' : 'REJECTED') as CardState,
              to: 'CLOSED' as const,
            },
          ];
    cards.push(
      card({
        id: `WC-24-${String(600 + i).padStart(4, '0')}`,
        type: t.type,
        title: t.title(r),
        subjectId: t.subject(i),
        state: 'CLOSED',
        owner,
        maker,
        value: t.value?.(r),
        createdAt: h(-ageH),
        dueAt: h(-ageH + sla),
        description: approve ? 'Approved and closed.' : 'Rejected and closed.',
        history: [
          created(h(-ageH)),
          ready(h(-ageH + 0.05)),
          {
            at: h(decidedAt),
            actor: owner.name,
            action: approve ? 'Approve' : 'Reject',
            from: 'AWAITING_DECISION',
            to: approve ? 'APPROVED' : 'REJECTED',
            note,
          },
          ...closing,
        ],
      }),
    );
  }
  for (let i = 0; i < 12; i++) {
    const t = pickTemplate(r);
    const ageH = 0.5 + r() * 20;
    const sla = SLA_HOURS[CARD_TYPES.find((c) => c.type === t.type)?.sla ?? '1 business day'] ?? 24;
    cards.push(
      card({
        // After the closed cards (WC-24-0600 to 0759), so no two cards share an ID.
        id: `WC-24-${String(800 + i).padStart(4, '0')}`,
        type: t.type,
        title: t.title(r),
        subjectId: t.subject(100 + i),
        state: 'AWAITING_DECISION',
        owner: pick(r, t.owners.open),
        maker: pick(r, t.makers),
        value: t.value?.(r),
        createdAt: h(-ageH),
        dueAt: h(-ageH + Math.max(sla, ageH + 1)),
        description: 'Raised by the automated checks; evidence assembled.',
        recommendation: {
          decision: 'APPROVE',
          confidence: Math.round((0.78 + r() * 0.18) * 100) / 100,
          version: 1,
          modelId: LLM,
          generatedAt: h(-ageH + 0.05),
          summary:
            'The evidence is consistent with the records of the systems of record; no exception found beyond the one that raised the card.',
          citations: ['E1'],
        },
        evidence: [
          {
            id: 'E1',
            kind: 'record',
            label: 'Source record',
            source: 'CARE / 5 Series',
            detail: 'Read when the card was raised',
          },
        ],
        history: [created(h(-ageH)), ready(h(-ageH + 0.05))],
      }),
    );
  }
  return cards;
}

/** Audit events that match the generated history (creation, gate, decision, write-back). */
function generatedAudit(cards: CardSeed[]): Omit<AuditEvent, 'id'>[] {
  const rows: Omit<AuditEvent, 'id'>[] = [];
  for (const c of cards) {
    const domain = c.type.startsWith('aml.') ? 'AML' : 'General';
    rows.push({
      at: c.createdAt,
      actor: 'n8n',
      actorRole: 'Automation',
      action: 'card.created',
      entity: 'card',
      entityId: c.id,
      detail: c.type,
      domain,
    });
    for (const e of c.history) {
      if (e.action === 'Approve' || e.action === 'Reject') {
        rows.push({
          at: e.at,
          actor: e.actor,
          actorRole: e.actor === DANIEL.name ? 'MLRO' : 'Checker',
          action: 'card.decided',
          entity: 'card',
          entityId: c.id,
          detail: `${e.action === 'Approve' ? 'APPROVE' : 'REJECT'}: ${e.note ?? ''}`,
          domain,
        });
      }
      if (e.action === 'Write-back confirmed') {
        rows.push({
          at: e.at,
          actor: 'platform-api-worker',
          actorRole: 'Automation',
          action: 'writeback.confirmed',
          entity: 'card',
          entityId: c.id,
          detail: 'Target acknowledged',
          domain,
        });
      }
    }
  }
  return rows;
}
