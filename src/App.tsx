import { useState, useEffect } from 'react';
import { Film, Terminal, ChevronRight, CheckCircle2, AlertTriangle, Link, Info, RefreshCw } from 'lucide-react';
import TextToVideoTab from './components/TextToVideoTab';
import ImageToVideoTab from './components/ImageToVideoTab';
import { ActiveTab, ServiceStatus } from './types';

export default function App() {
  const [activeTab, setActiveTab] = useState<ActiveTab>('text-to-video');
  const [serviceStatus, setServiceStatus] = useState<ServiceStatus>({
    status: 'connecting',
    ngrokUrl: '',
    ngrokEnabled: false,
  });

  // Pull Ngrok endpoint status from server
  useEffect(() => {
    const fetchStatus = async () => {
      try {
        const res = await fetch('/api/status');
        if (res.ok) {
          const data: ServiceStatus = await res.json();
          setServiceStatus(data);
        }
      } catch (err) {
        console.error('Failed to contact server status API:', err);
      }
    };

    fetchStatus();
    const interval = setInterval(fetchStatus, 8000);
    return () => clearInterval(interval);
  }, []);

  return (
    <div className="min-h-screen bg-gradient-to-b from-[#121214] to-[#08080a] font-sans text-zinc-100 flex flex-col">
      {/* Top Banner (Service & Ngrok Details) */}
      <div className="bg-[#0c0c0e]/95 backdrop-blur-md py-3 px-4 sm:px-6 flex flex-col sm:flex-row items-center justify-between gap-3 border-b border-zinc-800/50">
        <div className="flex items-center gap-2.5">
          <div className="bg-zinc-900 p-1.5 rounded-lg border border-zinc-800">
            <Terminal className="w-4 h-4 text-violet-400 shrink-0 animate-pulse" />
          </div>
          <div className="text-xs">
            <span className="font-semibold text-zinc-300">System Integration Status:</span>
            <span className="text-zinc-500 ml-1.5 font-mono">
              Port 3000 • Node Express • Headless Engine
            </span>
          </div>
        </div>

        {/* Ngrok status tracker */}
        <div className="flex items-center gap-3">
          {serviceStatus.ngrokEnabled && serviceStatus.ngrokUrl ? (
            <div className="flex items-center gap-2 bg-zinc-900 border border-violet-500/20 px-3 py-1 rounded-full text-xs">
              <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
              <span className="font-medium text-violet-300">Tunnel Live:</span>
              <a
                href={serviceStatus.ngrokUrl}
                target="_blank"
                rel="noreferrer"
                className="text-zinc-200 hover:text-white underline hover:underline flex items-center gap-1 font-mono text-[11px]"
              >
                {serviceStatus.ngrokUrl.replace('https://', '')}
                <Link className="w-3 h-3 hover:scale-110 transition-transform" />
              </a>
            </div>
          ) : (
            <div className="flex items-center gap-2 bg-zinc-900/80 border border-amber-500/10 px-3 py-1 rounded-full text-xs text-amber-400 font-medium">
              <RefreshCw className="w-3 h-3 animate-spin text-amber-500" />
              <span>Initializing Ngrok Tunnel...</span>
            </div>
          )}
        </div>
      </div>

      <header className="border-b border-zinc-900 py-6 bg-gradient-to-b from-[#0e0e11] to-[#0c0c0e]/20">
        <div className="max-w-4xl mx-auto px-4 sm:px-6 flex flex-col md:flex-row items-center justify-between gap-6">
          <div className="flex items-center gap-4">
            <div className="bg-gradient-to-br from-violet-600 via-indigo-600 to-indigo-700 text-white p-3.5 rounded-2xl shadow-lg shadow-indigo-900/30 border border-indigo-500/20 flex items-center justify-center">
              <Film className="w-7 h-7" />
            </div>
            <div>
              <h1 className="text-2xl font-extrabold text-transparent bg-clip-text bg-gradient-to-r from-zinc-50 via-zinc-100 to-zinc-400 tracking-tight font-display">
                BautiAI
              </h1>
              <p className="text-xs text-zinc-400 mt-1 font-medium leading-relaxed">
                Automated High-Fidelity Rendering via Grok & Google VEO Engines
              </p>
            </div>
          </div>

          {/* Navigation Controls */}
          <div className="flex bg-zinc-950 p-1.5 rounded-2xl w-full md:w-auto border border-zinc-800/80">
            <button
              onClick={() => setActiveTab('text-to-video')}
              className={`flex-1 md:flex-none px-6 py-2.5 rounded-xl text-sm font-semibold tracking-wide transition-all ${
                activeTab === 'text-to-video'
                  ? 'bg-gradient-to-r from-violet-600 to-indigo-600 text-white shadow-md shadow-indigo-600/20'
                  : 'text-zinc-400 hover:text-zinc-200 hover:bg-zinc-900/50'
              }`}
            >
              Text to Video
            </button>
            <button
              onClick={() => setActiveTab('image-to-video')}
              className={`flex-1 md:flex-none px-6 py-2.5 rounded-xl text-sm font-semibold tracking-wide transition-all ${
                activeTab === 'image-to-video'
                  ? 'bg-gradient-to-r from-violet-600 to-indigo-600 text-white shadow-md shadow-indigo-600/20'
                  : 'text-zinc-400 hover:text-zinc-200 hover:bg-zinc-900/50'
              }`}
            >
              Image to Video
            </button>
          </div>
        </div>
      </header>

      {/* Main Panel container */}
      <main className="max-w-4xl mx-auto px-4 sm:px-6 py-8 flex-grow w-full">
        <div className="grid grid-cols-1 gap-6">
          {/* Operational guidelines and hints */}
          <div className="p-5 bg-gradient-to-r from-zinc-900 to-[#18181b]/50 rounded-2xl border border-zinc-800/70 flex gap-4 shadow-lg shadow-black/20">
            <div className="bg-indigo-500/10 p-2.5 rounded-xl border border-indigo-500/20 flex items-center justify-center self-start">
              <Info className="w-5 h-5 text-indigo-400 shrink-0" />
            </div>
            <div className="text-zinc-300 leading-relaxed">
              <span className="font-bold text-zinc-100 block text-sm mb-1 font-display">
                Automated Browser Pipelines
              </span>
              <p className="text-xs text-zinc-400 leading-relaxed">
                This environment executes automated headless Playwright sessions to render files. 
                Renders and queues are managed asynchronously server-side. For optimal viewing or sharing, access the public tunnel from a separate tab.
              </p>
            </div>
          </div>

          {/* Current Tab mount */}
          <div className="transition-all duration-300">
            {activeTab === 'text-to-video' ? <TextToVideoTab /> : <ImageToVideoTab />}
          </div>
        </div>
      </main>

      <footer className="w-full max-w-4xl mx-auto px-4 sm:px-6 py-8 text-center text-xs text-zinc-500 border-t border-zinc-900 mt-12 font-mono">
        <p>© 2026 BautiAI. Powered by Playwright headless engines and ngrok technology.</p>
      </footer>
    </div>
  );
}
