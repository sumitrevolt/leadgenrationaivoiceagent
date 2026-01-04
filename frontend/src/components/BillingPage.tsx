/**
 * Billing Page Component
 * Subscription management, usage tracking, and payment history
 */
import React, { useState, useEffect } from 'react';
import { billingApi, type Subscription, type UsageStats, type Invoice } from '../services/api';

interface BillingPageProps {
  clientId: string;
}

const BillingPage: React.FC<BillingPageProps> = ({ clientId }) => {
  const [subscription, setSubscription] = useState<Subscription | null>(null);
  const [usage, setUsage] = useState<UsageStats | null>(null);
  const [invoices, setInvoices] = useState<Invoice[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showUpgradeModal, setShowUpgradeModal] = useState(false);
  const [showCancelModal, setShowCancelModal] = useState(false);

  useEffect(() => {
    loadBillingData();
  }, [clientId]);

  const loadBillingData = async () => {
    setLoading(true);
    setError(null);
    try {
      const [subData, usageData, invoiceData] = await Promise.all([
        billingApi.getSubscription(clientId).catch(() => null),
        billingApi.getUsage(clientId),
        billingApi.getInvoices(clientId, 5),
      ]);
      setSubscription(subData);
      setUsage(usageData);
      setInvoices(invoiceData);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load billing data');
    } finally {
      setLoading(false);
    }
  };

  const handleCancelSubscription = async (reason: string) => {
    try {
      await billingApi.cancelSubscription(clientId, reason);
      await loadBillingData();
      setShowCancelModal(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to cancel subscription');
    }
  };

  const formatCurrency = (amount: number, currency: string = 'INR') => {
    return new Intl.NumberFormat('en-IN', {
      style: 'currency',
      currency,
    }).format(amount);
  };

  const formatDate = (dateString: string | undefined) => {
    if (!dateString) return '-';
    return new Date(dateString).toLocaleDateString('en-IN', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
    });
  };

  const getStatusColor = (status: string) => {
    const colors: Record<string, string> = {
      active: 'bg-green-100 text-green-800',
      trial: 'bg-blue-100 text-blue-800',
      past_due: 'bg-red-100 text-red-800',
      cancelled: 'bg-gray-100 text-gray-800',
      paused: 'bg-yellow-100 text-yellow-800',
      paid: 'bg-green-100 text-green-800',
      open: 'bg-yellow-100 text-yellow-800',
      draft: 'bg-gray-100 text-gray-800',
    };
    return colors[status] || 'bg-gray-100 text-gray-800';
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-indigo-600"></div>
      </div>
    );
  }

  return (
    <div className="max-w-6xl mx-auto px-4 py-8">
      <h1 className="text-3xl font-bold text-gray-900 mb-8">Billing & Subscription</h1>

      {error && (
        <div className="mb-6 bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg">
          {error}
        </div>
      )}

      {/* Current Subscription Card */}
      <div className="bg-white rounded-xl shadow-md p-6 mb-8">
        <div className="flex justify-between items-start mb-6">
          <div>
            <h2 className="text-xl font-semibold text-gray-900">Current Plan</h2>
            {subscription ? (
              <div className="mt-2">
                <span className="text-2xl font-bold text-indigo-600">{subscription.plan_name}</span>
                <span className={`ml-3 px-3 py-1 rounded-full text-sm font-medium ${getStatusColor(subscription.status)}`}>
                  {subscription.status.charAt(0).toUpperCase() + subscription.status.slice(1)}
                </span>
              </div>
            ) : (
              <p className="text-gray-500 mt-2">No active subscription</p>
            )}
          </div>
          <div className="flex gap-3">
            {subscription && subscription.status !== 'cancelled' && (
              <>
                <button
                  onClick={() => setShowUpgradeModal(true)}
                  className="px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 transition-colors"
                >
                  Upgrade Plan
                </button>
                <button
                  onClick={() => setShowCancelModal(true)}
                  className="px-4 py-2 border border-red-300 text-red-600 rounded-lg hover:bg-red-50 transition-colors"
                >
                  Cancel
                </button>
              </>
            )}
            {!subscription && (
              <button
                onClick={() => setShowUpgradeModal(true)}
                className="px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 transition-colors"
              >
                Subscribe Now
              </button>
            )}
          </div>
        </div>

        {subscription && (
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            <div className="bg-gray-50 rounded-lg p-4">
              <p className="text-sm text-gray-500">Billing Cycle</p>
              <p className="text-lg font-semibold text-gray-900 capitalize">{subscription.billing_cycle}</p>
              <p className="text-sm text-gray-500 mt-1">
                {formatCurrency(subscription.base_price, subscription.currency)}/month
              </p>
            </div>
            <div className="bg-gray-50 rounded-lg p-4">
              <p className="text-sm text-gray-500">Current Period</p>
              <p className="text-lg font-semibold text-gray-900">
                {formatDate(subscription.current_period_start)} - {formatDate(subscription.current_period_end)}
              </p>
            </div>
            {subscription.trial_ends_at && (
              <div className="bg-blue-50 rounded-lg p-4">
                <p className="text-sm text-blue-600">Trial Ends</p>
                <p className="text-lg font-semibold text-blue-900">{formatDate(subscription.trial_ends_at)}</p>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Usage Stats */}
      {usage && (
        <div className="bg-white rounded-xl shadow-md p-6 mb-8">
          <h2 className="text-xl font-semibold text-gray-900 mb-6">Usage This Period</h2>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            {/* Calls Usage */}
            <div className="bg-gradient-to-br from-blue-50 to-indigo-50 rounded-lg p-4">
              <div className="flex justify-between items-start mb-2">
                <p className="text-sm font-medium text-gray-700">Calls Made</p>
                <span className="text-xs text-gray-500">
                  {usage.calls_limit === 'Unlimited' ? 'Unlimited' : `${usage.calls_used} / ${usage.calls_limit}`}
                </span>
              </div>
              <p className="text-3xl font-bold text-indigo-600">{usage.calls_used}</p>
              {typeof usage.calls_limit === 'number' && usage.calls_limit > 0 && (
                <div className="mt-3">
                  <div className="w-full bg-gray-200 rounded-full h-2">
                    <div
                      className="bg-indigo-600 h-2 rounded-full transition-all"
                      style={{ width: `${Math.min((usage.calls_used / usage.calls_limit) * 100, 100)}%` }}
                    ></div>
                  </div>
                  <p className="text-xs text-gray-500 mt-1">
                    {typeof usage.calls_remaining === 'number' ? `${usage.calls_remaining} remaining` : 'Unlimited'}
                  </p>
                </div>
              )}
            </div>

            {/* Leads Generated */}
            <div className="bg-gradient-to-br from-green-50 to-emerald-50 rounded-lg p-4">
              <div className="flex justify-between items-start mb-2">
                <p className="text-sm font-medium text-gray-700">Leads Generated</p>
                <span className="text-xs text-gray-500">
                  {usage.leads_limit === 'Unlimited' ? 'Unlimited' : `${usage.leads_generated} / ${usage.leads_limit}`}
                </span>
              </div>
              <p className="text-3xl font-bold text-green-600">{usage.leads_generated}</p>
              {typeof usage.leads_limit === 'number' && usage.leads_limit > 0 && (
                <div className="mt-3">
                  <div className="w-full bg-gray-200 rounded-full h-2">
                    <div
                      className="bg-green-600 h-2 rounded-full transition-all"
                      style={{ width: `${Math.min((usage.leads_generated / usage.leads_limit) * 100, 100)}%` }}
                    ></div>
                  </div>
                  <p className="text-xs text-gray-500 mt-1">
                    {typeof usage.leads_remaining === 'number' ? `${usage.leads_remaining} remaining` : 'Unlimited'}
                  </p>
                </div>
              )}
            </div>

            {/* Appointments */}
            <div className="bg-gradient-to-br from-purple-50 to-pink-50 rounded-lg p-4">
              <p className="text-sm font-medium text-gray-700 mb-2">Appointments Booked</p>
              <p className="text-3xl font-bold text-purple-600">{usage.appointments_booked}</p>
              <p className="text-xs text-gray-500 mt-3">No limit</p>
            </div>
          </div>

          {usage.period_start && usage.period_end && (
            <p className="text-sm text-gray-500 mt-4">
              Period: {formatDate(usage.period_start)} - {formatDate(usage.period_end)}
            </p>
          )}
        </div>
      )}

      {/* Recent Invoices */}
      <div className="bg-white rounded-xl shadow-md p-6">
        <div className="flex justify-between items-center mb-6">
          <h2 className="text-xl font-semibold text-gray-900">Recent Invoices</h2>
          {invoices.length > 0 && (
            <button className="text-indigo-600 hover:text-indigo-800 text-sm font-medium">
              View All
            </button>
          )}
        </div>

        {invoices.length === 0 ? (
          <div className="text-center py-8 text-gray-500">
            <svg className="mx-auto h-12 w-12 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
            </svg>
            <p className="mt-2">No invoices yet</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b border-gray-200">
                  <th className="text-left py-3 px-4 text-sm font-medium text-gray-500">Invoice</th>
                  <th className="text-left py-3 px-4 text-sm font-medium text-gray-500">Date</th>
                  <th className="text-left py-3 px-4 text-sm font-medium text-gray-500">Amount</th>
                  <th className="text-left py-3 px-4 text-sm font-medium text-gray-500">Status</th>
                  <th className="text-right py-3 px-4 text-sm font-medium text-gray-500">Actions</th>
                </tr>
              </thead>
              <tbody>
                {invoices.map((invoice) => (
                  <tr key={invoice.id} className="border-b border-gray-100 hover:bg-gray-50">
                    <td className="py-4 px-4">
                      <span className="font-medium text-gray-900">{invoice.invoice_number}</span>
                    </td>
                    <td className="py-4 px-4 text-gray-600">{formatDate(invoice.invoice_date)}</td>
                    <td className="py-4 px-4">
                      <span className="font-medium text-gray-900">
                        {formatCurrency(invoice.total, invoice.currency)}
                      </span>
                    </td>
                    <td className="py-4 px-4">
                      <span className={`px-2 py-1 rounded-full text-xs font-medium ${getStatusColor(invoice.status)}`}>
                        {invoice.status.charAt(0).toUpperCase() + invoice.status.slice(1)}
                      </span>
                    </td>
                    <td className="py-4 px-4 text-right">
                      {invoice.pdf_url && (
                        <a
                          href={invoice.pdf_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-indigo-600 hover:text-indigo-800 text-sm font-medium"
                        >
                          Download PDF
                        </a>
                      )}
                      {invoice.hosted_url && !invoice.pdf_url && (
                        <a
                          href={invoice.hosted_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-indigo-600 hover:text-indigo-800 text-sm font-medium"
                        >
                          View Invoice
                        </a>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Upgrade Modal */}
      {showUpgradeModal && (
        <PricingModal
          clientId={clientId}
          onClose={() => setShowUpgradeModal(false)}
          onSuccess={() => {
            setShowUpgradeModal(false);
            loadBillingData();
          }}
        />
      )}

      {/* Cancel Modal */}
      {showCancelModal && (
        <CancelModal
          onClose={() => setShowCancelModal(false)}
          onConfirm={handleCancelSubscription}
        />
      )}
    </div>
  );
};

// Pricing Modal Component
interface PricingModalProps {
  clientId: string;
  onClose: () => void;
  onSuccess: () => void;
}

const PricingModal: React.FC<PricingModalProps> = ({ clientId, onClose, onSuccess }) => {
  const [plans, setPlans] = useState<Array<{
    id: string;
    name: string;
    monthly_price: number;
    features: string[];
    calls_per_month: number | string;
    leads_per_month: number | string;
  }>>([]);
  const [selectedPlan, setSelectedPlan] = useState<string | null>(null);
  const [billingCycle, setBillingCycle] = useState<'monthly' | 'quarterly' | 'yearly'>('monthly');
  const [loading, setLoading] = useState(true);
  const [processing, setProcessing] = useState(false);

  useEffect(() => {
    loadPlans();
  }, []);

  const loadPlans = async () => {
    try {
      const data = await billingApi.getPlans();
      setPlans(data.filter(p => p.id !== 'trial' && p.id !== 'per_lead'));
    } catch (err) {
      console.error('Failed to load plans:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleCheckout = async () => {
    if (!selectedPlan) return;
    
    setProcessing(true);
    try {
      const session = await billingApi.createCheckout(
        clientId,
        selectedPlan,
        billingCycle,
        `${window.location.origin}/billing/success`,
        `${window.location.origin}/billing/cancel`
      );

      if (session.checkout_url) {
        // Stripe - redirect to checkout
        window.location.href = session.checkout_url;
      } else if (session.order_id && session.key_id) {
        // Razorpay - open modal
        const options = {
          key: session.key_id,
          amount: session.amount * 100,
          currency: session.currency,
          name: 'AuraLeads',
          description: `${selectedPlan} Plan - ${billingCycle}`,
          order_id: session.order_id,
          handler: async (response: { razorpay_order_id: string; razorpay_payment_id: string; razorpay_signature: string }) => {
            try {
              await billingApi.verifyPayment(
                clientId,
                response.razorpay_order_id,
                response.razorpay_payment_id,
                response.razorpay_signature
              );
              onSuccess();
            } catch (err) {
              console.error('Payment verification failed:', err);
            }
          },
          prefill: {},
          theme: { color: '#4F46E5' },
        };

        // @ts-expect-error Razorpay is loaded from script
        const rzp = new window.Razorpay(options);
        rzp.open();
      }
    } catch (err) {
      console.error('Checkout failed:', err);
    } finally {
      setProcessing(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-2xl max-w-4xl w-full max-h-[90vh] overflow-y-auto">
        <div className="p-6 border-b border-gray-200">
          <div className="flex justify-between items-center">
            <h2 className="text-2xl font-bold text-gray-900">Choose Your Plan</h2>
            <button onClick={onClose} className="text-gray-400 hover:text-gray-600">
              <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>

          {/* Billing Cycle Toggle */}
          <div className="flex justify-center mt-6">
            <div className="bg-gray-100 p-1 rounded-lg inline-flex">
              {(['monthly', 'quarterly', 'yearly'] as const).map((cycle) => (
                <button
                  key={cycle}
                  onClick={() => setBillingCycle(cycle)}
                  className={`px-4 py-2 rounded-md text-sm font-medium transition-colors ${
                    billingCycle === cycle
                      ? 'bg-white text-indigo-600 shadow-sm'
                      : 'text-gray-600 hover:text-gray-900'
                  }`}
                >
                  {cycle.charAt(0).toUpperCase() + cycle.slice(1)}
                  {cycle === 'yearly' && <span className="ml-1 text-green-600">-20%</span>}
                </button>
              ))}
            </div>
          </div>
        </div>

        <div className="p-6">
          {loading ? (
            <div className="flex justify-center py-12">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-indigo-600"></div>
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
              {plans.map((plan) => (
                <div
                  key={plan.id}
                  onClick={() => setSelectedPlan(plan.id)}
                  className={`border-2 rounded-xl p-6 cursor-pointer transition-all ${
                    selectedPlan === plan.id
                      ? 'border-indigo-600 bg-indigo-50'
                      : 'border-gray-200 hover:border-gray-300'
                  }`}
                >
                  <h3 className="text-lg font-semibold text-gray-900">{plan.name}</h3>
                  <div className="mt-4">
                    <span className="text-3xl font-bold text-gray-900">
                      ?{plan.monthly_price.toLocaleString()}
                    </span>
                    <span className="text-gray-500">/month</span>
                  </div>
                  <ul className="mt-6 space-y-3">
                    <li className="flex items-center text-sm text-gray-600">
                      <svg className="w-4 h-4 mr-2 text-green-500" fill="currentColor" viewBox="0 0 20 20">
                        <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
                      </svg>
                      {plan.calls_per_month === 0 ? 'Unlimited' : plan.calls_per_month} calls/month
                    </li>
                    <li className="flex items-center text-sm text-gray-600">
                      <svg className="w-4 h-4 mr-2 text-green-500" fill="currentColor" viewBox="0 0 20 20">
                        <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
                      </svg>
                      {plan.leads_per_month === 0 ? 'Unlimited' : plan.leads_per_month} leads/month
                    </li>
                    {plan.features.slice(0, 4).map((feature, idx) => (
                      <li key={idx} className="flex items-center text-sm text-gray-600">
                        <svg className="w-4 h-4 mr-2 text-green-500" fill="currentColor" viewBox="0 0 20 20">
                          <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
                        </svg>
                        {feature}
                      </li>
                    ))}
                  </ul>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="p-6 border-t border-gray-200 bg-gray-50 rounded-b-2xl">
          <div className="flex justify-end gap-3">
            <button
              onClick={onClose}
              className="px-6 py-2 border border-gray-300 text-gray-700 rounded-lg hover:bg-gray-100 transition-colors"
            >
              Cancel
            </button>
            <button
              onClick={handleCheckout}
              disabled={!selectedPlan || processing}
              className="px-6 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {processing ? 'Processing...' : 'Continue to Payment'}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

// Cancel Modal Component
interface CancelModalProps {
  onClose: () => void;
  onConfirm: (reason: string) => void;
}

const CancelModal: React.FC<CancelModalProps> = ({ onClose, onConfirm }) => {
  const [reason, setReason] = useState('');
  const [processing, setProcessing] = useState(false);

  const handleConfirm = async () => {
    setProcessing(true);
    await onConfirm(reason);
    setProcessing(false);
  };

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-xl max-w-md w-full p-6">
        <h2 className="text-xl font-semibold text-gray-900 mb-4">Cancel Subscription</h2>
        <p className="text-gray-600 mb-4">
          Are you sure you want to cancel your subscription? You'll continue to have access until the end of your current billing period.
        </p>
        <textarea
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          placeholder="Please tell us why you're cancelling (optional)"
          className="w-full border border-gray-300 rounded-lg p-3 mb-4 focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500"
          rows={3}
        />
        <div className="flex justify-end gap-3">
          <button
            onClick={onClose}
            className="px-4 py-2 border border-gray-300 text-gray-700 rounded-lg hover:bg-gray-100 transition-colors"
          >
            Keep Subscription
          </button>
          <button
            onClick={handleConfirm}
            disabled={processing}
            className="px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 transition-colors disabled:opacity-50"
          >
            {processing ? 'Cancelling...' : 'Cancel Subscription'}
          </button>
        </div>
      </div>
    </div>
  );
};

export default BillingPage;
