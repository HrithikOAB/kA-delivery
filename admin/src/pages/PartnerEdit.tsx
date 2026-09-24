import { useEffect, useMemo, useRef, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { api } from '@/api/client';
import type { PartnerDetail, PartnerUpdatePayload, RiderDocument } from '@/api/types';
import { money } from '@/theme';
import { AsyncView } from '@/ui/kit';

type SectionId = 'personal' | 'vehicle' | 'bank' | 'kyc' | 'shifts' | 'audit';

const SECTIONS: { id: SectionId; num: number; label: string }[] = [
  { id: 'personal', num: 1, label: 'Personal Details' },
  { id: 'vehicle', num: 2, label: 'Vehicle & Fleet' },
  { id: 'bank', num: 3, label: 'Bank & Payout' },
  { id: 'kyc', num: 4, label: 'KYC Documents' },
  { id: 'shifts', num: 5, label: 'Shifts & Operations' },
  { id: 'audit', num: 6, label: 'Audit Trail' },
];

const VEHICLE_OPTIONS = [
  { id: 'bike', label: 'Two-Wheeler (ICE)', icon: '🏍️' },
  { id: 'scooter', label: 'Electric Scooter (EV)', icon: '⚡' },
  { id: 'bicycle', label: 'Bicycle', icon: '🚲' },
  { id: 'three_wheeler', label: 'Three-wheeler', icon: '🛺' },
];

const EQUIPMENT = [
  'Insulated Delivery Box',
  'Khana Delivery Rainwear Set',
  'Fleece Winter Jacket',
  'Thermal Bag Liner',
  'Helmet (Company Issued)',
  'Reflective Safety Vest',
];

const KYC_META: Record<string, { title: string; icon: string }> = {
  id_proof: { title: 'Aadhaar Card', icon: '🪪' },
  license: { title: 'Driving License', icon: '📄' },
  vehicle_rc: { title: 'Vehicle RC', icon: '🚗' },
  insurance: { title: 'Insurance', icon: '🛡️' },
  pan: { title: 'PAN Card', icon: '💳' },
  police_verification: { title: 'Police Verification', icon: '👮' },
};

function initials(name: string) {
  return name.split(/\s+/).filter(Boolean).slice(0, 2).map((p) => p[0]?.toUpperCase() ?? '').join('');
}

function partnerId(p: PartnerDetail) {
  return p.partner_code ?? `DM-${String(p.rider_id).padStart(4, '0')}`;
}

function fmt(iso: string | null) {
  if (!iso) return '—';
  return new Date(iso).toLocaleString('en-IN', { day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' });
}

function joinDate(iso: string) {
  return new Date(iso).toLocaleDateString('en-IN', { month: 'long', year: 'numeric' });
}

function buildForm(p: PartnerDetail): PartnerUpdatePayload {
  return {
    full_name: p.full_name,
    phone: p.phone ?? '',
    email: p.email ?? p.contact_email ?? '',
    emergency_contact: p.emergency_contact,
    operating_hub: p.operating_hub,
    fleet_tier: p.fleet_tier,
    bank_name: p.bank_name,
    bank_account_masked: p.bank_account_masked,
    ifsc_code: p.ifsc_code,
    upi_id: p.upi_id ?? '',
    upi_linked: p.upi_linked,
    vehicle_model: p.vehicle_model,
    vehicle_number: p.vehicle_number,
    license_number: p.license_number,
    vehicle_type: p.vehicle_type,
  };
}

function docStatusBadge(status: string) {
  if (status === 'accepted') return <span className="pe-doc-badge ok">Approved</span>;
  if (status === 'pending') return <span className="pe-doc-badge warn">Pending</span>;
  return <span className="pe-doc-badge warn">{status}</span>;
}

function kycCard(doc: RiderDocument | undefined, fallbackLabel: string, fallbackKey: string) {
  const meta = KYC_META[fallbackKey] ?? { title: fallbackLabel, icon: '📎' };
  const title = doc ? (KYC_META[doc.doc_type]?.title ?? doc.doc_type.replace(/_/g, ' ')) : meta.title;
  const status = doc?.status ?? 'missing';
  return (
    <div key={fallbackKey} className="pe-kyc-card">
      <div className="pe-kyc-card-top">
        <span className="pe-kyc-icon">{meta.icon}</span>
        {docStatusBadge(status)}
      </div>
      <div className="pe-kyc-title">{title}</div>
      <div className="pe-kyc-meta muted">{doc ? doc.original_name : 'Not uploaded'}</div>
      {doc && <div className="pe-kyc-meta muted">Uploaded {fmt(doc.uploaded_at)}</div>}
      <div className="pe-kyc-actions">
        <button type="button" className="link-btn" disabled={!doc}>Preview</button>
        <button type="button" className="link-btn">Update</button>
      </div>
    </div>
  );
}

export function PartnerEdit() {
  const { riderId } = useParams();
  const navigate = useNavigate();
  const id = Number(riderId);
  const [partner, setPartner] = useState<PartnerDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [form, setForm] = useState<PartnerUpdatePayload>({});
  const [draftSaved, setDraftSaved] = useState(false);
  const [busy, setBusy] = useState(false);
  const [saveErr, setSaveErr] = useState<string | null>(null);
  const [changeReason, setChangeReason] = useState('');
  const [activeSection, setActiveSection] = useState<SectionId>('personal');
  const [payoutMethod, setPayoutMethod] = useState<'imps' | 'neft'>('imps');
  const [cashoutLimit, setCashoutLimit] = useState(15000);
  const [dispatchRadius, setDispatchRadius] = useState(8.5);
  const [maxOrders, setMaxOrders] = useState(2);
  const [equipment, setEquipment] = useState<string[]>(EQUIPMENT.slice(0, 3));
  const sectionRefs = useRef<Record<SectionId, HTMLElement | null>>({
    personal: null, vehicle: null, bank: null, kyc: null, shifts: null, audit: null,
  });

  const load = () => {
    setLoading(true);
    api.partner(id).then((p) => {
      setPartner(p);
      setForm(buildForm(p));
      setMaxOrders(p.max_active_orders);
      setCashoutLimit(Math.round(p.daily_cashout_limit_cents / 100));
    }).catch((e) => setError(e.message)).finally(() => setLoading(false));
  };

  useEffect(() => { if (Number.isFinite(id)) load(); }, [id]);

  const set = <K extends keyof PartnerUpdatePayload>(key: K, value: PartnerUpdatePayload[K]) => {
    setForm((f) => ({ ...f, [key]: value }));
    setDraftSaved(false);
  };

  const dirty = useMemo(() => {
    if (!partner) return false;
    const base = buildForm(partner);
    return JSON.stringify(form) !== JSON.stringify(base) || changeReason.trim().length > 0;
  }, [partner, form, changeReason]);

  const scrollTo = (sid: SectionId) => {
    setActiveSection(sid);
    sectionRefs.current[sid]?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  };

  const saveDraft = () => {
    localStorage.setItem(`partner-edit-draft-${id}`, JSON.stringify({ form, changeReason, equipment, payoutMethod, cashoutLimit, dispatchRadius, maxOrders }));
    setDraftSaved(true);
  };

  const discard = () => {
    if (dirty && !window.confirm('Discard unsaved changes?')) return;
    navigate(`/partners/${id}`);
  };

  const submit = async () => {
    if (!partner) return;
    if (!changeReason.trim()) {
      setSaveErr('Please provide a reason for changes in the Audit Trail section.');
      scrollTo('audit');
      return;
    }
    setBusy(true);
    setSaveErr(null);
    try {
      await api.updatePartner(id, form);
      await api.addPartnerNote(id, `Profile edit: ${changeReason.trim()}`);
      localStorage.removeItem(`partner-edit-draft-${id}`);
      navigate(`/partners/${id}`);
    } catch (e) {
      setSaveErr(e instanceof Error ? e.message : 'Save failed');
      setBusy(false);
    }
  };

  const docMap = useMemo(() => {
    const m: Record<string, RiderDocument> = {};
    partner?.documents.forEach((d) => { m[d.doc_type] = d; });
    return m;
  }, [partner]);

  return (
    <div className="content pe-page">
      <AsyncView data={partner} loading={loading} error={error} onRetry={load} isEmpty={(d) => !d}>
        {(p) => (
          <>
            <div className="pe-breadcrumb">
              <Link to="/partners">OPERATIONS</Link>
              <span>›</span>
              <Link to="/partners">DELIVERY PARTNERS</Link>
              <span>›</span>
              <Link to={`/partners/${id}`}>RIDERS</Link>
              <span>›</span>
              <strong>EDIT PROFILE</strong>
            </div>

            <div className="pe-head">
              <div>
                <h1 className="pe-title">Edit Partner Profile — {p.full_name}</h1>
                <div className="pe-badges">
                  {p.account_active && <span className="pp-badge pp-badge-green">Active</span>}
                  {p.fleet_tier && <span className="pp-badge pp-badge-gold">{p.fleet_tier}</span>}
                  <span className="pp-badge pp-badge-green">Onboarded</span>
                </div>
              </div>
              <div className="pe-head-actions">
                <button type="button" className="btn secondary sm" onClick={discard}>Discard Changes</button>
                <button type="button" className="btn secondary sm" onClick={saveDraft}>{draftSaved ? 'Draft Saved' : 'Save as Draft'}</button>
                <button type="button" className="btn primary sm" onClick={submit} disabled={busy}>{busy ? 'Saving…' : 'Save Changes'}</button>
              </div>
            </div>

            <nav className="pe-section-nav" aria-label="Form sections">
              {SECTIONS.map((s) => (
                <button
                  key={s.id}
                  type="button"
                  className={`pe-section-tab ${activeSection === s.id ? 'active' : ''}`}
                  onClick={() => scrollTo(s.id)}
                >
                  <span className="pe-section-num">{s.num}</span>
                  {s.label}
                </button>
              ))}
            </nav>

            {saveErr && <div className="card profile-alert">{saveErr}</div>}

            <div className="pe-form-stack">
              <section className="pe-section" ref={(el) => { sectionRefs.current.personal = el; }}>
                <div className="pe-section-label"><span className="pe-section-num">1</span> Personal &amp; Contact Information</div>
                <div className="pe-section-body">
                  <div className="pe-personal-grid">
                    <div className="pe-photo-col">
                      <div className="lt-avatar xl">{initials(p.full_name)}</div>
                      <div className="pe-photo-name">{p.full_name}</div>
                      <div className="pe-photo-id">{partnerId(p)}</div>
                      <div className="muted" style={{ fontSize: 12 }}>Joined {joinDate(p.history[0]?.created_at ?? new Date().toISOString())}</div>
                      <button type="button" className="btn secondary sm" style={{ marginTop: 12 }}>Upload New Photo</button>
                    </div>
                    <div className="pe-fields">
                      <div className="pe-field-row">
                        <label>Full Legal Name</label>
                        <div className="pe-input-wrap">
                          <input value={form.full_name ?? ''} onChange={(e) => set('full_name', e.target.value)} />
                          <span className="pe-verified">Name Verified</span>
                        </div>
                      </div>
                      <div className="pe-field-row">
                        <label>Date of Birth</label>
                        <input type="date" defaultValue="1995-06-15" />
                        <span className="pe-hint muted">Age must be 18+ for fleet eligibility</span>
                      </div>
                      <div className="pe-field-row">
                        <label>Primary Dispatch Mobile</label>
                        <div className="pe-input-wrap">
                          <input value={form.phone ?? ''} onChange={(e) => set('phone', e.target.value)} />
                          {p.phone_verified && <span className="pe-verified">Verified</span>}
                        </div>
                        <button type="button" className="link-btn" style={{ marginTop: 4 }}>Request Number Change</button>
                      </div>
                      <div className="pe-field-row">
                        <label>Alternative Contact</label>
                        <input value={form.emergency_contact ?? ''} onChange={(e) => set('emergency_contact', e.target.value)} placeholder="Name & relationship" />
                      </div>
                      <div className="pe-field-row">
                        <label>Registered Email</label>
                        <div className="pe-input-wrap">
                          <input type="email" value={form.email ?? ''} onChange={(e) => set('email', e.target.value)} />
                          {(p.email || p.contact_email) && <span className="pe-verified">Email Confirmed</span>}
                        </div>
                      </div>
                      <div className="pe-field-row pe-field-full">
                        <label>Residential Address</label>
                        <textarea rows={2} placeholder="Flat / Street, Area" defaultValue="42, 5th Cross, Koramangala 4th Block" />
                      </div>
                      <div className="pe-field-row trio">
                        <div><label>City</label><input defaultValue="Bangalore" /></div>
                        <div><label>State</label><select defaultValue="KA"><option value="KA">Karnataka</option></select></div>
                        <div><label>Pincode</label><input defaultValue="560034" /></div>
                      </div>
                    </div>
                  </div>
                </div>
              </section>

              <section className="pe-section" ref={(el) => { sectionRefs.current.vehicle = el; }}>
                <div className="pe-section-label"><span className="pe-section-num">2</span> Vehicle &amp; Fleet Allocation</div>
                <div className="pe-section-body">
                  <div className="pe-sub-label">Vehicle Classification</div>
                  <div className="pe-vehicle-cards">
                    {VEHICLE_OPTIONS.map((v) => (
                      <button
                        key={v.id}
                        type="button"
                        className={`pe-vehicle-card ${form.vehicle_type === v.id ? 'selected' : ''}`}
                        onClick={() => set('vehicle_type', v.id)}
                      >
                        <span className="pe-vehicle-icon">{v.icon}</span>
                        <span>{v.label}</span>
                      </button>
                    ))}
                  </div>
                  <div className="pe-fields pe-fields-grid">
                    <div className="pe-field-row"><label>Vehicle Make / Model</label><input value={form.vehicle_model ?? ''} onChange={(e) => set('vehicle_model', e.target.value)} /></div>
                    <div className="pe-field-row">
                      <label>License Plate Registration</label>
                      <div className="pe-input-wrap">
                        <input value={form.vehicle_number ?? ''} onChange={(e) => set('vehicle_number', e.target.value)} />
                        <span className="pe-verified">Verified</span>
                      </div>
                    </div>
                    <div className="pe-field-row"><label>Fuel Type</label><select value={p.vehicle_fuel_type} onChange={() => {}}><option>Petrol</option><option>Electric</option><option>CNG</option></select></div>
                    <div className="pe-field-row"><label>Operating Hub</label><input value={form.operating_hub ?? ''} onChange={(e) => set('operating_hub', e.target.value)} /></div>
                    <div className="pe-field-row"><label>Partner Fleet Tier</label><input value={form.fleet_tier ?? ''} onChange={(e) => set('fleet_tier', e.target.value)} /></div>
                    <div className="pe-field-row"><label>Driving License No.</label><input value={form.license_number ?? ''} onChange={(e) => set('license_number', e.target.value)} /></div>
                  </div>
                  <div className="pe-sub-label" style={{ marginTop: 20 }}>Issued Equipment</div>
                  <div className="pe-equipment-grid">
                    {EQUIPMENT.map((item) => (
                      <label key={item} className="pe-check">
                        <input
                          type="checkbox"
                          checked={equipment.includes(item)}
                          onChange={(e) => setEquipment((prev) => e.target.checked ? [...prev, item] : prev.filter((x) => x !== item))}
                        />
                        {item}
                      </label>
                    ))}
                  </div>
                </div>
              </section>

              <section className="pe-section" ref={(el) => { sectionRefs.current.bank = el; }}>
                <div className="pe-section-label"><span className="pe-section-num">3</span> Bank &amp; Settlement Node</div>
                <div className="pe-section-body">
                  <div className="pe-warn-banner">
                    Changes to bank details may delay payout processing by 24–48 hours while penny-drop verification completes.
                  </div>
                  <div className="pe-fields pe-fields-grid">
                    <div className="pe-field-row"><label>Beneficiary Name</label><input value={form.full_name ?? ''} onChange={(e) => set('full_name', e.target.value)} /></div>
                    <div className="pe-field-row"><label>Settlement Bank</label><input value={form.bank_name ?? ''} onChange={(e) => set('bank_name', e.target.value)} placeholder="e.g. HDFC Bank" /></div>
                    <div className="pe-field-row"><label>IFSC Code</label><input value={form.ifsc_code ?? ''} onChange={(e) => set('ifsc_code', e.target.value.toUpperCase())} placeholder="HDFC0000128" maxLength={11} /></div>
                    <div className="pe-field-row">
                      <label>Account Number (last 4 digits)</label>
                      <input
                        type="text"
                        inputMode="numeric"
                        value={form.bank_account_masked ?? ''}
                        onChange={(e) => set('bank_account_masked', e.target.value.replace(/\D/g, '').slice(0, 4))}
                        placeholder="e.g. 4521"
                        maxLength={4}
                      />
                    </div>
                    <div className="pe-field-row"><label>UPI ID</label><input value={form.upi_id ?? ''} onChange={(e) => set('upi_id', e.target.value)} placeholder="partner@bank" /></div>
                    <div className="pe-field-row">
                      <label className="pe-check" style={{ marginTop: 24 }}>
                        <input type="checkbox" checked={form.upi_linked ?? false} onChange={(e) => set('upi_linked', e.target.checked)} />
                        UPI linked for instant payouts
                      </label>
                    </div>
                  </div>
                  <div className="pe-sub-label" style={{ marginTop: 16 }}>Payout Method</div>
                  <div className="pe-payout-cards">
                    <button type="button" className={`pe-payout-card ${payoutMethod === 'imps' ? 'selected' : ''}`} onClick={() => setPayoutMethod('imps')}>
                      <strong>IMPS Instant Payout</strong>
                      <span className="muted">Same-day settlement</span>
                    </button>
                    <button type="button" className={`pe-payout-card ${payoutMethod === 'neft' ? 'selected' : ''}`} onClick={() => setPayoutMethod('neft')}>
                      <strong>NEFT Batch Transfer</strong>
                      <span className="muted">Next business day</span>
                    </button>
                  </div>
                  <div className="pe-slider-row">
                    <label>Daily Cashout Limit: <strong>{money(cashoutLimit * 100)}</strong></label>
                    <input type="range" min={5000} max={50000} step={1000} value={cashoutLimit} onChange={(e) => setCashoutLimit(Number(e.target.value))} />
                  </div>
                </div>
              </section>

              <section className="pe-section" ref={(el) => { sectionRefs.current.kyc = el; }}>
                <div className="pe-section-label"><span className="pe-section-num">4</span> KYC &amp; Regulatory Compliance Documents</div>
                <div className="pe-section-body">
                  <div className="pe-kyc-grid">
                    {kycCard(docMap.id_proof, 'Aadhaar Card', 'id_proof')}
                    {kycCard(docMap.license, 'Driving License', 'license')}
                    {kycCard(docMap.vehicle_rc, 'Vehicle RC', 'vehicle_rc')}
                    {kycCard(docMap.insurance, 'Insurance', 'insurance')}
                    {kycCard(docMap.pan, 'PAN Card', 'pan')}
                    {kycCard(docMap.police_verification, 'Police Verification', 'police_verification')}
                  </div>
                </div>
              </section>

              <section className="pe-section" ref={(el) => { sectionRefs.current.shifts = el; }}>
                <div className="pe-section-label"><span className="pe-section-num">5</span> Operational Preferences &amp; Shift Management</div>
                <div className="pe-section-body">
                  <div className="pe-slider-row">
                    <label>Dispatch Radius: <strong>{dispatchRadius} km</strong></label>
                    <input type="range" min={3} max={15} step={0.5} value={dispatchRadius} onChange={(e) => setDispatchRadius(Number(e.target.value))} />
                  </div>
                  <div className="pe-field-row" style={{ maxWidth: 320, marginTop: 16 }}>
                    <label>Max Concurrent Orders</label>
                    <select value={maxOrders} onChange={(e) => setMaxOrders(Number(e.target.value))}>
                      <option value={1}>1 Simultaneous Order</option>
                      <option value={2}>2 Simultaneous Orders</option>
                      <option value={3}>3 Simultaneous Orders</option>
                    </select>
                  </div>
                  <div className="pe-shifts-grid">
                    <div>
                      <div className="pe-sub-label">Subscribed Delivery Shifts</div>
                      {['Morning (6 AM – 11 AM)', 'Lunch Peak (11 AM – 3 PM)', 'Evening Peak (5 PM – 11 PM)', 'Late Night (11 PM – 2 AM)'].map((shift) => (
                        <label key={shift} className="pe-check">
                          <input type="checkbox" defaultChecked={shift.includes('Evening')} />
                          {shift}
                        </label>
                      ))}
                    </div>
                    <div>
                      <div className="pe-sub-label">Order Handling Eligibility</div>
                      {['COD Orders', 'Prepaid Orders', 'High-Value Orders (>₹1,000)', 'Test / Training Orders'].map((item) => (
                        <label key={item} className="pe-check">
                          <input type="checkbox" defaultChecked={!item.startsWith('Test')} />
                          {item}
                        </label>
                      ))}
                    </div>
                  </div>
                </div>
              </section>

              <section className="pe-section" ref={(el) => { sectionRefs.current.audit = el; }}>
                <div className="pe-section-label"><span className="pe-section-num">6</span> Security &amp; Admin Audit Trail Record</div>
                <div className="pe-section-body">
                  <div className="pe-field-row pe-field-full">
                    <label>Reason for Changes <span className="pe-required">*</span></label>
                    <textarea
                      rows={3}
                      value={changeReason}
                      onChange={(e) => setChangeReason(e.target.value)}
                      placeholder="Describe why these profile changes are being made (required for audit compliance)"
                      maxLength={500}
                    />
                    <span className="pe-hint muted">{changeReason.length}/500 characters</span>
                  </div>
                  <div className="pe-audit-log">
                    <div className="pe-sub-label">Recent Administrative Changes</div>
                    {p.history.length === 0 ? (
                      <p className="muted">No audit events recorded.</p>
                    ) : p.history.slice(0, 5).map((ev) => (
                      <div key={ev.id} className="pe-audit-item">
                        <div><strong>{ev.event_type.replace(/_/g, ' ')}</strong> — {ev.detail || ev.reason || '—'}</div>
                        <div className="muted" style={{ fontSize: 12 }}>{fmt(ev.created_at)}</div>
                      </div>
                    ))}
                  </div>
                </div>
              </section>
            </div>

            <div className="pe-sticky-footer">
              <div className="pe-footer-status">
                <span className="pe-footer-ok">✓</span>
                All 32 form modules checked. {dirty ? 'Unsaved changes pending.' : 'No unresolved validation flags.'}
              </div>
              <div className="pe-footer-actions">
                <button type="button" className="btn secondary" onClick={discard}>Cancel</button>
                <button type="button" className="btn secondary" onClick={saveDraft}>Save Draft</button>
                <button type="button" className="btn primary" onClick={submit} disabled={busy}>{busy ? 'Saving…' : 'Save & Apply Changes'}</button>
              </div>
            </div>
          </>
        )}
      </AsyncView>
    </div>
  );
}
