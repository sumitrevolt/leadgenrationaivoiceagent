import { useEffect, useMemo, useState } from 'react';
import { Modal, } from '@/components/ui/Modal';
import { Badge, Button, Field, Input, Select, Textarea } from '@/components/ui/primitives';
import type { Lead, LeadInput, LeadSource, LeadStatus, LeadTemperature, Niche } from '@/types';
import { titleCase } from '@/lib/utils';

const NICHES: Niche[] = [
  'salon',
  'clinic',
  'gym',
  'real_estate',
  'coaching',
  'restaurant',
  'boutique',
  'automobile',
];
const STATUSES: LeadStatus[] = [
  'new',
  'enriched',
  'contacted',
  'qualified',
  'nurturing',
  'converted',
  'disqualified',
];
const SOURCES: LeadSource[] = [
  'google_maps',
  'website_audit',
  'seo_page',
  'referral',
  'campaign',
  'manual',
];
const OWNERS = ['Sumit', 'Riya', 'Field Agent', 'Unassigned'];
const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/;
const PHONE_RE = /^[6-9]\d{9}$/;

export type FormValues = LeadInput;
export type FormErrors = Partial<Record<keyof FormValues, string>>;

export function emptyLead(): FormValues {
  return {
    name: '',
    businessName: '',
    phone: '',
    email: '',
    city: '',
    state: '',
    niche: 'salon',
    source: 'manual',
    status: 'new',
    temperature: 'cold',
    score: 40,
    owner: 'Unassigned',
    notes: '',
    lastContactedAt: null,
  };
}

export function validateField(field: keyof FormValues, values: FormValues): string | undefined {
  switch (field) {
    case 'name':
      if (!values.name.trim()) return 'Contact name is required.';
      if (values.name.trim().length < 2) return 'Name must be at least 2 characters.';
      return undefined;
    case 'businessName':
      if (!values.businessName.trim()) return 'Business name is required.';
      if (values.businessName.trim().length < 2) return 'Business name is too short.';
      return undefined;
    case 'phone': {
      const digits = values.phone.replace(/\D/g, '');
      if (!digits) return 'Phone number is required.';
      if (!PHONE_RE.test(digits)) return 'Enter a valid 10-digit Indian mobile number.';
      return undefined;
    }
    case 'email':
      if (values.email.trim() && !EMAIL_RE.test(values.email.trim()))
        return 'Enter a valid email address.';
      return undefined;
    case 'city':
      if (!values.city.trim()) return 'City is required.';
      return undefined;
    case 'state':
      if (!values.state.trim()) return 'State is required.';
      return undefined;
    case 'score':
      if (values.score < 0 || values.score > 100) return 'Score must be between 0 and 100.';
      return undefined;
    case 'notes':
      if (values.notes.length > 500) return 'Notes cannot exceed 500 characters.';
      return undefined;
    default:
      return undefined;
  }
}

export function validateAll(values: FormValues): FormErrors {
  const fields: (keyof FormValues)[] = [
    'name',
    'businessName',
    'phone',
    'email',
    'city',
    'state',
    'score',
    'notes',
  ];
  const errors: FormErrors = {};
  fields.forEach((f) => {
    const message = validateField(f, values);
    if (message) errors[f] = message;
  });
  return errors;
}

export function temperatureFor(score: number): LeadTemperature {
  return score >= 72 ? 'hot' : score >= 45 ? 'warm' : 'cold';
}

export function LeadFormModal({
  open,
  onClose,
  onSubmit,
  initial,
  submitting,
}: {
  open: boolean;
  onClose: () => void;
  onSubmit: (values: FormValues) => void;
  initial?: Lead | null;
  submitting: boolean;
}) {
  const [values, setValues] = useState<FormValues>(emptyLead);
  const [errors, setErrors] = useState<FormErrors>({});
  const [touched, setTouched] = useState<Partial<Record<keyof FormValues, boolean>>>({});
  const [submitAttempted, setSubmitAttempted] = useState(false);

  useEffect(() => {
    if (!open) return;
    setValues(initial ? { ...initial } : emptyLead());
    setErrors({});
    setTouched({});
    setSubmitAttempted(false);
  }, [open, initial]);

  const liveErrors = useMemo(() => {
    // Only surface errors for fields the user has touched (or after a submit attempt).
    const all = validateAll(values);
    const shown: FormErrors = {};
    (Object.keys(all) as (keyof FormValues)[]).forEach((k) => {
      if (submitAttempted || touched[k]) shown[k] = all[k];
    });
    return shown;
  }, [values, touched, submitAttempted]);

  const isValid = Object.keys(validateAll(values)).length === 0;

  function set<K extends keyof FormValues>(key: K, value: FormValues[K]) {
    setValues((prev) => ({ ...prev, [key]: value }));
    if (key === 'score') {
      setValues((prev) => ({ ...prev, temperature: temperatureFor(Number(value)) }));
    }
  }

  function blur(key: keyof FormValues) {
    setTouched((prev) => ({ ...prev, [key]: true }));
  }

  function handleSubmit() {
    setSubmitAttempted(true);
    const all = validateAll(values);
    if (Object.keys(all).length > 0) {
      setErrors(all);
      return;
    }
    onSubmit({ ...values, temperature: temperatureFor(values.score) });
  }

  return (
    <Modal
      open={open}
      onClose={onClose}
      size="lg"
      title={initial ? `Edit ${initial.name}` : 'Create lead'}
      description={
        initial
          ? `Update the record for ${initial.id}.`
          : 'Add a prospect manually. Duplicate phone numbers are rejected.'
      }
      closeOnBackdrop={!submitting}
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={submitting}>
            Cancel
          </Button>
          <Button onClick={handleSubmit} loading={submitting} disabled={submitting || !isValid}>
            {initial ? 'Save changes' : 'Create lead'}
          </Button>
        </>
      }
    >
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <Field label="Contact name" htmlFor="name" required error={liveErrors.name}>
          <Input
            id="name"
            value={values.name}
            invalid={Boolean(liveErrors.name)}
            onChange={(e) => set('name', e.target.value)}
            onBlur={() => blur('name')}
            placeholder="e.g. Priya Sharma"
          />
        </Field>

        <Field label="Business name" htmlFor="businessName" required error={liveErrors.businessName}>
          <Input
            id="businessName"
            value={values.businessName}
            invalid={Boolean(liveErrors.businessName)}
            onChange={(e) => set('businessName', e.target.value)}
            onBlur={() => blur('businessName')}
            placeholder="e.g. Glow Salon"
          />
        </Field>

        <Field
          label="Phone"
          htmlFor="phone"
          required
          error={liveErrors.phone}
          hint="10-digit Indian mobile number"
        >
          <Input
            id="phone"
            inputMode="numeric"
            value={values.phone}
            invalid={Boolean(liveErrors.phone)}
            onChange={(e) => set('phone', e.target.value.replace(/[^\d\s+]/g, ''))}
            onBlur={() => blur('phone')}
            placeholder="9876543210"
          />
        </Field>

        <Field label="Email" htmlFor="email" error={liveErrors.email} hint="Optional">
          <Input
            id="email"
            type="email"
            value={values.email}
            invalid={Boolean(liveErrors.email)}
            onChange={(e) => set('email', e.target.value)}
            onBlur={() => blur('email')}
            placeholder="owner@business.in"
          />
        </Field>

        <Field label="City" htmlFor="city" required error={liveErrors.city}>
          <Input
            id="city"
            value={values.city}
            invalid={Boolean(liveErrors.city)}
            onChange={(e) => set('city', e.target.value)}
            onBlur={() => blur('city')}
            placeholder="Pune"
          />
        </Field>

        <Field label="State" htmlFor="state" required error={liveErrors.state}>
          <Input
            id="state"
            value={values.state}
            invalid={Boolean(liveErrors.state)}
            onChange={(e) => set('state', e.target.value)}
            onBlur={() => blur('state')}
            placeholder="Maharashtra"
          />
        </Field>

        <Field label="Niche" htmlFor="niche" required>
          <Select
            id="niche"
            value={values.niche}
            onChange={(e) => set('niche', e.target.value as Niche)}
          >
            {NICHES.map((n) => (
              <option key={n} value={n}>
                {titleCase(n)}
              </option>
            ))}
          </Select>
        </Field>

        <Field label="Source" htmlFor="source" required>
          <Select
            id="source"
            value={values.source}
            onChange={(e) => set('source', e.target.value as LeadSource)}
          >
            {SOURCES.map((s) => (
              <option key={s} value={s}>
                {titleCase(s)}
              </option>
            ))}
          </Select>
        </Field>

        <Field label="Status" htmlFor="status" required>
          <Select
            id="status"
            value={values.status}
            onChange={(e) => set('status', e.target.value as LeadStatus)}
          >
            {STATUSES.map((s) => (
              <option key={s} value={s}>
                {titleCase(s)}
              </option>
            ))}
          </Select>
        </Field>

        <Field label="Owner" htmlFor="owner">
          <Select id="owner" value={values.owner} onChange={(e) => set('owner', e.target.value)}>
            {OWNERS.map((o) => (
              <option key={o} value={o}>
                {o}
              </option>
            ))}
          </Select>
        </Field>

        <div className="sm:col-span-2">
          <Field
            label={`Score — ${values.score}`}
            htmlFor="score"
            error={liveErrors.score}
            hint="Temperature is derived from the score (hot ≥ 72, warm ≥ 45)."
          >
            <div className="flex items-center gap-3">
              <input
                id="score"
                type="range"
                min={0}
                max={100}
                value={values.score}
                onChange={(e) => set('score', Number(e.target.value))}
                className="h-2 w-full cursor-pointer appearance-none rounded-full bg-elevated accent-[rgb(var(--brand))]"
              />
              <Badge
                tone={
                  temperatureFor(values.score) === 'hot'
                    ? 'danger'
                    : temperatureFor(values.score) === 'warm'
                      ? 'warn'
                      : 'info'
                }
                dot
              >
                {temperatureFor(values.score)}
              </Badge>
            </div>
          </Field>
        </div>

        <div className="sm:col-span-2">
          <Field
            label="Notes"
            htmlFor="notes"
            error={liveErrors.notes}
            hint={`${values.notes.length}/500`}
          >
            <Textarea
              id="notes"
              value={values.notes}
              invalid={Boolean(liveErrors.notes)}
              onChange={(e) => set('notes', e.target.value)}
              onBlur={() => blur('notes')}
              placeholder="Context from calls, WhatsApp or site audit…"
            />
          </Field>
        </div>
      </div>

      {submitAttempted && Object.keys(errors).length > 0 && (
        <p className="mt-4 rounded-lg border border-danger/30 bg-danger/10 px-3 py-2 text-xs text-danger">
          {Object.keys(errors).length} field{Object.keys(errors).length > 1 ? 's' : ''} need attention
          before saving.
        </p>
      )}
    </Modal>
  );
}
