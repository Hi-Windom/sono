import { BrowserRouter as Router, Routes, Route } from "react-router-dom";
import LandingPage from "@/pages/LandingPage";
import RepairPage from "@/pages/RepairPage";
import TrainingUploadPage from "@/pages/TrainingUploadPage";
import QualityTestPage from "@/pages/QualityTestPage";
import ProfileManagerPage from "@/pages/ProfileManagerPage";
import CacheManagerPage from "@/pages/CacheManagerPage";
import ComparePage from "@/pages/ComparePage";
import DetectPage from "@/pages/DetectPage";
import FlowVisualizationPage from "@/pages/FlowVisualizationPage";
import { BuildInfo } from "@/components/BuildInfo";
import { useEffect, useState } from "react";
import { BackendProvider } from "@/contexts/BackendContext";

function VConsoleInit() {
  useEffect(() => {
    let vc: any;
    import('vconsole').then((VConsole) => {
      vc = new VConsole.default({
        theme: 'dark',
        onReady: function() {
          const vcSwitch = document.querySelector('.vc-switch');
          if (vcSwitch) {
            (vcSwitch as HTMLElement).style.display = 'none';
          }
        },
      });
      (window as any).__vconsole__ = vc;
    });
    return () => {
      if (vc) vc.destroy();
    };
  }, []);
  return null;
}

function GlobalErrorHandler() {
  const [fatalError, setFatalError] = useState<string | null>(null);

  useEffect(() => {
    const handleUnhandledRejection = (event: PromiseRejectionEvent) => {
      console.error('[GlobalErrorHandler] 未处理的 Promise 拒绝:', event.reason);
      const msg = event.reason?.message || String(event.reason);
      if (msg.includes('chunk') || msg.includes('Loading') || msg.includes('import')) {
        window.location.reload();
        return;
      }
    };

    const handleError = (event: ErrorEvent) => {
      console.error('[GlobalErrorHandler] 未捕获的错误:', event.error);
    };

    window.addEventListener('unhandledrejection', handleUnhandledRejection);
    window.addEventListener('error', handleError);

    return () => {
      window.removeEventListener('unhandledrejection', handleUnhandledRejection);
      window.removeEventListener('error', handleError);
    };
  }, []);

  if (fatalError) {
    return (
      <div className="min-h-screen bg-gray-950 flex items-center justify-center p-6">
        <div className="max-w-md w-full bg-gray-900 border border-red-500/30 rounded-2xl p-6 text-center">
          <div className="text-4xl mb-3">💥</div>
          <h2 className="text-white text-lg font-bold mb-2">致命错误</h2>
          <p className="text-gray-400 text-sm mb-4 break-all">{fatalError}</p>
          <div className="flex flex-col gap-2">
            <button
              onClick={() => window.location.reload()}
              className="px-4 py-2 bg-cyan-500/20 hover:bg-cyan-500/30 text-cyan-400 rounded-lg text-sm transition"
            >
              刷新页面
            </button>
            <button
              onClick={() => {
                try { localStorage.removeItem('repair-session'); } catch {}
                try { localStorage.removeItem('app-settings'); } catch {}
                window.location.reload();
              }}
              className="px-4 py-2 bg-red-500/20 hover:bg-red-500/30 text-red-400 rounded-lg text-sm transition"
            >
              清除状态并刷新
            </button>
          </div>
        </div>
      </div>
    );
  }

  return null;
}

function AppRoutes() {
  return (
    <>
      <VConsoleInit />
      <GlobalErrorHandler />
      <Routes>
        <Route path="/" element={<LandingPage />} />
        <Route path="/repair" element={<RepairPage />} />
        <Route path="/training-upload" element={<TrainingUploadPage />} />
        <Route path="/quality-tests" element={<QualityTestPage />} />
        <Route path="/profile-manager" element={<ProfileManagerPage />} />
        <Route path="/cache-manager" element={<CacheManagerPage />} />
        <Route path="/compare" element={<ComparePage />} />
        <Route path="/detect" element={<DetectPage />} />
        <Route path="/flow" element={<FlowVisualizationPage />} />
      </Routes>
      <BuildInfo />
    </>
  );
}

export default function App() {
  return (
    <BackendProvider>
      <Router>
        <AppRoutes />
      </Router>
    </BackendProvider>
  );
}
