import React, { useState } from 'react';
import { backendHttpUrl } from '../../services/websocket';
import { AlertTriangle, Key, Loader2, CheckCircle } from 'lucide-react';

export const RecoveryModal: React.FC<{
  isOpen: boolean;
  onSuccess: () => void;
}> = ({ isOpen, onSuccess }) => {
  const [oldKey, setOldKey] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState(false);

  if (!isOpen) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!oldKey.trim()) return;

    setLoading(true);
    setError('');
    
    try {
      const res = await fetch(`${backendHttpUrl}/settings/recover`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ old_key: oldKey.trim() })
      });
      
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Recovery failed');
      
      setSuccess(true);
      setTimeout(() => {
        onSuccess();
      }, 3000);
    } catch (err: any) {
      setError(err.message || 'Failed to submit recovery key');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/80 backdrop-blur-md">
      <div className="bg-slate-900 border border-red-500/30 shadow-2xl rounded-2xl w-[500px] p-6 text-white">
        {success ? (
          <div className="text-center py-8 space-y-4">
            <CheckCircle className="mx-auto text-green-500" size={64} />
            <h2 className="text-xl font-bold text-white">Recovery Successful</h2>
            <p className="text-slate-400">Database migrated successfully. Please restart Maya AI.</p>
          </div>
        ) : (
          <>
            <div className="flex items-center gap-3 mb-4">
              <AlertTriangle className="text-yellow-500" size={32} />
              <h2 className="text-lg font-bold">Key Unreadable (Recovery Required)</h2>
            </div>
            
            <p className="text-sm text-slate-300 mb-6 leading-relaxed">
              Maya could not decrypt your database. This happens if the system hardware signature changed 
              or if the encryption salt file is missing. If you have your previous <code className="bg-black/30 px-1 py-0.5 rounded text-yellow-400">.fernet_key</code>, 
              please enter it below to recover your data.
            </p>

            <form onSubmit={handleSubmit} className="space-y-4">
              <div>
                <label className="block text-xs font-semibold text-slate-400 mb-1">
                  Legacy Key (e.g. from .fernet_key)
                </label>
                <div className="relative">
                  <Key className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500" size={16} />
                  <input
                    type="text"
                    value={oldKey}
                    onChange={(e) => setOldKey(e.target.value)}
                    placeholder="Paste the key here..."
                    className="w-full bg-slate-950 border border-slate-800 rounded-lg py-2 pl-9 pr-3 text-sm focus:outline-none focus:border-primary/50 text-white font-mono placeholder:font-sans transition-colors"
                  />
                </div>
              </div>

              {error && (
                <div className="p-3 bg-red-500/10 border border-red-500/20 rounded-lg">
                  <p className="text-xs text-red-400">{error}</p>
                </div>
              )}

              <div className="pt-4 flex justify-end gap-3">
                <button
                  type="submit"
                  disabled={loading || !oldKey.trim()}
                  className="px-5 py-2 bg-primary hover:bg-primary/90 text-primary-foreground text-sm font-semibold rounded-lg transition-all disabled:opacity-50 flex items-center gap-2"
                >
                  {loading ? <Loader2 size={16} className="animate-spin" /> : 'Recover Data'}
                </button>
              </div>
            </form>
          </>
        )}
      </div>
    </div>
  );
};
