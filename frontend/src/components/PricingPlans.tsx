/**
 * Pricing Plans Component
 * Displays pricing plans with plan selection and checkout
 */
import React, { useState, useEffect } from 'react';
import { billingApi, type PricingPlan } from '../services/api';

interface PricingPlansProps {
  clientId?: string;
  onSelectPlan?: (planId: string, billingCycle: string) => void;
  showCheckout?: boolean;
}

const PricingPlans: React.FC<PricingPlansProps> = ({
  clientId,
  onSelectPlan,
  showCheckout = true,
}) => {
  const [plans, setPlans] = useState<PricingPlan[]>([]);
  const [loading, setLoading] = useState(true);
  const [billingCycle, setBillingCycle] = useState<'monthly' | 'quarterly' | 'yearly'>('monthly');
  const [selectedPlan, setSelectedPlan] = useState<string | null>(null);
  const [pricingDetails, setPricingDetails] = useState<Record<string, {
    total: number;
    per_month: number;
    discount: number;
    discount_percentage: number;
  }>>({});

  useEffect(() => {
    loadPlans();
  }, []);

  useEffect(() => {
    if (plans.length > 0) {
      loadPricingDetails();
    }
  }, [plans, billingCycle]);

  const loadPlans = async () => {
    try {
      const data = await billingApi.getPlans();
      // Filter out trial and per-lead plans for display
      const displayPlans = data.filter(p => 
        p.pricing_model === 'subscription' && p.id !== 'trial'
      );
      setPlans(displayPlans);
    } catch (err) {
      console.error('Failed to load plans:', err);
    } finally {
      setLoading(false);
    }
  };

  const loadPricingDetails = async () => {
    const details: typeof pricingDetails = {};
    for (const plan of plans) {
      try {
        const pricing = await billingApi.calculatePricing(plan.id, billingCycle);
        details[plan.id] = {
          total: pricing.total,
          per_month: pricing.per_month,
          discount: pricing.discount,
          discount_percentage: pricing.discount_percentage,
        };
      } catch {
        // Use default pricing
        details[plan.id] = {
          total: plan.monthly_price,
          per_month: plan.monthly_price,
          discount: 0,
          discount_percentage: 0,
        };
      }
    }
    setPricingDetails(details);
  };

  const handleSelectPlan = (planId: string) => {
    setSelectedPlan(planId);
    if (onSelectPlan) {
      onSelectPlan(planId, billingCycle);
    }
  };

  const handleCheckout = async (planId: string) => {
    if (!clientId) {
      console.error('Client ID required for checkout');
      return;
    }

    try {
      const session = await billingApi.createCheckout(
        clientId,
        planId,
        billingCycle,
        `${window.location.origin}/billing/success`,
        `${window.location.origin}/billing/cancel`
      );

      if (session.checkout_url) {
        window.location.href = session.checkout_url;
      } else if (session.order_id && session.key_id) {
        // Handle Razorpay
        const options = {
          key: session.key_id,
          amount: session.amount * 100,
          currency: session.currency,
          name: 'AuraLeads',
          description: `${planId} Plan - ${billingCycle}`,
          order_id: session.order_id,
          handler: async (response: { razorpay_order_id: string; razorpay_payment_id: string; razorpay_signature: string }) => {
            try {
              await billingApi.verifyPayment(
                clientId,
                response.razorpay_order_id,
                response.razorpay_payment_id,
                response.razorpay_signature
              );
              window.location.href = '/billing/success';
            } catch (err) {
              console.error('Payment verification failed:', err);
            }
          },
          theme: { color: '#4F46E5' },
        };
        // @ts-expect-error Razorpay loaded from script
        const rzp = new window.Razorpay(options);
        rzp.open();
      }
    } catch (err) {
      console.error('Checkout failed:', err);
    }
  };

  const formatPrice = (amount: number) => {
    return new Intl.NumberFormat('en-IN', {
      style: 'currency',
      currency: 'INR',
      maximumFractionDigits: 0,
    }).format(amount);
  };

  const getPlanHighlight = (planId: string) => {
    if (planId === 'growth') return true;
    return false;
  };

  if (loading) {
    return (
      <div className="flex justify-center py-12">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-indigo-600"></div>
      </div>
    );
  }

  return (
    <div className="py-12">
      {/* Header */}
      <div className="text-center mb-12">
        <h2 className="text-3xl font-bold text-gray-900 mb-4">
          Simple, Transparent Pricing
        </h2>
        <p className="text-lg text-gray-600 max-w-2xl mx-auto">
          Choose the plan that works best for your business. All plans include our AI voice agent technology.
        </p>
      </div>

      {/* Billing Cycle Toggle */}
      <div className="flex justify-center mb-10">
        <div className="bg-gray-100 p-1 rounded-xl inline-flex">
          {(['monthly', 'quarterly', 'yearly'] as const).map((cycle) => (
            <button
              key={cycle}
              onClick={() => setBillingCycle(cycle)}
              className={`px-6 py-3 rounded-lg text-sm font-medium transition-all ${
                billingCycle === cycle
                  ? 'bg-white text-indigo-600 shadow-md'
                  : 'text-gray-600 hover:text-gray-900'
              }`}
            >
              {cycle === 'monthly' && 'Monthly'}
              {cycle === 'quarterly' && (
                <>
                  Quarterly
                  <span className="ml-2 px-2 py-0.5 bg-green-100 text-green-700 rounded-full text-xs">
                    Save 10%
                  </span>
                </>
              )}
              {cycle === 'yearly' && (
                <>
                  Yearly
                  <span className="ml-2 px-2 py-0.5 bg-green-100 text-green-700 rounded-full text-xs">
                    Save 20%
                  </span>
                </>
              )}
            </button>
          ))}
        </div>
      </div>

      {/* Plans Grid */}
      <div className="max-w-6xl mx-auto px-4">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
          {plans.map((plan) => {
            const isHighlighted = getPlanHighlight(plan.id);
            const pricing = pricingDetails[plan.id];
            const isSelected = selectedPlan === plan.id;

            return (
              <div
                key={plan.id}
                className={`relative rounded-2xl p-8 transition-all ${
                  isHighlighted
                    ? 'bg-indigo-600 text-white shadow-xl scale-105'
                    : isSelected
                    ? 'bg-white border-2 border-indigo-600 shadow-lg'
                    : 'bg-white border border-gray-200 shadow-md hover:shadow-lg'
                }`}
              >
                {isHighlighted && (
                  <div className="absolute -top-4 left-1/2 -translate-x-1/2">
                    <span className="bg-gradient-to-r from-yellow-400 to-orange-500 text-white text-sm font-semibold px-4 py-1 rounded-full">
                      Most Popular
                    </span>
                  </div>
                )}

                <h3 className={`text-xl font-bold mb-2 ${isHighlighted ? 'text-white' : 'text-gray-900'}`}>
                  {plan.name}
                </h3>

                <div className="mb-6">
                  <div className="flex items-baseline">
                    <span className={`text-4xl font-bold ${isHighlighted ? 'text-white' : 'text-gray-900'}`}>
                      {formatPrice(pricing?.per_month || plan.monthly_price)}
                    </span>
                    <span className={`ml-2 ${isHighlighted ? 'text-indigo-200' : 'text-gray-500'}`}>
                      /month
                    </span>
                  </div>
                  {pricing?.discount_percentage > 0 && (
                    <div className={`mt-1 text-sm ${isHighlighted ? 'text-indigo-200' : 'text-green-600'}`}>
                      {billingCycle === 'quarterly' && `Billed ${formatPrice(pricing.total)} quarterly`}
                      {billingCycle === 'yearly' && `Billed ${formatPrice(pricing.total)} yearly`}
                    </div>
                  )}
                </div>

                {/* Limits */}
                <div className={`mb-6 pb-6 border-b ${isHighlighted ? 'border-indigo-500' : 'border-gray-200'}`}>
                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <p className={`text-2xl font-bold ${isHighlighted ? 'text-white' : 'text-gray-900'}`}>
                        {plan.calls_per_month === 0 ? '?' : plan.calls_per_month.toLocaleString()}
                      </p>
                      <p className={`text-sm ${isHighlighted ? 'text-indigo-200' : 'text-gray-500'}`}>
                        Calls/month
                      </p>
                    </div>
                    <div>
                      <p className={`text-2xl font-bold ${isHighlighted ? 'text-white' : 'text-gray-900'}`}>
                        {plan.leads_per_month === 0 ? '?' : plan.leads_per_month.toLocaleString()}
                      </p>
                      <p className={`text-sm ${isHighlighted ? 'text-indigo-200' : 'text-gray-500'}`}>
                        Leads/month
                      </p>
                    </div>
                  </div>
                </div>

                {/* Features */}
                <ul className="space-y-3 mb-8">
                  {plan.features.map((feature, idx) => (
                    <li key={idx} className="flex items-start">
                      <svg
                        className={`w-5 h-5 mr-3 flex-shrink-0 ${
                          isHighlighted ? 'text-indigo-200' : 'text-green-500'
                        }`}
                        fill="currentColor"
                        viewBox="0 0 20 20"
                      >
                        <path
                          fillRule="evenodd"
                          d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z"
                          clipRule="evenodd"
                        />
                      </svg>
                      <span className={`text-sm ${isHighlighted ? 'text-indigo-100' : 'text-gray-600'}`}>
                        {feature}
                      </span>
                    </li>
                  ))}
                </ul>

                {/* CTA Button */}
                {showCheckout && clientId ? (
                  <button
                    onClick={() => handleCheckout(plan.id)}
                    className={`w-full py-3 px-6 rounded-lg font-semibold transition-all ${
                      isHighlighted
                        ? 'bg-white text-indigo-600 hover:bg-gray-100'
                        : 'bg-indigo-600 text-white hover:bg-indigo-700'
                    }`}
                  >
                    Get Started
                  </button>
                ) : (
                  <button
                    onClick={() => handleSelectPlan(plan.id)}
                    className={`w-full py-3 px-6 rounded-lg font-semibold transition-all ${
                      isSelected
                        ? 'bg-indigo-600 text-white'
                        : isHighlighted
                        ? 'bg-white text-indigo-600 hover:bg-gray-100'
                        : 'bg-indigo-600 text-white hover:bg-indigo-700'
                    }`}
                  >
                    {isSelected ? 'Selected' : 'Select Plan'}
                  </button>
                )}
              </div>
            );
          })}
        </div>
      </div>

      {/* Enterprise CTA */}
      <div className="mt-16 text-center">
        <div className="bg-gradient-to-r from-gray-900 to-gray-800 rounded-2xl p-8 max-w-3xl mx-auto">
          <h3 className="text-2xl font-bold text-white mb-2">Need a Custom Solution?</h3>
          <p className="text-gray-300 mb-6">
            Contact us for custom pricing, unlimited usage, and dedicated support.
          </p>
          <button className="bg-white text-gray-900 px-8 py-3 rounded-lg font-semibold hover:bg-gray-100 transition-colors">
            Contact Sales
          </button>
        </div>
      </div>

      {/* FAQ Section */}
      <div className="mt-16 max-w-3xl mx-auto px-4">
        <h3 className="text-2xl font-bold text-gray-900 text-center mb-8">
          Frequently Asked Questions
        </h3>
        <div className="space-y-4">
          <details className="bg-white rounded-lg shadow-sm border border-gray-200 p-4">
            <summary className="font-medium text-gray-900 cursor-pointer">
              What payment methods do you accept?
            </summary>
            <p className="mt-3 text-gray-600">
              We accept all major credit/debit cards, UPI, Net Banking, and Wallets for Indian customers. 
              International customers can pay via Stripe using credit/debit cards.
            </p>
          </details>
          <details className="bg-white rounded-lg shadow-sm border border-gray-200 p-4">
            <summary className="font-medium text-gray-900 cursor-pointer">
              Can I change my plan later?
            </summary>
            <p className="mt-3 text-gray-600">
              Yes! You can upgrade or downgrade your plan at any time. Changes take effect immediately, 
              and we'll prorate your billing accordingly.
            </p>
          </details>
          <details className="bg-white rounded-lg shadow-sm border border-gray-200 p-4">
            <summary className="font-medium text-gray-900 cursor-pointer">
              What happens if I exceed my limits?
            </summary>
            <p className="mt-3 text-gray-600">
              We'll notify you when you're approaching your limits. You can upgrade your plan or 
              add additional capacity as needed. We never cut off your service abruptly.
            </p>
          </details>
          <details className="bg-white rounded-lg shadow-sm border border-gray-200 p-4">
            <summary className="font-medium text-gray-900 cursor-pointer">
              Is there a free trial?
            </summary>
            <p className="mt-3 text-gray-600">
              Yes! All new accounts get a 7-day free trial with 100 calls included. 
              No credit card required to start.
            </p>
          </details>
        </div>
      </div>
    </div>
  );
};

export default PricingPlans;
