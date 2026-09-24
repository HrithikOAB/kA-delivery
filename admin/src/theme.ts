/** Khana Delivery brand tokens for the admin dashboard. */
export const brand = {
  indigo: '#5B3DF5',
  indigoDark: '#4A2FE0',
  indigoSoft: '#EEEAFE',
  mint: '#19C6A5',
  mintDark: '#14A88C',
  mintSoft: '#E6FAF5',
  amber: '#FFC857',
  amberSoft: '#FFF8E6',
  bg: '#F7F8FC',
  surface: '#FFFFFF',
  border: '#E5E7EB',
  text: '#171923',
  textMuted: '#6B7280',
  danger: '#EF4444',
  dangerSoft: '#FEE2E2',
  success: '#16A34A',
  successSoft: '#DCFCE7',
  warning: '#D97706',
  warningSoft: '#FEF3C7',
};

/** Colour + label for a partner verification status. */
export const approvalMeta: Record<string, { label: string; color: string; soft: string }> = {
  draft: { label: 'Draft', color: brand.textMuted, soft: brand.border },
  pending: { label: 'Pending', color: brand.warning, soft: brand.warningSoft },
  submitted: { label: 'Submitted', color: brand.indigo, soft: brand.indigoSoft },
  under_review: { label: 'Under review', color: brand.warning, soft: brand.warningSoft },
  approved: { label: 'Approved', color: brand.success, soft: brand.successSoft },
  rejected: { label: 'Rejected', color: brand.danger, soft: brand.dangerSoft },
  needs_correction: { label: 'Needs correction', color: brand.amberSoft && brand.warning, soft: brand.amberSoft },
};

export const money = (cents: number) => `₹${(cents / 100).toFixed(2)}`;

export const formatGmv = (cents: number) => {
  const rupees = cents / 100;
  if (rupees >= 100000) return `₹${(rupees / 100000).toFixed(2)}L`;
  if (rupees >= 1000) return `₹${Math.round(rupees).toLocaleString('en-IN')}`;
  return money(cents);
};

export const orderStatusMeta: Record<string, { label: string; cls: string }> = {
  preparing: { label: 'Prep Delayed', cls: 'status-warn' },
  ready: { label: 'Dispatching', cls: 'status-info' },
  picked_up: { label: 'Picked Up', cls: 'status-ok' },
  out_for_delivery: { label: 'In-Transit', cls: 'status-purple' },
  assigned: { label: 'Dispatching', cls: 'status-info' },
  accepted: { label: 'Kitchen', cls: 'status-muted' },
};
