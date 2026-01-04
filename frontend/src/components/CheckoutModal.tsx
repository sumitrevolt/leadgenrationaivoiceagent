/**
 * Checkout Modal Component
 * Handles Stripe and Razorpay payment flows
 */
import React, { useState, useEffect } from 'react';
import { loadStripe, Stripe } from '@stripe/stripe-js';
import { billingApi, type PricingPlan, type CheckoutSession } from '../services/api';

// Initialize Stripe
const stripePromise = loadStripe(import.meta.env.VITE_STRIPE_PUBLISHABLE_KEY || '');

interface CheckoutModalProps {
  clientId: string;
  planId?: string;
  billingCycle?: 'monthly' | 'quarterly' | 'yearly';
  onClose: () => void;
  onSuccess: () => void;
  mode?: 'subscription' | 'balance';
  balanceAmount?: number;
}

const CheckoutModal: React.FC<CheckoutModalProps> = ({
  clientId,
  planId,
  billingCycle = 'monthly',
  onClose,
  onSuccess,
  mode = 'subscription',
  balanceAmount = 5000,
}) => {
  const [step, setStep] = useState<'select' | 'payment' | 'processing' | 'success' | 'error'>('select');
  const [selectedPlan, setSelectedPlan] = useState<string | null>(planId || null);
  const [selectedCycle, setSelectedCycle] = useState<'monthly' | 'quarterly' | 'yearly'>(billingCycle);
  const [plans, setPlans] = useState<PricingPlan[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [checkoutSession, setCheckoutSession] = useState<CheckoutSession | null>(null);
  const [amount, setAmount] = useState(balanceAmount);
  const [stripe, setStripe] = useState<Stripe | null>(null);

  useEffect(() => {
    initStripe();
    if (mode === 'subscription') {
      loadPlans();
    } else {
      setLoading(false);
    }
  }, [mode]);

  const initStripe = async () => {
    const stripeInstance = await stripePromise;
    setStripe(stripeInstance);
  };

  const loadPlans = async () => {
    try {
      const data = await billingApi.getPlans();
      setPlans(data.filter(p => p.pricing_model === 'subscription' && p.id !== 'trial'));
    } catch (err) {
      console.error('Failed to load plans:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleProceedToPayment = async () => {
    setStep('processing');
    setError(null);

    try {
      let session: CheckoutSession;

      if (mode === 'subscription' && selectedPlan) {
        session = await billingApi.createCheckout(
          clientId,
          selectedPlan,
          selectedCycle,
          `${window.location.origin}/billing/success`,
          `${window.location.origin}/billing/cancel`
        );
      } else if (mode === 'balance') {
        session = await billingApi.addBalance(
          clientId,
          amount,
          `${window.location.origin}/billing/success`,
          `${window.location.origin}/billing/cancel`
        );
      } else {
        throw new Error('Invalid checkout mode');
      }

      setCheckoutSession(session);

      if (session.gateway === 'stripe' && session.checkout_url) {
        // Redirect to Stripe Checkout
        window.location.href = session.checkout_url;
      } else if (session.gateway === 'razorpay' && session.order_id && session.key_id) {
        // Open Razorpay modal
        await handleRazorpayPayment(session);
      } else {
        throw new Error('Invalid payment session');
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Payment failed');
      setStep('error');
    }
  };

  const handleRazorpayPayment = async (session: CheckoutSession) => {
    return new Promise<void>((resolve, reject) => {
      const options = {
        key: session.key_id,
        amount: session.amount * 100,
        currency: session.currency,
        name: 'AuraLeads',
        description: mode === 'subscription' 
          ? `${selectedPlan} Plan - ${selectedCycle}` 
          : 'Account Balance Top-up',
        order_id: session.order_id,
        handler: async (response: {
          razorpay_order_id: string;
          razorpay_payment_id: string;
          razorpay_signature: string;
        }) => {
          try {
            await billingApi.verifyPayment(
              clientId,
              response.razorpay_order_id,
              response.razorpay_payment_id,
              response.razorpay_signature
            );
            setStep('success');
            setTimeout(() => {
              onSuccess();
            }, 2000);
            resolve();
          } catch (err) {
            setError('Payment verification failed');
            setStep('error');
            reject(err);
          }
        },
        modal: {
          ondismiss: () => {
            setStep('select');
            reject(new Error('Payment cancelled'));
          },
        },
        prefill: {},
        theme: {
          color: '#4F46E5',
        },
      };

      // @ts-expect-error Razorpay is loaded from external script
      if (typeof window.Razorpay !== 'undefined') {
        // @ts-expect-error Razorpay is loaded from external script
        const rzp = new window.Razorpay(options);
        rzp.open();
      } else {
        // Load Razorpay script dynamically
        const script = document.createElement('script');
        script.src = 'https://checkout.razorpay.com/v1/checkout.js';
        script.onload = () => {
          // @ts-expect-error Razorpay is loaded from external script
          const rzp = new window.Razorpay(options);
          rzp.open();
        };
        script.onerror = () => {
          setError('Failed to load payment gateway');
          setStep('error');
          reject(new Error('Failed to load Razorpay'));
        };
        document.body.appendChild(script);
      }
    });
  };

  const formatCurrency = (value: number) => {
    return new Intl.NumberFormat('en-IN', {
      style: 'currency',
      currency: 'INR',
      maximumFractionDigits: 0,
    }).format(value);
  };

  const renderPlanSelection = () => (
    <div className="p-6">
      <h3 className="text-lg font-semibold text-gray-900 mb-4">Select Your Plan</h3>
      
      {/* Billing Cycle */}
      <div className="flex justify-center mb-6">
        <div className="bg-gray-100 p-1 rounded-lg inline-flex">
          {(['monthly', 'quarterly', 'yearly'] as const).map((cycle) => (
            <button
              key={cycle}
              onClick={() => setSelectedCycle(cycle)}
              className={`px-4 py-2 rounded-md text-sm font-medium transition-colors ${
                selectedCycle === cycle
                  ? 'bg-white text-indigo-600 shadow-sm'
                  : 'text-gray-600 hover:text-gray-900'
              }`}
            >
              {cycle.charAt(0).toUpperCase() + cycle.slice(1)}
            </button>
          ))}
        </div>
      </div>

      {/* Plans */}
      <div className="space-y-3">
        {plans.map((plan) => (
          <div
            key={plan.id}
            onClick={() => setSelectedPlan(plan.id)}
            className={`border-2 rounded-lg p-4 cursor-pointer transition-all ${
              selectedPlan === plan.id
                ? 'border-indigo-600 bg-indigo-50'
                : 'border-gray-200 hover:border-gray-300'
            }`}
          >
            <div className="flex justify-between items-center">
              <div>
                <h4 className="font-semibold text-gray-900">{plan.name}</h4>
                <p className="text-sm text-gray-500">
                  {typeof plan.calls_per_month === 'number' && plan.calls_per_month > 0
                    ? `${plan.calls_per_month} calls/month`
                    : 'Unlimited calls'}
                </p>
              </div>
              <div className="text-right">
                <span className="text-xl font-bold text-gray-900">
                  {formatCurrency(plan.monthly_price)}
                </span>
                <span className="text-gray-500">/mo</span>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );

  const renderBalanceTopup = () => (
    <div className="p-6">
      <h3 className="text-lg font-semibold text-gray-900 mb-4">Add Account Balance</h3>
      <p className="text-gray-500 mb-6">
        Add funds to your account for per-lead billing.
      </p>

      {/* Quick amounts */}
      <div className="grid grid-cols-3 gap-3 mb-6">
        {[5000, 10000, 25000].map((value) => (
          <button
            key={value}
            onClick={() => setAmount(value)}
            className={`p-3 rounded-lg border-2 transition-all ${
              amount === value
                ? 'border-indigo-600 bg-indigo-50 text-indigo-600'
                : 'border-gray-200 hover:border-gray-300 text-gray-700'
            }`}
          >
            {formatCurrency(value)}
          </button>
        ))}
      </div>

      {/* Custom amount */}
      <div className="mb-6">
        <label className="block text-sm font-medium text-gray-700 mb-2">
          Or enter custom amount
        </label>
        <div className="relative">
          <span className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-500">?</span>
          <input
            type="number"
            value={amount}
            onChange={(e) => setAmount(Math.max(1000, parseInt(e.target.value) || 0))}
            min={1000}
            className="w-full pl-8 pr-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500"
          />
        </div>
        <p className="text-xs text-gray-500 mt-1">Minimum amount: ?1,000</p>
      </div>

      {/* Summary */}
      <div className="bg-gray-50 rounded-lg p-4">
        <div className="flex justify-between items-center">
          <span className="text-gray-600">Amount to add</span>
          <span className="text-xl font-bold text-gray-900">{formatCurrency(amount)}</span>
        </div>
      </div>
    </div>
  );

  const renderProcessing = () => (
    <div className="p-12 text-center">
      <div className="animate-spin rounded-full h-16 w-16 border-4 border-indigo-600 border-t-transparent mx-auto mb-6"></div>
      <h3 className="text-lg font-semibold text-gray-900 mb-2">Processing Payment</h3>
      <p className="text-gray-500">Please wait while we process your payment...</p>
    </div>
  );

  const renderSuccess = () => (
    <div className="p-12 text-center">
      <div className="w-16 h-16 bg-green-100 rounded-full flex items-center justify-center mx-auto mb-6">
        <svg className="w-8 h-8 text-green-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
        </svg>
      </div>
      <h3 className="text-lg font-semibold text-gray-900 mb-2">Payment Successful!</h3>
      <p className="text-gray-500">
        {mode === 'subscription'
          ? 'Your subscription has been activated.'
          : `${formatCurrency(amount)} has been added to your account.`}
      </p>
    </div>
  );

  const renderError = () => (
    <div className="p-12 text-center">
      <div className="w-16 h-16 bg-red-100 rounded-full flex items-center justify-center mx-auto mb-6">
        <svg className="w-8 h-8 text-red-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
        </svg>
      </div>
      <h3 className="text-lg font-semibold text-gray-900 mb-2">Payment Failed</h3>
      <p className="text-gray-500 mb-6">{error || 'Something went wrong. Please try again.'}</p>
      <button
        onClick={() => setStep('select')}
        className="px-6 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 transition-colors"
      >
        Try Again
      </button>
    </div>
  );

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-2xl max-w-md w-full max-h-[90vh] overflow-y-auto">
        {/* Header */}
        <div className="p-6 border-b border-gray-200">
          <div className="flex justify-between items-center">
            <h2 className="text-xl font-bold text-gray-900">
              {mode === 'subscription' ? 'Checkout' : 'Add Balance'}
            </h2>
            <button onClick={onClose} className="text-gray-400 hover:text-gray-600">
              <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
        </div>

        {/* Content */}
        {loading ? (
          <div className="p-12 flex justify-center">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-indigo-600"></div>
          </div>
        ) : (
          <>
            {step === 'select' && mode === 'subscription' && renderPlanSelection()}
            {step === 'select' && mode === 'balance' && renderBalanceTopup()}
            {step === 'processing' && renderProcessing()}
            {step === 'success' && renderSuccess()}
            {step === 'error' && renderError()}
          </>
        )}

        {/* Footer */}
        {step === 'select' && !loading && (
          <div className="p-6 border-t border-gray-200 bg-gray-50 rounded-b-2xl">
            <div className="flex justify-end gap-3">
              <button
                onClick={onClose}
                className="px-4 py-2 border border-gray-300 text-gray-700 rounded-lg hover:bg-gray-100 transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={handleProceedToPayment}
                disabled={(mode === 'subscription' && !selectedPlan) || (mode === 'balance' && amount < 1000)}
                className="px-6 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
              >
                <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
                </svg>
                Proceed to Payment
              </button>
            </div>
            <p className="text-xs text-gray-500 text-center mt-4">
              Secure payment powered by Stripe & Razorpay
            </p>
          </div>
        )}
      </div>
    </div>
  );
};

export default CheckoutModal;
