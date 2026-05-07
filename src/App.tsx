import { BrowserRouter as Router, Routes, Route } from "react-router-dom";
import LandingPage from "@/pages/LandingPage";
import RepairPage from "@/pages/RepairPage";
import TrainingUploadPage from "@/pages/TrainingUploadPage";
import { BuildInfo } from "@/components/BuildInfo";

export default function App() {
  return (
    <Router>
      <Routes>
        <Route path="/" element={<LandingPage />} />
        <Route path="/repair" element={<RepairPage />} />
        <Route path="/training-upload" element={<TrainingUploadPage />} />
      </Routes>
      <BuildInfo />
    </Router>
  );
}
