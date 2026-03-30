import { lazy, Suspense } from "react";
import { Routes, Route } from "react-router-dom";
import Layout from "./components/Layout";
import ErrorBoundary from "./components/ErrorBoundary";
import LoadingSpinner from "./components/LoadingSpinner";
import "./App.css";

// -- Auth pages ---------------------------------------------------------------
const Login = lazy(() => import("./pages/Login"));

// -- Core pages (dashboard, campaigns) ----------------------------------------
const Dashboard = lazy(() => import("./pages/Dashboard"));
const CampaignList = lazy(() => import("./pages/Campaigns"));
const CampaignCreate = lazy(() => import("./pages/CampaignCreate"));
const CampaignDetail = lazy(() => import("./pages/CampaignDetail"));

// -- Asset management (addressbooks, templates, landing pages) ----------------
const AddressBookList = lazy(() => import("./pages/AddressBooks"));
const TemplateList = lazy(() => import("./pages/Templates"));
const LandingPageList = lazy(() => import("./pages/LandingPages"));

// -- Reporting & admin --------------------------------------------------------
const ReportList = lazy(() => import("./pages/Reports"));
const Settings = lazy(() => import("./pages/Settings"));
const AuditLog = lazy(() => import("./pages/AuditLog"));

export default function App() {
  return (
    <ErrorBoundary>
      <Suspense fallback={<LoadingSpinner fullScreen message="Loading..." />}>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route element={<Layout />}>
            <Route path="/" element={<Dashboard />} />
            <Route path="/campaigns" element={<CampaignList />} />
            <Route path="/campaigns/new" element={<CampaignCreate />} />
            <Route path="/campaigns/:id" element={<CampaignDetail />} />
            <Route path="/addressbooks" element={<AddressBookList />} />
            <Route path="/templates" element={<TemplateList />} />
            <Route path="/landing-pages" element={<LandingPageList />} />
            <Route path="/reports" element={<ReportList />} />
            <Route path="/settings" element={<Settings />} />
            <Route path="/audit" element={<AuditLog />} />
          </Route>
        </Routes>
      </Suspense>
    </ErrorBoundary>
  );
}
