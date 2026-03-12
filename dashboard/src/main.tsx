import ReactDOM from "react-dom/client";
import "./index.css";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import { Layout } from "./components/Layout";
import { FleetPage } from "./pages/FleetPage";
import { MissionsPage } from "./pages/MissionsPage";
import { OTAPage } from "./pages/OTAPage";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <BrowserRouter>
    <Routes>
      <Route path="/" element={<Layout />}>
        <Route index element={<FleetPage />} />
        <Route path="missions" element={<MissionsPage />} />
        <Route path="ota" element={<OTAPage />} />
      </Route>
    </Routes>
  </BrowserRouter>,
);
