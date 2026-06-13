import React, { useState, useEffect } from 'react';
import { Play, Sparkles, Film, Settings, AlertCircle, CheckCircle2, Download, RefreshCw, Loader, ExternalLink } from 'lucide-react';
import { JobStatus } from '../types';

export default function TextToVideoTab() {
  const [model, setModel] = useState<string>('3.1');
  const [aspectRatio, setAspectRatio] = useState<string>('VIDEO_ASPECT_RATIO_PORTRAIT');
  const [prompt, setPrompt] = useState<string>('');
  
  const [loading, setLoading] = useState<boolean>(false);
  const [currentJob, setCurrentJob] = useState<JobStatus | null>(null);
  const [enhancing, setEnhancing] = useState<boolean>(false);
  const [enhanceError, setEnhanceError] = useState<string | null>(null);

  const handleEnhancePrompt = async () => {
    if (!prompt.trim()) {
      setEnhanceError('Please enter some text in the prompt field first to optimize.');
      return;
    }
    setEnhancing(true);
    setEnhanceError(null);
    try {
      const res = await fetch('/api/generate-prompt', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ prompt }),
      });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.error || 'Failed to optimize prompt.');
      }
      setPrompt(data.enhancedPrompt);
    } catch (err: any) {
      console.error(err);
      setEnhanceError(err.message || 'Error occurred during prompt optimization.');
    } finally {
      setEnhancing(false);
    }
  };

  // Poll job status
  useEffect(() => {
    if (!currentJob || currentJob.status === 'completed' || currentJob.status === 'failed') {
      return;
    }

    const interval = setInterval(async () => {
      try {
        const res = await fetch(`/api/job-status/${currentJob.id}`);
        if (res.ok) {
          const data: JobStatus = await res.json();
          setCurrentJob(data);
          if (data.status === 'completed' || data.status === 'failed') {
            setLoading(false);
          }
        }
      } catch (err) {
        console.error('Error polling job status:', err);
      }
    }, 4000);

    return () => clearInterval(interval);
  }, [currentJob]);

  const handleGenerate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!prompt.trim()) return;

    setLoading(true);
    setCurrentJob(null);

    try {
      const res = await fetch('/api/generate-video', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          model,
          aspectRatio,
          prompt,
        }),
      });

      if (!res.ok) {
        throw new Error('Failed to start text-to-video generation job.');
      }

      const data = await res.json();
      setCurrentJob({
        id: data.jobId,
        type: 'text-to-video',
        status: 'queued',
        progress: 'Queuing job on server...',
        videoUrl: null,
        error: null,
        createdAt: Date.now(),
      });
    } catch (err: any) {
      alert(err.message || 'Error occurred starting video generation.');
      setLoading(false);
    }
  };

  const handleApplyPreset = (value: string) => {
    setPrompt(value);
  };

  const presets = [
    'A majestic cinematic shot of a golden retriever flying in space, background filled with nebula stars.',
    'Retro synthwave Cyberpunk futuristic neon city street, rainy night, high-definition reflections.',
    'A hyper-realistic close-up of a cup of coffee splashing, liquid floating in slow motion, sunny warm atmosphere.',
  ];

  return (
    <div className="space-y-6">
      <div className="bg-[#121214] rounded-2xl border border-zinc-800/80 p-6 shadow-xl shadow-black/20">
        <h2 className="text-lg font-semibold text-zinc-100 flex items-center gap-2 mb-4 font-display">
          <Sparkles className="w-5 h-5 text-violet-400" />
          Text to Video Specifications
        </h2>
 
        <form onSubmit={handleGenerate} className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {/* Model Selector */}
            <div className="space-y-1">
              <label htmlFor="modal" className="block text-xs font-semibold text-zinc-400 uppercase tracking-wider font-mono">
                Select Model
              </label>
              <div className="relative">
                <select
                  id="modal"
                  name="modal"
                  value={model}
                  onChange={(e) => setModel(e.target.value)}
                  className="w-full h-11 px-3 bg-[#18181b] border border-zinc-800 text-zinc-200 text-sm focus:outline-none focus:ring-1 focus:ring-violet-500 focus:border-violet-500 rounded-xl transition-all appearance-none cursor-pointer font-medium"
                >
                  <option value="3.1">Grok 4 (Premium Model 3.1)</option>
                  <option value="2.0">Grok 4.5 (Legacy Model 2.0)</option>
                </select>
                <div className="absolute right-3.5 top-1/2 -translate-y-1/2 pointer-events-none text-zinc-500">
                  <Settings className="w-4 h-4" />
                </div>
              </div>
            </div>
 
            {/* Aspect Ratio Selector */}
            <div className="space-y-1">
              <label htmlFor="aspect-ration" className="block text-xs font-semibold text-zinc-400 uppercase tracking-wider font-mono">
                Aspect Ratio
              </label>
              <div className="relative">
                <select
                  id="aspect-ration"
                  name="aspect-ration"
                  value={aspectRatio}
                  onChange={(e) => setAspectRatio(e.target.value)}
                  className="w-full h-11 px-3 bg-[#18181b] border border-zinc-800 text-zinc-200 text-sm focus:outline-none focus:ring-1 focus:ring-violet-500 focus:border-violet-500 rounded-xl transition-all appearance-none cursor-pointer font-medium"
                >
                  <option value="VIDEO_ASPECT_RATIO_PORTRAIT">Portrait (9:16)</option>
                  <option value="VIDEO_ASPECT_RATIO_LANDSCAPE">Landscape (16:9)</option>
                </select>
                <div className="absolute right-3.5 top-1/2 -translate-y-1/2 pointer-events-none text-zinc-500">
                  <Film className="w-4 h-4" />
                </div>
              </div>
            </div>
          </div>
 
          {/* Prompt Area */}
          <div className="space-y-1.5 division-y border-t border-transparent">
            <div className="flex justify-between items-center py-1">
              <label htmlFor="fn__include_textarea" className="block text-xs font-semibold text-zinc-400 uppercase tracking-wider font-mono">
                Video Prompt
              </label>
              <div className="flex gap-3 items-center">
                {enhancing ? (
                  <span className="text-xs text-violet-400 animate-pulse font-mono flex items-center gap-1">
                    <RefreshCw className="w-3 h-3 animate-spin" /> Optimizing with Llama...
                  </span>
                ) : (
                  <button
                    type="button"
                    onClick={handleEnhancePrompt}
                    className="text-xs text-violet-400 hover:text-violet-300 font-bold font-mono transition-colors flex items-center gap-1 px-2.5 py-1 bg-violet-950/40 hover:bg-violet-950/75 border border-violet-500/20 rounded-lg shadow-sm cursor-pointer"
                  >
                    <Sparkles className="w-3 h-3 text-violet-400" /> Enhance with Llama-4
                  </button>
                )}
                <span className="text-xs text-zinc-500 font-mono">{prompt.length} / 800 chars</span>
              </div>
            </div>
            <textarea
              id="fn__include_textarea"
              name="fn__include_textarea"
              rows={4}
              maxLength={800}
              placeholder="Describe the scenes, camera angles, lighting, and action sequence in detail..."
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              className="w-full p-4 bg-[#18181b] border border-zinc-800 rounded-xl text-zinc-100 text-sm focus:outline-none focus:ring-1 focus:ring-violet-500 focus:border-violet-500 transition-all resize-none placeholder-zinc-600 leading-relaxed shadow-inner"
            />
            {enhanceError && (
              <p className="text-[11px] text-rose-400 mt-1 font-mono flex items-center gap-1.5 bg-rose-950/10 border border-rose-900/25 px-2.5 py-1.5 rounded-lg animate-fade-in">
                <AlertCircle className="w-3.5 h-3.5" />
                {enhanceError}
              </p>
            )}
          </div>
 
          {/* Presets */}
          <div className="space-y-2">
            <span className="text-xs font-semibold text-zinc-500 uppercase tracking-wider block font-mono">Quick Presets</span>
            <div className="flex flex-col gap-2 matches-scroll flex-wrap max-h-48 overflow-y-auto pr-1">
              {presets.map((p, idx) => (
                <button
                  key={idx}
                  type="button"
                  onClick={() => handleApplyPreset(p)}
                  className="text-left py-2 px-3 text-xs text-zinc-400 bg-zinc-900 hover:bg-[#1f1f23] hover:text-zinc-100 border border-zinc-800/60 rounded-xl transition-all truncate hover:translate-x-0.5 duration-150 shadow-sm"
                  title={p}
                >
                  {p}
                </button>
              ))}
            </div>
          </div>
 
          {/* Action Trigger */}
          <button
            type="submit"
            disabled={loading || !prompt.trim()}
            className={`w-full h-12 flex items-center justify-center gap-2 rounded-xl text-white font-semibold shadow-lg transition-all ${
              loading || !prompt.trim()
                ? 'bg-zinc-800 text-zinc-500 cursor-not-allowed shadow-none border border-zinc-800'
                : 'bg-gradient-to-r from-violet-600 to-indigo-600 hover:from-violet-500 hover:to-indigo-500 active:scale-[0.99] hover:shadow-violet-600/10 border border-violet-500/20'
            }`}
          >
            {loading ? (
              <>
                <Loader className="w-5 h-5 animate-spin" />
                Generating Video...
              </>
            ) : (
              <>
                <Play className="w-5 h-5 pointer-events-none" />
                Generate Instant Video
              </>
            )}
          </button>
        </form>
      </div>
 
      {/* Progress & Output State Panel */}
      {currentJob && (
        <div className="bg-[#121214] rounded-2xl border border-zinc-800 p-6 shadow-xl space-y-4">
          <div className="flex items-center justify-between border-b border-zinc-800/60 pb-3">
            <h3 className="font-semibold text-zinc-100 flex items-center gap-2 font-display text-sm">
              <Film className="w-4 h-4 text-violet-400" />
              Generator Workspace Tracker
            </h3>
            <div className="flex items-center gap-2 text-xs font-mono text-zinc-500 bg-zinc-900 border border-zinc-800 px-2.5 py-0.5 rounded-full select-all">
              ID: {currentJob.id}
            </div>
          </div>
 
          {/* Processing Status Ticker */}
          {(currentJob.status === 'queued' || currentJob.status === 'processing') && (
            <div className="p-4 bg-zinc-900/50 border border-zinc-800/80 rounded-xl space-y-3">
              <div className="flex items-center justify-between">
                <span className="text-sm font-semibold text-violet-400 flex items-center gap-2">
                  <RefreshCw className="w-4 h-4 animate-spin text-violet-400" />
                  {currentJob.status === 'queued' ? 'Queued' : 'Executing Automation'}
                </span>
                <span className="text-xs bg-zinc-800 text-zinc-400 border border-zinc-700/60 px-2.5 py-0.5 rounded-full font-semibold font-mono">
                  Browser Node Mode
                </span>
              </div>
              <p className="text-xs text-zinc-300 leading-normal font-mono bg-[#0c0c0e] py-2 px-3 border border-zinc-800 rounded-lg">
                <span className="text-zinc-500 mr-1.5">&gt;</span>{currentJob.progress}
              </p>
              <div className="w-full bg-zinc-800 h-2 rounded-full overflow-hidden">
                <div 
                  className="bg-gradient-to-r from-violet-500 to-indigo-500 h-full rounded-full transition-all duration-500 animate-pulse"
                  style={{ width: currentJob.status === 'queued' ? '15%' : '65%' }}
                />
              </div>
              <p className="text-[11px] text-zinc-500 leading-relaxed font-mono">
                VeoAIFree is processing the frame renders. Playwright is reading live DOM output variables and is waiting for video completion. This normally takes about 90 to 120 seconds.
              </p>

              {/* Live Generator Browser Preview */}
              {currentJob.screenshots && currentJob.screenshots.length > 0 && (
                <div className="mt-4 space-y-3.5 border-t border-zinc-805/45 pt-4">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-semibold text-zinc-400 flex items-center gap-2 font-mono">
                      <span className="relative flex h-2.5 w-2.5 shrink-0">
                        <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-rose-400 opacity-75"></span>
                        <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-rose-500"></span>
                      </span>
                      Live Playwright Node View
                    </span>
                    <span className="text-[10px] text-zinc-500 font-mono tracking-wider">
                      Updating Live (5s)
                    </span>
                  </div>
                  
                  {/* Active main screenshot */}
                  {(() => {
                    const latest = currentJob.screenshots[currentJob.screenshots.length - 1];
                    return (
                      <div className="relative group rounded-xl overflow-hidden border border-zinc-800 shadow-2xl bg-zinc-950 max-w-full">
                        <img 
                          src={latest} 
                          alt="Live generator screenshot" 
                          referrerPolicy="no-referrer"
                          className="w-full object-contain max-h-[350px] mx-auto bg-zinc-950 transition-opacity duration-300"
                        />
                        <div className="absolute top-3 left-3 bg-black/80 backdrop-blur-md px-2.5 py-1 rounded-lg border border-zinc-800 text-[10px] font-mono text-zinc-300 pointer-events-none flex items-center gap-1.5 shadow-md">
                          <span className="w-1.5 h-1.5 bg-rose-500 rounded-full animate-pulse" />
                          Live Frame {currentJob.screenshots.length}
                        </div>
                      </div>
                    );
                  })()}

                  {/* Thumbnail row if more than 1 screenshot */}
                  {currentJob.screenshots.length > 1 && (
                    <div className="space-y-2">
                      <span className="text-[10px] font-semibold text-zinc-500 uppercase tracking-wider block font-mono">Frame Lifecycle Progress</span>
                      <div className="flex gap-2.5 pb-2 overflow-x-auto select-none scrollbar-thin scrollbar-thumb-zinc-800 scrollbar-track-transparent">
                        {currentJob.screenshots.map((shot, sIdx) => {
                          const isActive = sIdx === currentJob.screenshots!.length - 1;
                          return (
                            <div 
                              key={sIdx} 
                              className={`relative min-w-[80px] aspect-[16/10] h-12 rounded-lg border overflow-hidden shrink-0 cursor-zoom-in transition-all ${
                                isActive 
                                  ? 'border-violet-500 ring-2 ring-violet-500/20 z-10 scale-[1.03]' 
                                  : 'border-zinc-800 opacity-60 hover:opacity-100 hover:border-zinc-700'
                              }`}
                              onClick={() => window.open(shot, '_blank')}
                            >
                              <img 
                                src={shot} 
                                alt={`Frame step ${sIdx + 1}`} 
                                referrerPolicy="no-referrer"
                                className="w-full h-full object-cover"
                              />
                              <div className="absolute inset-0 bg-gradient-to-t from-black/60 to-transparent flex items-end justify-start p-1">
                                <span className="text-[8px] font-mono text-zinc-300 font-bold bg-zinc-950/80 px-1 rounded-sm border border-zinc-900">
                                  #{sIdx + 1}
                                </span>
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>
          )}
 
          {/* Complete Status Video Player */}
          {currentJob.status === 'completed' && currentJob.videoUrl && (
            <div className="space-y-4">
              <div className="p-4 bg-emerald-950/10 border border-emerald-500/20 text-emerald-400 rounded-xl flex gap-3">
                <CheckCircle2 className="w-5 h-5 text-emerald-500 shrink-0 mt-0.5" />
                <div className="text-xs leading-normal">
                  <span className="font-bold text-emerald-300 block text-sm">Render Finished Successfully!</span>
                  <p className="text-emerald-400/80 mt-0.5">The video pipeline has successfully tracked the direct render output link from VeoAIFree. Dynamic stream is playing from origin CDN.</p>
                </div>
              </div>
 
              <div className="border border-zinc-800/80 rounded-2xl overflow-hidden shadow-2xl bg-black aspect-[16/9] w-full min-h-[350px] md:min-h-[460px] flex items-center justify-center relative">
                <video
                  src={currentJob.videoUrl}
                  controls
                  className="w-full h-full object-contain rounded-xl"
                  autoPlay
                  loop
                  playsInline
                  preload="auto"
                />
              </div>
 
              {/* Action Downloads */}
              <div className="flex flex-wrap gap-2.5 justify-end">
                <a
                  href={currentJob.videoUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="h-11 px-5 bg-zinc-800 hover:bg-zinc-700 text-zinc-100 border border-zinc-700/50 rounded-xl text-sm font-semibold flex items-center gap-2 tracking-wide transition-all"
                >
                  <ExternalLink className="w-4 h-4" />
                  Open Direct Link
                </a>
                <a
                  href={currentJob.videoUrl}
                  download={`generation-${currentJob.id}.mp4`}
                  className="h-11 px-5 bg-[#7c3aed] hover:bg-[#6d28d9] text-white rounded-xl text-sm font-semibold flex items-center gap-2 tracking-wide transition-colors shadow-lg shadow-violet-900/10"
                >
                  <Download className="w-4 h-4" />
                  Save / Download Video
                </a>
              </div>
            </div>
          )}
 
          {/* Failed Status Box */}
          {currentJob.status === 'failed' && (
            <div className="p-5 bg-rose-950/15 border border-rose-900/30 rounded-xl space-y-3">
              <div className="flex items-center gap-2 text-rose-400 font-bold text-sm">
                <AlertCircle className="w-5 h-5 text-rose-500 shrink-0" />
                Generation Automation Interrupted
              </div>
              <p className="text-xs text-rose-300 leading-relaxed font-mono bg-zinc-950/80 p-3.5 rounded-lg border border-rose-900/30">
                {currentJob.error || 'The browser node failed to respond within the timing requirements.'}
              </p>
              <p className="text-[11px] text-zinc-500 leading-relaxed font-sans">
                Please double check your configuration details & prompt specs. You can retry anytime.
              </p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
