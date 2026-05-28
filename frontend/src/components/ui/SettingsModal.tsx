import React, { useState, useEffect } from 'react';
import {
  X, Key, Shield, Lock, Eye, EyeOff,
  CheckCircle, XCircle, Loader2, Volume2, Send,
} from 'lucide-react';

interface Props { isOpen: boolean; onClose: () => void; }
type Tab = 'providers' | 'voice' | 'permissions' | 'telegram';
type SaveStatus = 'idle' | 'testing' | 'saving' | 'success' | 'error';

export const SettingsModal: React.FC<Props> = ({ isOpen, onClose }) => {
  const [activeTab, setActiveTab] = useState<Tab>('providers');

  // Gemini
  const [geminiKey, setGeminiKey]       = useState('');
  const [showGemini, setShowGemini]     = useState(false);
  const [geminiStatus, setGeminiStatus] = useState<SaveStatus>('idle');
  const [geminiError, setGeminiError]   = useState('');
  const [geminiConfigured, setGeminiConfigured] = useState(false);

  // ElevenLabs
  const [elevenlabsKey, setElevenlabsKey] = useState('');
  const [showElevenlabs, setShowElevenlabs] = useState(false);
  const [elevenlabsVoiceId, setElevenlabsVoiceId] = useState('');
  const [elevenlabsModelId, setElevenlabsModelId] = useState('eleven_multilingual_v2');
  const [elevenlabsStatus, setElevenlabsStatus] = useState<SaveStatus>('idle');
  const [elevenlabsError, setElevenlabsError] = useState('');
  const [elevenlabsConfigured, setElevenlabsConfigured] = useState(false);
  const [ttsPrimaryProvider, setTtsPrimaryProvider] = useState('edge');

  // Permissions
  const [perms, setPerms] = useState({
    browser: false,
    filesystem: false,
    terminal: false,
    system: false,
    auto_approve: false,
    web_search: false,
  });

  // Telegram
  const [telegramEnabled, setTelegramEnabled] = useState(false);
  const [telegramToken, setTelegramToken] = useState('');
  const [showTelegramToken, setShowTelegramToken] = useState(false);
  const [telegramStatus, setTelegramStatus] = useState<SaveStatus>('idle');
  const [telegramError, setTelegramError] = useState('');
  const [telegramConfigured, setTelegramConfigured] = useState(false);
  const [telegramPaired, setTelegramPaired] = useState(false);
  const [telegramChatId, setTelegramChatId] = useState('');
  const [telegramPairingCode, setTelegramPairingCode] = useState('');

  useEffect(() => {
    if (!isOpen) return;
    fetch('http://127.0.0.1:8000/settings/status')
      .then(r => r.json())
      .then(data => {
        if (data.gemini_configured) {
          setGeminiConfigured(true);
          setGeminiKey('••••••••••••••••••••••••••••••••••••••••');
        }
        if (data.elevenlabs_configured) {
          setElevenlabsConfigured(true);
          setElevenlabsKey('••••••••••••••••••••••••••••••••••••••••');
        }
        if (data.elevenlabs_voice_id) {
          setElevenlabsVoiceId(data.elevenlabs_voice_id);
        }
        if (data.elevenlabs_model_id) {
          setElevenlabsModelId(data.elevenlabs_model_id);
        }
        if (data.tts_primary_provider) {
          setTtsPrimaryProvider(data.tts_primary_provider);
        }
        if (data.permissions) {
          setPerms({
            browser: !!data.permissions.browser,
            filesystem: !!data.permissions.filesystem,
            terminal: !!data.permissions.terminal,
            system: !!data.permissions.system,
            auto_approve: !!data.permissions.auto_approve,
            web_search: !!data.permissions.web_search,
          });
        }
      })
      .catch(console.error);

    fetch('http://127.0.0.1:8000/settings/telegram')
      .then(r => r.json())
      .then(data => {
        setTelegramEnabled(!!data.enabled);
        if (data.token_configured) {
          setTelegramConfigured(true);
          setTelegramToken('••••••••••••••••••••••••••••••••••••••••');
        }
        setTelegramPaired(!!data.paired);
        setTelegramChatId(data.chat_id || '');
        setTelegramPairingCode(data.pairing_code || '');
      })
      .catch(console.error);
  }, [isOpen]);

  // ── Gemini ─────────────────────────────────────────────────────────────────
  const saveGeminiKey = async () => {
    if (!geminiKey || geminiKey.includes('•')) return;
    setGeminiStatus('testing'); setGeminiError('');
    try {
      const tr = await fetch('http://127.0.0.1:8000/settings/test-key', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ gemini_key: geminiKey }),
      });
      if (!tr.ok) { const e = await tr.json(); throw new Error(e.detail || 'Invalid key'); }
      setGeminiStatus('saving');
      await fetch('http://127.0.0.1:8000/settings/keys', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ gemini_key: geminiKey }),
      });
      setGeminiStatus('success'); setGeminiConfigured(true);
      setTimeout(() => setGeminiStatus('idle'), 3000);
    } catch (e: any) { setGeminiError(e.message); setGeminiStatus('error'); }
  };

  const saveElevenlabsSettings = async () => {
    if (!elevenlabsKey) return;
    setElevenlabsStatus('testing'); setElevenlabsError('');
    try {
      // Validate key if it was changed (doesn't contain bullets)
      if (!elevenlabsKey.includes('•')) {
        const tr = await fetch('http://127.0.0.1:8000/settings/test-key', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ elevenlabs_key: elevenlabsKey }),
        });
        if (!tr.ok) { const e = await tr.json(); throw new Error(e.detail || 'Invalid ElevenLabs key'); }
      }
      
      setElevenlabsStatus('saving');
      const payload: any = {
        elevenlabs_voice_id: elevenlabsVoiceId,
        elevenlabs_model_id: elevenlabsModelId
      };
      if (!elevenlabsKey.includes('•')) {
        payload.elevenlabs_key = elevenlabsKey;
      }
      
      const sr = await fetch('http://127.0.0.1:8000/settings/keys', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      if (!sr.ok) throw new Error('Failed to save ElevenLabs keys');
      
      setElevenlabsStatus('success'); setElevenlabsConfigured(true);
      if (!elevenlabsKey.includes('•')) {
        setElevenlabsKey('••••••••••••••••••••••••••••••••••••••••');
      }
      setTimeout(() => setElevenlabsStatus('idle'), 3000);
    } catch (e: any) { setElevenlabsError(e.message); setElevenlabsStatus('error'); }
  };

  const changePrimaryProvider = async (provider: string) => {
    setTtsPrimaryProvider(provider);
    try {
      await fetch('http://127.0.0.1:8000/settings/keys', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ tts_primary_provider: provider })
      });
    } catch (e) {
      console.error("Failed to save primary TTS provider:", e);
    }
  };

  const togglePermission = async (key: keyof typeof perms) => {
    const newVal = !perms[key];
    setPerms(prev => ({ ...prev, [key]: newVal }));
    try {
      await fetch('http://127.0.0.1:8000/settings/permissions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ [key]: newVal })
      });
    } catch (e) {
      console.error("Failed to save permission:", e);
    }
  };

  const saveTelegramSettings = async () => {
    setTelegramStatus('saving'); setTelegramError('');
    try {
      const payload: any = { enabled: telegramEnabled };
      if (telegramToken && !telegramToken.includes('•')) {
        payload.bot_token = telegramToken;
      }
      const r = await fetch('http://127.0.0.1:8000/settings/telegram', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      if (!r.ok) throw new Error('Failed to save Telegram settings');
      setTelegramStatus('success');
      if (telegramToken && !telegramToken.includes('•')) {
        setTelegramConfigured(true);
      }
      // Refresh pairing code / status
      const res = await fetch('http://127.0.0.1:8000/settings/telegram');
      const data = await res.json();
      setTelegramPaired(!!data.paired);
      setTelegramChatId(data.chat_id || '');
      setTelegramPairingCode(data.pairing_code || '');
      setTimeout(() => setTelegramStatus('idle'), 3000);
    } catch (e: any) { setTelegramError(e.message); setTelegramStatus('error'); }
  };

  const resetTelegramPairing = async () => {
    try {
      const r = await fetch('http://127.0.0.1:8000/settings/telegram/reset', { method: 'POST' });
      if (!r.ok) throw new Error('Failed to reset pairing');
      const res = await fetch('http://127.0.0.1:8000/settings/telegram');
      const data = await res.json();
      setTelegramPaired(false);
      setTelegramChatId('');
      setTelegramPairingCode(data.pairing_code || '');
    } catch (e) {
      console.error(e);
    }
  };

  if (!isOpen) return null;

  const tabs: { id: Tab; label: string; icon: React.ReactNode }[] = [
    { id: 'providers', label: 'AI Providers', icon: <Key size={15} /> },
    { id: 'voice',     label: 'Voice & TTS',  icon: <Volume2 size={15} /> },
    { id: 'permissions', label: 'Permissions',  icon: <Shield size={15} /> },
    { id: 'telegram',   label: 'Telegram Bot', icon: <Send size={15} /> },
  ];

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm">
      <div className="bg-slate-900 border border-slate-700/80 shadow-2xl rounded-2xl w-[660px] max-h-[540px] flex overflow-hidden">

        {/* Sidebar */}
        <div className="w-[190px] bg-slate-800/60 p-4 border-r border-slate-700/60 flex flex-col gap-1 shrink-0">
          <h2 className="text-sm font-bold text-white mb-4 px-2 tracking-wide">⚙️ Settings</h2>
          {tabs.map(t => (
            <button key={t.id} onClick={() => setActiveTab(t.id)}
              className={`flex items-center gap-2.5 px-3 py-2.5 rounded-xl text-sm text-left transition-all ${
                activeTab === t.id
                  ? 'bg-violet-500/20 text-violet-300 font-medium'
                  : 'text-slate-400 hover:bg-slate-700/50 hover:text-white'
              }`}>
              {t.icon} {t.label}
            </button>
          ))}
        </div>

        {/* Content */}
        <div className="flex-1 p-6 overflow-y-auto relative">
          <button onClick={onClose} className="absolute top-4 right-4 text-slate-500 hover:text-white transition-colors">
            <X size={18} />
          </button>

          {/* ── AI Providers ── */}
          {activeTab === 'providers' && (
            <div className="space-y-5 mt-1">
              <div>
                <h3 className="text-white font-semibold text-sm mb-0.5">Google Gemini</h3>
                <p className="text-slate-400 text-xs mb-2">Maya's brain — required for conversations.</p>
                <KeyInputField value={geminiKey} onChange={setGeminiKey}
                  show={showGemini} onToggleShow={() => setShowGemini(v => !v)}
                  placeholder="AIzaSy..." configured={geminiConfigured} />
                <div className="flex items-center gap-3 mt-2">
                  <ActionButton onClick={saveGeminiKey} status={geminiStatus}
                    idleLabel="Test & Save" loadingLabel={geminiStatus === 'testing' ? 'Testing...' : 'Saving...'} />
                  <StatusText status={geminiStatus} error={geminiError} />
                </div>
              </div>
            </div>
          )}

          {/* ── Voice & TTS ── */}
          {activeTab === 'voice' && (
            <div className="space-y-4 mt-1">
              {/* Primary Voice Engine */}
              <div>
                <h3 className="text-white font-semibold text-sm mb-0.5">Primary Voice Engine</h3>
                <p className="text-slate-400 text-xs mb-2">Choose the active engine for Maya's speech output.</p>
                <select value={ttsPrimaryProvider} onChange={e => changePrimaryProvider(e.target.value)}
                  className="w-full bg-slate-950 border border-slate-700/80 text-white text-sm rounded-xl px-3 py-2.5 focus:outline-none focus:ring-1 focus:ring-violet-500 transition-all cursor-pointer">
                  <option value="edge">Microsoft Edge TTS (Free, Fast, Built-in)</option>
                  <option value="elevenlabs">ElevenLabs / cvoice.ai (Cloud Clone Voice)</option>
                  <option value="gpt_sovits">GPT-SoVITS (Local Offline Clone Voice)</option>
                </select>
              </div>

              {/* ElevenLabs Settings */}
              <div>
                <h3 className="text-white font-semibold text-sm mb-0.5">ElevenLabs Clone Voice</h3>
                <p className="text-slate-400 text-xs mb-2">Configure cloud voice cloning for high-quality emotional speech.</p>
                
                <div className="space-y-3 bg-slate-800/40 p-4 border border-slate-700/40 rounded-xl">
                  {/* API Key */}
                  <div>
                    <label className="block text-[11px] font-semibold text-slate-400 mb-1">ElevenLabs API Key</label>
                    <KeyInputField value={elevenlabsKey} onChange={setElevenlabsKey}
                      show={showElevenlabs} onToggleShow={() => setShowElevenlabs(v => !v)}
                      placeholder="Enter XI API Key..." configured={elevenlabsConfigured} />
                  </div>
                  
                  {/* Voice ID & Model ID Grid */}
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <label className="block text-[11px] font-semibold text-slate-400 mb-1">Voice ID</label>
                      <input type="text" value={elevenlabsVoiceId} onChange={e => setElevenlabsVoiceId(e.target.value)}
                        placeholder="e.g. 21m00Tcm4TlvD..."
                        className="w-full bg-slate-950 border border-slate-700 text-white text-sm rounded-lg px-3 py-2 focus:outline-none focus:ring-1 focus:ring-violet-500 placeholder:text-slate-700" />
                    </div>
                    <div>
                      <label className="block text-[11px] font-semibold text-slate-400 mb-1">Model ID</label>
                      <select value={elevenlabsModelId} onChange={e => setElevenlabsModelId(e.target.value)}
                        className="w-full bg-slate-950 border border-slate-700 text-white text-sm rounded-lg px-3 py-2 focus:outline-none focus:ring-1 focus:ring-violet-500">
                        <option value="eleven_multilingual_v2">Multilingual v2 (Best for BN/HI)</option>
                        <option value="eleven_flash_v2_5">Flash v2.5 (Fastest)</option>
                        <option value="eleven_monolingual_v1">Monolingual v1 (English)</option>
                      </select>
                    </div>
                  </div>
                  
                  {/* Action Buttons */}
                  <div className="flex items-center gap-3 pt-1">
                    <ActionButton onClick={saveElevenlabsSettings} status={elevenlabsStatus}
                      idleLabel="Test & Save Voice" loadingLabel={elevenlabsStatus === 'testing' ? 'Testing...' : 'Saving...'} />
                    <StatusText status={elevenlabsStatus} error={elevenlabsError} />
                  </div>
                </div>
              </div>

              {/* Local Offline Fallbacks */}
              <div className="bg-slate-800/20 border border-slate-700/30 rounded-xl p-3">
                <p className="text-slate-500 text-[11px] font-semibold mb-1.5">🔊 Offline/Backup Voice Engines</p>
                <div className="grid grid-cols-3 gap-2 text-xs">
                  {[
                    ['Bengali', 'Edge TTS', 'Tanishaa'],
                    ['Hindi',   'Edge TTS', 'Swara'],
                    ['English', 'Edge TTS', 'Neerja'],
                  ].map(([lang, engine, voice]) => (
                    <div key={lang} className="text-center p-2 bg-slate-800/40 border border-slate-700/20 rounded-lg">
                      <p className="text-slate-300 font-medium">{lang}</p>
                      <p className="text-slate-400 text-[10px]">{engine}</p>
                      <p className="text-slate-500 text-[9px]">{voice}</p>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}

          {/* ── Permissions ── */}
          {activeTab === 'permissions' && (
            <div className="space-y-4 mt-1">
              <div>
                <h3 className="text-white font-semibold text-sm">System Access Control</h3>
                <p className="text-slate-400 text-xs mb-3">Enable or disable advanced capabilities. Red options give Maya full OS control.</p>
              </div>

              <PermissionToggle 
                label="Web & Browser Automation" 
                desc="Allow Maya to open websites and search the web."
                checked={perms.browser} 
                onChange={() => togglePermission('browser')} 
              />
              <PermissionToggle 
                label="Background Web Search" 
                desc="Allow Maya to search the web and read text summaries headlessly."
                checked={perms.web_search} 
                onChange={() => togglePermission('web_search')} 
              />
              <PermissionToggle 
                label="File System Access" 
                desc="Allow Maya to read, write, or delete files on your drive."
                checked={perms.filesystem} 
                onChange={() => togglePermission('filesystem')} 
              />
              <PermissionToggle 
                label="Python & Terminal Execution" 
                desc="Allow Maya to write and run arbitrary scripts in the background."
                checked={perms.terminal} 
                onChange={() => togglePermission('terminal')} 
                danger
              />
              <PermissionToggle 
                label="System & Window Management" 
                desc="Allow Maya to close apps, change volume, or shutdown."
                checked={perms.system} 
                onChange={() => togglePermission('system')} 
                danger
              />
              <PermissionToggle 
                label="⚡ God Mode (Full Power)" 
                desc="Bypass approval cards. Run scripts and OS commands instantly."
                checked={perms.auto_approve} 
                onChange={() => togglePermission('auto_approve')} 
                danger
              />

              <div className="mt-4 p-3 bg-red-500/10 border border-red-500/30 rounded-xl">
                <p className="text-red-400 text-xs flex items-center gap-2">
                  <Shield size={14} /> 
                  Danger actions always require explicit 1-click approval via popup, even if enabled here.
                </p>
              </div>
            </div>
          )}

          {/* ── Telegram Bot ── */}
          {activeTab === 'telegram' && (
            <div className="space-y-5 mt-1">
              <div>
                <h3 className="text-white font-semibold text-sm mb-0.5">Telegram Bot Control</h3>
                <p className="text-slate-400 text-xs mb-3">Command Maya AI from your phone using Telegram (like OpenClaw).</p>
              </div>

              {/* Enable Toggle */}
              <div className="flex items-center justify-between p-3 bg-slate-800/50 rounded-xl border border-slate-700/50">
                <div className="flex-1 pr-4">
                  <h4 className="text-sm font-medium text-slate-200">Enable Telegram Bot</h4>
                  <p className="text-[11px] text-slate-500 mt-0.5">Turn the background bot service on or off.</p>
                </div>
                <button 
                  onClick={() => setTelegramEnabled(v => !v)}
                  className={`w-10 h-5 rounded-full relative transition-colors ${telegramEnabled ? 'bg-cyan-500' : 'bg-slate-700'}`}
                >
                  <div className={`absolute top-0.5 w-4 h-4 bg-white rounded-full transition-transform ${telegramEnabled ? 'translate-x-5' : 'translate-x-1'}`} />
                </button>
              </div>

              {/* Bot Token Input */}
              <div>
                <h4 className="text-xs font-semibold text-slate-400 mb-1.5">Bot API Token (from @BotFather)</h4>
                <KeyInputField value={telegramToken} onChange={setTelegramToken}
                  show={showTelegramToken} onToggleShow={() => setShowTelegramToken(v => !v)}
                  placeholder="1234567890:ABCdefGhIJKlmNoPQRsTUVwxyZ..." configured={telegramConfigured} />
                <div className="flex items-center gap-3 mt-2">
                  <ActionButton onClick={saveTelegramSettings} status={telegramStatus}
                    idleLabel="Save Configuration" loadingLabel="Saving..." />
                  <StatusText status={telegramStatus} error={telegramError} />
                </div>
              </div>

              {/* Pairing Status */}
              {telegramConfigured && (
                <div className="p-4 bg-slate-800/30 border border-slate-700/50 rounded-xl space-y-3">
                  <div className="flex items-center justify-between">
                    <h4 className="text-xs font-bold text-slate-300">Pairing Status</h4>
                    <span className={`px-2 py-0.5 rounded text-[10px] font-semibold ${
                      telegramPaired ? 'bg-green-500/15 text-green-400' : 'bg-yellow-500/15 text-yellow-400'
                    }`}>
                      {telegramPaired ? '🟢 Paired' : '🟡 Unpaired'}
                    </span>
                  </div>

                  {!telegramPaired ? (
                    <div className="space-y-2 text-xs">
                      <p className="text-slate-400">To authorize your Telegram account, start a chat with your bot and send this pairing code:</p>
                      <div className="bg-slate-950 p-2.5 rounded-lg border border-slate-800 text-center font-mono text-lg tracking-wider text-cyan-400 font-bold select-all">
                        /pair {telegramPairingCode}
                      </div>
                    </div>
                  ) : (
                    <div className="space-y-2 text-xs flex items-center justify-between">
                      <p className="text-slate-400">Paired with Telegram Chat ID: <span className="font-mono text-slate-300">{telegramChatId}</span></p>
                      <button onClick={resetTelegramPairing} className="px-2.5 py-1 bg-red-500/10 border border-red-500/30 hover:bg-red-500/20 text-red-400 text-[10px] rounded-lg transition-colors">
                        Reset Pairing
                      </button>
                    </div>
                  )}
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

// ── Reusable UI Helpers ───────────────────────────────────────────────────────

function PermissionToggle({ label, desc, checked, onChange, danger = false }: {
  label: string; desc: string; checked: boolean; onChange: () => void; danger?: boolean;
}) {
  return (
    <div className="flex items-center justify-between p-3 bg-slate-800/50 rounded-xl border border-slate-700/50">
      <div className="flex-1 pr-4">
        <h4 className={`text-sm font-medium ${danger ? 'text-red-400' : 'text-slate-200'}`}>{label}</h4>
        <p className="text-[11px] text-slate-500 mt-0.5">{desc}</p>
      </div>
      <button 
        onClick={onChange}
        className={`w-10 h-5 rounded-full relative transition-colors ${checked ? (danger ? 'bg-red-500' : 'bg-cyan-500') : 'bg-slate-700'}`}
      >
        <div className={`absolute top-0.5 w-4 h-4 bg-white rounded-full transition-transform ${checked ? 'translate-x-5' : 'translate-x-1'}`} />
      </button>
    </div>
  );
}

function KeyInputField({ value, onChange, show, onToggleShow, placeholder, configured }: {
  value: string; onChange: (v: string) => void; show: boolean;
  onToggleShow: () => void; placeholder: string; configured: boolean;
}) {
  return (
    <div className="flex gap-2">
      <div className="relative flex-1">
        <Lock className="absolute left-3 top-2.5 text-slate-500" size={13} />
        <input type={show ? 'text' : 'password'} value={value}
          onChange={e => onChange(e.target.value)} placeholder={placeholder}
          onFocus={() => {
            if (configured && value.includes('•')) {
              onChange('');
            }
          }}
          className="w-full bg-slate-950 border border-slate-700 text-white text-sm rounded-lg pl-9 pr-4 py-2 focus:outline-none focus:ring-1 focus:ring-violet-500 placeholder:text-slate-600" />
        {configured && !value.includes('•') && <CheckCircle className="absolute right-3 top-2.5 text-green-400" size={13} />}
      </div>
      <button onClick={onToggleShow} className="px-3 bg-slate-800 hover:bg-slate-700 text-slate-400 rounded-lg transition-colors">
        {show ? <EyeOff size={13} /> : <Eye size={13} />}
      </button>
    </div>
  );
}

function ActionButton({ onClick, status, idleLabel, loadingLabel, color = 'cyan' }: {
  onClick: () => void; status: SaveStatus;
  idleLabel: string; loadingLabel: string; color?: 'cyan' | 'violet';
}) {
  const busy = status === 'testing' || status === 'saving';
  const cls = color === 'violet' ? 'bg-violet-600 hover:bg-violet-500' : 'bg-cyan-600 hover:bg-cyan-500';
  return (
    <button onClick={onClick} disabled={busy}
      className={`${cls} text-white px-5 py-1.5 rounded-lg text-sm font-medium transition-colors disabled:opacity-50 flex items-center gap-2`}>
      {busy && <Loader2 size={13} className="animate-spin" />}
      {busy ? loadingLabel : idleLabel}
    </button>
  );
}

function StatusText({ status, error }: { status: SaveStatus; error: string }) {
  if (status === 'success') return <span className="text-green-400 text-xs flex items-center gap-1"><CheckCircle size={13} /> Saved!</span>;
  if (status === 'error')   return <span className="text-red-400 text-xs flex items-center gap-1" title={error}><XCircle size={13} /> {error || 'Failed'}</span>;
  return null;
}
