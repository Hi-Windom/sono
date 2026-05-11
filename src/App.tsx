import { BrowserRouter as Router, Routes, Route } from "react-router-dom";
import LandingPage from "@/pages/LandingPage";
import RepairPage from "@/pages/RepairPage";
import TrainingUploadPage from "@/pages/TrainingUploadPage";
import QualityTestPage from "@/pages/QualityTestPage";
import ProfileManagerPage from "@/pages/ProfileManagerPage";
import CacheManagerPage from "@/pages/CacheManagerPage";
import ComparePage from "@/pages/ComparePage";
import { BuildInfo } from "@/components/BuildInfo";
import { useEffect } from "react";

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

export default function App() {
  return (
    <Router>
      <VConsoleInit />
      <Routes>
        <Route path="/" element={<LandingPage />} />
        <Route path="/repair" element={<RepairPage />} />
        <Route path="/training-upload" element={<TrainingUploadPage />} />
        <Route path="/quality-tests" element={<QualityTestPage />} />
        <Route path="/profile-manager" element={<ProfileManagerPage />} />
        <Route path="/cache-manager" element={<CacheManagerPage />} />
        <Route path="/compare" element={<ComparePage />} />
      </Routes>
      <BuildInfo />
    </Router>
  );
}
