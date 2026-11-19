import { GridOptions, ModuleRegistry, themeQuartz } from 'ag-grid-community';
import { AllEnterpriseModule, LicenseManager } from 'ag-grid-enterprise';

let registered = false;

/**
 * Registers AG Grid Enterprise on first use. Only lazy routes import this file, so the
 * grid stays out of the initial bundle. The statement grid needs master-detail, range
 * selection and Excel export (decision D-14). Without a key the grid still works but
 * shows a watermark and console warnings, which is fine for DEV.
 */
export function setUpAgGrid(licenseKey: string): void {
  if (registered) return;
  registered = true;
  ModuleRegistry.registerModules([AllEnterpriseModule]);
  if (licenseKey) {
    LicenseManager.setLicenseKey(licenseKey);
  }
}

/** AG Grid theme built from the same Intertec palette and tokens as the Material theme. */
export const amcGridTheme = themeQuartz.withParams({
  fontFamily: ['Carlito', 'Calibri', 'sans-serif'],
  fontSize: 13,
  foregroundColor: '#1A2332',
  backgroundColor: '#FFFFFF',
  accentColor: '#1F5FA8',
  headerBackgroundColor: '#F7F8FA',
  headerTextColor: '#3D4757',
  headerFontSize: 12,
  headerFontWeight: 600,
  headerHeight: 38,
  rowHeight: 40,
  rowHoverColor: '#F5F8FC',
  selectedRowBackgroundColor: 'rgba(31, 95, 168, 0.10)',
  borderColor: '#E3E7EC',
  rowBorder: { color: '#EDF0F3' },
  wrapperBorderRadius: 10,
  spacing: 6,
  cellHorizontalPadding: 12,
  paginationPanelHeight: 44,
});

/** Standard paging for list grids: 25 rows a page, with 25, 50 or 100 to choose from. */
export const GRID_PAGING: Pick<
  GridOptions,
  'pagination' | 'paginationPageSize' | 'paginationPageSizeSelector'
> = {
  pagination: true,
  paginationPageSize: 25,
  paginationPageSizeSelector: [25, 50, 100],
};

/** Confidence bands for extracted fields (green, amber, red). Thresholds come from the ruleset. */
export function confidenceClass(
  confidence: number | null | undefined,
  amberBelow = 0.9,
  redBelow = 0.7,
): string {
  if (confidence == null) return 'amc-conf-none';
  if (confidence < redBelow) return 'amc-conf-red';
  if (confidence < amberBelow) return 'amc-conf-amber';
  return 'amc-conf-green';
}
