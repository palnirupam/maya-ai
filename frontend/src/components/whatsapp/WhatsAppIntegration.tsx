import React, { useState, useEffect } from 'react';
import { backendHttpUrl } from '../../services/websocket';
import { XCircle, ShieldAlert, Loader2, Smartphone, AlertTriangle } from 'lucide-react';

interface WhatsAppStatusData {
  tos_accepted: boolean;
  state: string;
  ready: boolean;
  phone_number?: string;
  last_error?: string;
}

export const WhatsAppIntegration: React.FC = () => {
  const [statusData, setStatusData] = useState<WhatsAppStatusData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [consentSubmitting, setConsentSubmitting] = useState(false);

  const fetchStatus = async () => {
    try {
      setLoading(true);
      const res = await fetch(`${backendHttpUrl}/status/whatsapp`);
      if (!res.ok) throw new Error('Failed to fetch WhatsApp status');
      const data = await res.json();
      setStatusData(data);
      setError('');
    } catch (err: any) {
      setError(err.message || 'Failed to connect to backend.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchStatus();
    const interval = setInterval(() => {
      if (statusData?.tos_accepted) {
        fetchStatus();
      }
    }, 5000);
    return () => clearInterval(interval);
  }, [statusData?.tos_accepted]);

  const handleConsent = async (accepted: boolean) => {
    try {
      setConsentSubmitting(true);
      const res = await fetch(`${backendHttpUrl}/whatsapp/consent`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ accepted }),
      });
      if (!res.ok) throw new Error('Failed to save consent');
      await fetchStatus();
    } catch (err: any) {
      setError(err.message || 'Failed to save consent');
    } finally {
      setConsentSubmitting(false);
    }
  };

  if (loading && !statusData) {
    return (
      <div className="flex flex-col items-center justify-center p-8 space-y-4">
        <Loader2 className="animate-spin text-green-500" size={32} />
        <p className="text-sm text-slate-400">Loading WhatsApp Status...</p>
      </div>
    );
  }

  if (error && !statusData) {
    return (
      <div className="p-4 bg-red-500/10 border border-red-500/30 rounded-xl">
        <p className="text-red-400 text-sm flex items-center gap-2">
          <XCircle size={16} /> {error}
        </p>
        <button onClick={fetchStatus} className="mt-3 px-3 py-1 bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs rounded transition-colors">
          Retry
        </button>
      </div>
    );
  }

  const { tos_accepted, state, phone_number, last_error } = statusData || {};

  return (
    <div className="space-y-6 mt-1">
      <div>
        <h3 className="text-white font-semibold text-sm mb-0.5">WhatsApp Integration</h3>
        <p className="text-slate-400 text-xs mb-3">Allow Maya to read and reply to your WhatsApp messages securely.</p>
      </div>

      {!tos_accepted ? (
        <div className="p-5 bg-slate-800/60 border border-slate-700/80 rounded-xl space-y-4">
          <div className="flex items-start gap-3">
            <ShieldAlert className="text-yellow-500 shrink-0 mt-0.5" size={24} />
            <div>
              <h4 className="text-sm font-bold text-slate-200">Terms of Service & Privacy</h4>
              <p className="text-xs text-slate-400 mt-1 leading-relaxed">
                By enabling WhatsApp integration, you allow Maya AI to read your incoming WhatsApp messages 
                locally. All data is processed end-to-end locally and encrypted on your device. 
                Maya will NEVER send a message without your explicit permission, unless you authorize specific 
                contacts via Telegram.
              </p>
            </div>
          </div>
          
          <div className="flex gap-3 justify-end pt-2 border-t border-slate-700/50">
            <button 
              onClick={() => handleConsent(false)}
              disabled={consentSubmitting}
              className="px-4 py-2 text-xs font-semibold text-slate-300 hover:text-white hover:bg-slate-700 rounded-lg transition-colors"
            >
              Decline
            </button>
            <button 
              onClick={() => handleConsent(true)}
              disabled={consentSubmitting}
              className="px-4 py-2 text-xs font-semibold bg-green-600 hover:bg-green-500 text-white rounded-lg transition-colors flex items-center gap-2"
            >
              {consentSubmitting && <Loader2 size={14} className="animate-spin" />}
              I Agree, Enable WhatsApp
            </button>
          </div>
        </div>
      ) : (
        <div className="space-y-4">
          <div className="p-4 bg-slate-800/30 border border-slate-700/50 rounded-xl space-y-3">
            <div className="flex items-center justify-between">
              <h4 className="text-xs font-bold text-slate-300 flex items-center gap-2">
                <Smartphone size={16} className="text-green-400" /> WhatsApp Service Status
              </h4>
              <span className={`px-2 py-0.5 rounded text-[10px] font-semibold ${
                state === 'READY' ? 'bg-green-500/15 text-green-400' :
                state === 'PAIRING' ? 'bg-yellow-500/15 text-yellow-400' :
                'bg-slate-500/15 text-slate-400'
              }`}>
                {state || 'UNKNOWN'}
              </span>
            </div>

            {phone_number && (
              <p className="text-xs text-slate-400">
                Connected Number: <span className="font-mono text-slate-200 font-semibold">{phone_number}</span>
              </p>
            )}

            {last_error && (
              <div className="p-2 bg-red-500/10 border border-red-500/20 rounded mt-2">
                <p className="text-[11px] text-red-400 flex items-center gap-1">
                  <AlertTriangle size={12} /> {last_error}
                </p>
              </div>
            )}
            
            <p className="text-[11px] text-slate-500 mt-2">
              Note: You can control pairing and access permissions entirely via the Maya Telegram Bot.
            </p>
          </div>
          
          <div className="flex justify-end">
             <button 
                onClick={() => handleConsent(false)}
                disabled={consentSubmitting}
                className="px-3 py-1.5 text-xs font-semibold text-red-400 bg-red-500/10 border border-red-500/20 hover:bg-red-500/20 rounded-lg transition-colors"
              >
                Revoke Consent & Disable
              </button>
          </div>
        </div>
      )}
    </div>
  );
};
