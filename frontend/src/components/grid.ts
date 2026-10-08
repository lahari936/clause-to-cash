import { AllCommunityModule, ModuleRegistry, themeQuartz } from 'ag-grid-community'

ModuleRegistry.registerModules([AllCommunityModule])

/** AG Grid in the app palette (PayPal navy/blue on a pale canvas). */
export const gridTheme = themeQuartz.withParams({
  fontFamily: 'Plus Jakarta Sans, Helvetica Neue, Arial, sans-serif',
  accentColor: '#0070e0',
  foregroundColor: '#001435',
  headerBackgroundColor: '#f5f7fa',
  headerTextColor: '#003087',
  headerFontWeight: 700,
  rowHoverColor: '#f0f6ff',
  selectedRowBackgroundColor: '#dbeafe',
  borderColor: '#e6eaf0',
  wrapperBorderRadius: 12,
  borderRadius: 8,
  rowHeight: 44,
  headerHeight: 44,
})
