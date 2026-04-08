import { useState, useEffect, useRef, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { datasetApi, analysisApi, sessionsApi, type DatasetResult } from "../api/client";
import DatasetCard from "../components/DatasetCard";
import SessionHistory from "../components/SessionHistory";
import UploadModal from "../components/UploadModal";
import { useAuth } from "../hooks/useAuth";

const SEARCH_STEPS = [
  "Searching data.gov...",
  "Searching World Bank...",
  "Searching Kaggle...",
  "Searching HuggingFace...",
  "Searching SDOH Place...",
  "Searching CMS Medicare/Medicaid...",
  "Searching Harvard Dataverse...",
  "Searching HUD Open Data...",
  "Searching BLS...",
  "Searching FRED...",
  "Searching CMAP Data Hub...",
  "Searching Census.gov...",
  "Searching Chicago Health Atlas...",
  "Searching Our World in Data...",
  "Searching OECD...",
  "Searching V-Dem...",
  "Searching EIA...",
  "Searching CDC PLACES...",
  "Ranking results by relevance...",
];

const SOURCES = [
  {
    name: "data.gov",
    key: "data.gov",
    color: "#0071bc",
    description: "The US government's open data portal with over 300,000 datasets spanning federal, state, and local government agencies. Covers topics like climate, education, finance, health, and public safety.",
    url: "https://data.gov",
  },
  {
    name: "World Bank",
    key: "worldbank",
    color: "#009fda",
    description: "Global development data from the World Bank covering 200+ countries. Includes economic indicators, poverty metrics, health statistics, education data, and environmental indicators.",
    url: "https://data.worldbank.org",
  },
  {
    name: "Kaggle",
    key: "kaggle",
    color: "#20beff",
    description: "Community-driven data science platform with thousands of public datasets. Covers machine learning, social science, business analytics, and more. Datasets are uploaded by users and organizations.",
    url: "https://www.kaggle.com/datasets",
  },
  {
    name: "HuggingFace",
    key: "huggingface",
    color: "#ff9d00",
    description: "AI/ML community hub hosting 100,000+ datasets for natural language processing, computer vision, audio, and tabular data. Popular for research and model training datasets.",
    url: "https://huggingface.co/datasets",
  },
  {
    name: "SDOH Place",
    key: "sdohplace",
    color: "#4caf50",
    description: "Social Determinants of Health data platform providing place-based data on factors affecting health outcomes — housing, food access, transportation, education, and economic stability at the community level.",
    url: "https://sdohplace.org",
  },
  {
    name: "CMS",
    key: "cms",
    color: "#d63384",
    description: "Centers for Medicare & Medicaid Services open data. Includes Medicare claims, provider utilization, hospital quality measures, prescription drug costs, and Medicaid enrollment data.",
    url: "https://data.cms.gov",
  },
  {
    name: "Harvard Dataverse",
    key: "harvard_dataverse",
    color: "#a51c30",
    description: "Open-access research data repository hosted by Harvard University. Contains datasets from academic research across all disciplines — social sciences, natural sciences, medicine, and humanities.",
    url: "https://dataverse.harvard.edu",
  },
  {
    name: "HUD",
    key: "hud",
    color: "#008542",
    description: "US Department of Housing and Urban Development open data. Includes Fair Market Rents, housing affordability, homelessness statistics, public housing data, and community development grants.",
    url: "https://www.huduser.gov/portal/datasets",
  },
  {
    name: "BLS",
    key: "bls",
    color: "#003366",
    description: "Bureau of Labor Statistics data on employment, unemployment, wages, inflation (CPI), productivity, workplace injuries, and consumer spending for the United States.",
    url: "https://www.bls.gov/data/",
  },
  {
    name: "FRED",
    key: "fred",
    color: "#1a5276",
    description: "Federal Reserve Economic Data — 800,000+ time series from the St. Louis Fed. Covers interest rates, GDP, employment, exchange rates, monetary aggregates, and other macroeconomic indicators.",
    url: "https://fred.stlouisfed.org",
  },
  {
    name: "CMAP",
    key: "cmap",
    color: "#6c3483",
    description: "Chicago Metropolitan Agency for Planning data hub. Regional data for the Chicago metro area covering transportation, land use, demographics, economic development, and environmental planning.",
    url: "https://datahub.cmap.illinois.gov",
  },
  {
    name: "Census",
    key: "census",
    color: "#b7410e",
    description: "US Census Bureau data including the American Community Survey, decennial census, population estimates, economic census, and demographic surveys covering the entire United States.",
    url: "https://data.census.gov",
  },
  {
    name: "Chicago Health Atlas",
    key: "chicago_health_atlas",
    color: "#1b9e77",
    description: "Chicago Department of Public Health data covering 450+ health indicators for Chicago community areas, ZIP codes, and census tracts. Includes data on chronic disease, mortality, social determinants, and healthcare access.",
    url: "https://chicagohealthatlas.org",
  },
  {
    name: "Our World in Data",
    key: "owid",
    color: "#286BBB",
    description: "Research and data on global challenges — poverty, disease, hunger, climate change, war, inequality, and more. Curated datasets with clear visualizations covering 200+ countries and topics from health to energy to education.",
    url: "https://ourworldindata.org",
  },
  {
    name: "OECD",
    key: "oecd",
    color: "#0E47CB",
    description: "Organisation for Economic Co-operation and Development data covering 38 member countries. Includes economic outlooks, trade statistics, education metrics, health spending, labor markets, productivity, and governance indicators.",
    url: "https://data-explorer.oecd.org",
  },
  {
    name: "V-Dem",
    key: "vdem",
    color: "#8B1A1A",
    description: "Varieties of Democracy (V-Dem) v15 dataset with 500+ democracy indicators for 202 countries from 1789 to 2024. Covers electoral, liberal, participatory, deliberative, and egalitarian democracy, plus corruption, civil liberties, media freedom, and gender equality. CC-BY-SA licensed.",
    url: "https://v-dem.net",
  },
  {
    name: "EIA",
    key: "eia",
    color: "#00843d",
    description: "U.S. Energy Information Administration — comprehensive energy data including electricity generation, petroleum prices, natural gas, coal, nuclear, and renewables. Covers production, consumption, prices, imports/exports, and state-level data.",
    url: "https://www.eia.gov/opendata/",
  },
  {
    name: "USASpending",
    key: "usaspending",
    color: "#1B2B65",
    description: "Federal government spending data — contracts, grants, loans, and other financial awards. Track billions in federal spending by agency, recipient, location, and program across all government departments.",
    url: "https://www.usaspending.gov",
  },
  {
    name: "CDC PLACES",
    key: "cdc_places",
    color: "#0D5C63",
    description: "CDC Population Level Analysis and Community Estimates — local health data for the entire US. County, city, census tract, and ZIP code level estimates for 39 health measures including chronic disease prevalence, prevention, risk behaviors, disability, and social needs.",
    url: "https://www.cdc.gov/places",
  },
  {
    name: "ClinicalTrials",
    key: "clinicaltrials",
    color: "#2E8B57",
    description: "ClinicalTrials.gov database of clinical studies conducted around the world. Search trials by condition, intervention, sponsor, phase, and status. Covers drug trials, device studies, and behavioral interventions.",
    url: "https://clinicaltrials.gov",
  },
  {
    name: "OpenFDA",
    key: "openfda",
    color: "#0058A4",
    description: "FDA open data on drug adverse events, recalls, medical device reports, and food safety enforcement actions. Explore medication side effects, manufacturer recalls, and consumer safety reports.",
    url: "https://open.fda.gov",
  },
  {
    name: "CFPB",
    key: "cfpb",
    color: "#20aa3f",
    description: "Consumer Financial Protection Bureau complaint database. Hundreds of thousands of consumer complaints against banks, lenders, and financial companies — searchable by product, company, issue, and outcome.",
    url: "https://www.consumerfinance.gov/data-research/consumer-complaints/",
  },
  {
    name: "SEC EDGAR",
    key: "sec_edgar",
    color: "#002B5C",
    description: "Securities and Exchange Commission EDGAR database. Search company filings including 10-K annual reports, 10-Q quarterly reports, 8-K current reports, and other regulatory disclosures for public companies.",
    url: "https://www.sec.gov/edgar",
  },
  {
    name: "Federal Register",
    key: "federal_register",
    color: "#8B0000",
    description: "The daily journal of the U.S. federal government. Search executive orders, agency rules, proposed regulations, and public notices from all federal agencies. The authoritative source for regulatory actions.",
    url: "https://www.federalregister.gov",
  },
  {
    name: "EPA GHGRP",
    key: "epa_ghgrp",
    color: "#2D6A4F",
    description: "EPA Greenhouse Gas Reporting Program — facility-level greenhouse gas emissions data from large industrial sources. Covers power plants, refineries, chemical plants, and other major emitters across the U.S.",
    url: "https://www.epa.gov/ghgreporting",
  },
  {
    name: "FDIC",
    key: "fdic",
    color: "#004B87",
    description: "Federal Deposit Insurance Corporation bank data. Quarterly financial reports for FDIC-insured institutions including total assets, deposits, net income, capital ratios, and institution directory.",
    url: "https://banks.data.fdic.gov",
  },
];

const LOADING_STEPS = [
  "Downloading dataset...",
  "Loading into analysis engine...",
  "Profiling columns and values...",
  "Running data quality assessment...",
  "Generating preliminary charts...",
];

function useProgressSteps(active: boolean, steps: string[], intervalMs = 2200) {
  const [stepIndex, setStepIndex] = useState(0);
  const timerRef = useRef<ReturnType<typeof setInterval>>(undefined);

  useEffect(() => {
    if (active) {
      setStepIndex(0);
      timerRef.current = setInterval(() => {
        setStepIndex((prev) => (prev < steps.length - 1 ? prev + 1 : prev));
      }, intervalMs);
    } else {
      clearInterval(timerRef.current);
      setStepIndex(0);
    }
    return () => clearInterval(timerRef.current);
  }, [active, steps, intervalMs]);

  return active ? steps[stepIndex] ?? "" : "";
}

export default function SearchPage() {
  const [question, setQuestion] = useState("");
  const [results, setResults] = useState<DatasetResult[]>([]);
  const [searching, setSearching] = useState(false);
  const [starting, setStarting] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [showUpload, setShowUpload] = useState(false);
  const [reloading, setReloading] = useState(false);
  const [error, setError] = useState("");
  const [searchDone, setSearchDone] = useState(false);
  const [selectedSources, setSelectedSources] = useState<Set<string>>(
    () => new Set(SOURCES.map((s) => s.key)),
  );
  const [infoSource, setInfoSource] = useState<typeof SOURCES[number] | null>(null);
  const { logout } = useAuth();
  const navigate = useNavigate();

  const searchStatus = useProgressSteps(searching, SEARCH_STEPS);
  const loadingStatus = useProgressSteps(starting, LOADING_STEPS, 3000);
  const uploadStatus = useProgressSteps(uploading, LOADING_STEPS, 3000);

  const handleSearch = async (e: FormEvent) => {
    e.preventDefault();
    if (!question.trim()) return;
    setSearching(true);
    setError("");
    setResults([]);
    setSearchDone(false);
    try {
      const sourcesArg = selectedSources.size === SOURCES.length
        ? undefined
        : [...selectedSources];
      const res = await datasetApi.search(question.trim(), sourcesArg);
      setResults(res.data);
      setSearchDone(true);
    } catch {
      setError("Search failed. Please try again.");
    } finally {
      setSearching(false);
    }
  };

  const handleSelect = async (dataset: DatasetResult) => {
    setStarting(true);
    setError("");
    try {
      const res = await analysisApi.start({
        source: dataset.source,
        dataset_id: dataset.id,
        question: question.trim(),
        download_url: dataset.download_url,
        dataset_title: dataset.title,
        dataset_description: dataset.ai_description || dataset.description || "",
      });
      navigate(`/analysis/${res.data.session_id}`, {
        state: {
          question: question.trim(),
          startResponse: res.data,
          datasetTitle: dataset.title,
          datasetDescription:
            dataset.ai_description || dataset.description || "",
          datasetSource: dataset.source,
          downloadUrl: dataset.download_url,
        },
      });
    } catch (err: unknown) {
      const detail =
        (err as { response?: { data?: { detail?: string } } })?.response?.data
          ?.detail;
      setError(detail || "Failed to load dataset. Please try another.");
    } finally {
      setStarting(false);
    }
  };

  const handleUpload = async (file: File, uploadQuestion: string) => {
    setUploading(true);
    setError("");
    try {
      const res = await analysisApi.upload(file, uploadQuestion);
      setShowUpload(false);
      navigate(`/analysis/${res.data.session_id}`, {
        state: {
          question: uploadQuestion || "Summarize and visualize this dataset",
          startResponse: res.data,
          datasetTitle: file.name,
          datasetDescription: `Uploaded file: ${file.name}`,
          datasetSource: "upload",
        },
      });
    } catch {
      setError("Failed to process uploaded file. Check the format and try again.");
    } finally {
      setUploading(false);
    }
  };

  const handleSampleSelect = async (url: string, name: string) => {
    setUploading(true);
    setError("");
    try {
      const res = await analysisApi.start({
        source: "upload",
        dataset_id: name,
        question: `Summarize and visualize this dataset: ${name}`,
        download_url: url,
      });
      setShowUpload(false);
      navigate(`/analysis/${res.data.session_id}`, {
        state: {
          question: `Summarize and visualize this dataset: ${name}`,
          startResponse: res.data,
          datasetTitle: name,
          datasetDescription: `Sample dataset: ${name}`,
          datasetSource: "upload",
          downloadUrl: url,
        },
      });
    } catch {
      setError("Failed to load sample dataset. Please try again.");
    } finally {
      setUploading(false);
    }
  };

  const handleReload = async (savedSessionId: string) => {
    setReloading(true);
    setError("");
    try {
      const res = await sessionsApi.reload(savedSessionId);
      const r = res.data;
      navigate(`/analysis/${r.session_id}`, {
        state: {
          question: r.chat_history?.[0]?.content || "",
          startResponse: {
            session_id: r.session_id,
            table_name: r.table_name,
            columns: r.columns,
            row_count: r.row_count,
            data_quality: r.data_quality,
            charts: r.charts,
            chart_code: r.chart_code,
          },
          datasetTitle: r.dataset_title,
          datasetDescription: r.dataset_description,
          datasetSource: r.dataset_source || "",
          downloadUrl: r.download_url || null,
          restoredChatHistory: r.chat_history,
        },
      });
    } catch {
      setError("Failed to reload session. The dataset may no longer be available.");
    } finally {
      setReloading(false);
    }
  };

  return (
    <div style={styles.page}>
      <header style={styles.header}>
        <div style={styles.headerLeft}>
          <h1 style={styles.logo}>Public Data Analysis</h1>
          <button
            onClick={() => setShowUpload(true)}
            style={styles.uploadBtn}
          >
            Upload Data
          </button>
        </div>
        <a
          href="https://docs.google.com/forms/d/e/1FAIpQLSdM6pWM7cQ2dKRpwKABo918d60IYnujGUkgsmd1A5moCBj_gQ/viewform?usp=header"
          target="_blank"
          rel="noopener noreferrer"
          style={styles.feedbackLink}
        >
          Feedback
        </a>
        <button onClick={logout} style={styles.logoutBtn}>Log out</button>
      </header>

      <UploadModal
        open={showUpload}
        onClose={() => setShowUpload(false)}
        onUpload={handleUpload}
        onSampleSelect={handleSampleSelect}
        loading={uploading}
        loadingStatus={uploadStatus}
      />

      {reloading && (
        <div style={styles.loading}>
          <div style={styles.spinner} />
          <span>Reloading session...</span>
        </div>
      )}

      <div style={styles.pageBody}>
        <aside style={styles.sidebar}>
          <SessionHistory onReload={handleReload} loading={reloading} />
        </aside>

      <main style={styles.main}>
        <h2 style={styles.heading}>
          What question do you want to explore with public data?
        </h2>
        <form onSubmit={handleSearch} style={styles.form}>
          <textarea
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            placeholder="e.g. How have global CO2 emissions changed by country over the last 30 years?"
            rows={3}
            style={styles.textarea}
          />
          <button
            type="submit"
            disabled={searching || !question.trim() || selectedSources.size === 0}
            style={styles.searchBtn}
          >
            {searching ? searchStatus : "Search Datasets"}
          </button>
        </form>
        <div style={styles.sourcesPanel}>
          <div style={styles.sourcesPanelHeader}>
            <span style={styles.sourcesLabel}>Data sources</span>
            <button
              type="button"
              style={styles.selectAllBtn}
              onClick={() => {
                if (selectedSources.size === SOURCES.length) {
                  setSelectedSources(new Set());
                } else {
                  setSelectedSources(new Set(SOURCES.map((s) => s.key)));
                }
              }}
            >
              {selectedSources.size === SOURCES.length ? "Deselect all" : "Select all"}
            </button>
          </div>
          <div style={styles.sourcesGrid}>
            {SOURCES.map((s) => (
              <label key={s.key} style={styles.sourceItem}>
                <input
                  type="checkbox"
                  checked={selectedSources.has(s.key)}
                  onChange={() => {
                    setSelectedSources((prev) => {
                      const next = new Set(prev);
                      if (next.has(s.key)) next.delete(s.key);
                      else next.add(s.key);
                      return next;
                    });
                  }}
                  style={styles.sourceCheckbox}
                />
                <span
                  style={{
                    ...styles.sourceChip,
                    background: selectedSources.has(s.key) ? s.color : "#ccc",
                  }}
                >
                  {s.name}
                </span>
                <button
                  type="button"
                  style={styles.infoBtn}
                  onClick={(e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    setInfoSource(s);
                  }}
                  title={`About ${s.name}`}
                >
                  i
                </button>
              </label>
            ))}
          </div>
        </div>

        {infoSource && (
          <div style={styles.modalOverlay} onClick={() => setInfoSource(null)}>
            <div style={styles.modalContent} onClick={(e) => e.stopPropagation()}>
              <div style={styles.modalHeader}>
                <span style={{ ...styles.sourceChip, background: infoSource.color, fontSize: "0.85rem", padding: "3px 10px" }}>
                  {infoSource.name}
                </span>
                <button
                  onClick={() => setInfoSource(null)}
                  style={styles.modalClose}
                >
                  X
                </button>
              </div>
              <p style={styles.modalText}>{infoSource.description}</p>
              <a
                href={infoSource.url}
                target="_blank"
                rel="noopener noreferrer"
                style={styles.modalLink}
              >
                Visit {infoSource.name}
              </a>
            </div>
          </div>
        )}

        {error && <p style={styles.error}>{error}</p>}

        {starting && (
          <div style={styles.loading}>
            <div style={styles.spinner} />
            <span>{loadingStatus}</span>
          </div>
        )}

        {searchDone && results.length === 0 && !searching && (
          <div style={styles.noResults}>
            <p style={styles.noResultsText}>
              No downloadable datasets found for your query. Try rephrasing your question or using different keywords.
            </p>
          </div>
        )}

        {results.length > 0 && (
          <div style={styles.results}>
            <h3 style={styles.resultsHeading}>
              Found {results.length} relevant datasets
            </h3>
            <div style={styles.grid}>
              {results.map((d) => (
                <DatasetCard
                  key={`${d.source}-${d.id}`}
                  dataset={d}
                  onSelect={handleSelect}
                  disabled={starting}
                />
              ))}
            </div>
          </div>
        )}
      </main>
      </div>
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  page: { minHeight: "100vh", background: "#f0f2f5", display: "flex", flexDirection: "column" },
  pageBody: { flex: 1, display: "flex" },
  sidebar: {
    width: 240,
    flexShrink: 0,
    background: "#fff",
    borderRight: "1px solid #e5e7eb",
    overflowY: "auto",
  },
  header: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    padding: "1rem 2rem",
    background: "#fff",
    borderBottom: "1px solid #e5e7eb",
  },
  headerLeft: { display: "flex", alignItems: "center", gap: "1rem" },
  logo: { fontSize: "1.1rem", fontWeight: 700 },
  uploadBtn: {
    background: "#f0f2f5",
    border: "1px solid #d1d5db",
    borderRadius: "6px",
    padding: "0.35rem 0.75rem",
    cursor: "pointer",
    fontSize: "0.82rem",
    fontWeight: 600,
    color: "#374151",
  },
  feedbackLink: {
    color: "#6b7280",
    fontSize: "0.82rem",
    textDecoration: "none",
  },
  logoutBtn: {
    background: "none",
    border: "1px solid #ddd",
    borderRadius: "6px",
    padding: "0.4rem 0.8rem",
    cursor: "pointer",
    fontSize: "0.85rem",
  },
  main: { flex: 1, maxWidth: 900, margin: "0 auto", padding: "2rem 1rem" },
  heading: { fontSize: "1.4rem", fontWeight: 600, marginBottom: "1rem" },
  form: { display: "flex", flexDirection: "column", gap: "0.75rem" },
  textarea: {
    padding: "0.8rem",
    border: "1px solid #ddd",
    borderRadius: "10px",
    fontSize: "1rem",
    resize: "vertical",
    fontFamily: "inherit",
  },
  searchBtn: {
    padding: "0.7rem",
    background: "#2563eb",
    color: "#fff",
    border: "none",
    borderRadius: "8px",
    fontSize: "1rem",
    fontWeight: 600,
    cursor: "pointer",
    alignSelf: "flex-start",
  },
  sourcesPanel: {
    marginTop: "0.75rem",
    padding: "0.6rem 0.75rem",
    background: "#fff",
    borderRadius: "8px",
    border: "1px solid #e5e7eb",
  },
  sourcesPanelHeader: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    marginBottom: "0.5rem",
  },
  sourcesLabel: {
    fontSize: "0.8rem",
    color: "#666",
    fontWeight: 600,
  },
  selectAllBtn: {
    background: "none",
    border: "none",
    color: "#2563eb",
    fontSize: "0.75rem",
    cursor: "pointer",
    fontWeight: 500,
    padding: 0,
  },
  sourcesGrid: {
    display: "flex",
    flexWrap: "wrap" as const,
    gap: "0.4rem",
  },
  sourceItem: {
    display: "flex",
    alignItems: "center",
    gap: "0.25rem",
    cursor: "pointer",
    userSelect: "none" as const,
  },
  sourceCheckbox: {
    margin: 0,
    cursor: "pointer",
    accentColor: "#2563eb",
  },
  sourceChip: {
    color: "#fff",
    padding: "1px 7px",
    borderRadius: "4px",
    fontSize: "0.7rem",
    fontWeight: 600,
    transition: "background 0.15s",
  },
  infoBtn: {
    background: "none",
    border: "1px solid #d1d5db",
    borderRadius: "50%",
    width: 16,
    height: 16,
    fontSize: "0.6rem",
    fontWeight: 700,
    color: "#888",
    cursor: "pointer",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    padding: 0,
    lineHeight: 1,
    flexShrink: 0,
  },
  modalOverlay: {
    position: "fixed" as const,
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
    background: "rgba(0,0,0,0.4)",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    zIndex: 1000,
  },
  modalContent: {
    background: "#fff",
    borderRadius: "12px",
    padding: "1.5rem",
    maxWidth: 420,
    width: "90%",
    boxShadow: "0 8px 30px rgba(0,0,0,0.2)",
  },
  modalHeader: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    marginBottom: "1rem",
  },
  modalClose: {
    background: "none",
    border: "none",
    fontSize: "1rem",
    cursor: "pointer",
    color: "#666",
    fontWeight: 700,
  },
  modalText: {
    fontSize: "0.9rem",
    lineHeight: 1.5,
    color: "#374151",
    margin: "0 0 1rem 0",
  },
  modalLink: {
    fontSize: "0.85rem",
    color: "#2563eb",
    textDecoration: "none",
    fontWeight: 500,
  },
  error: { color: "#dc2626", marginTop: "0.5rem" },
  loading: {
    marginTop: "2rem",
    padding: "1.2rem",
    background: "#fff",
    borderRadius: "10px",
    textAlign: "center",
    color: "#444",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    gap: "0.75rem",
    fontSize: "0.95rem",
  },
  spinner: {
    width: 20,
    height: 20,
    border: "3px solid #e5e7eb",
    borderTop: "3px solid #2563eb",
    borderRadius: "50%",
    animation: "spin 0.8s linear infinite",
    flexShrink: 0,
  },
  noResults: {
    marginTop: "2rem",
    padding: "1.5rem",
    background: "#fff",
    borderRadius: "10px",
    textAlign: "center",
  },
  noResultsText: {
    color: "#6b7280",
    fontSize: "0.95rem",
    margin: 0,
  },
  results: { marginTop: "2rem" },
  resultsHeading: {
    fontSize: "1.1rem",
    fontWeight: 600,
    marginBottom: "1rem",
  },
  grid: {
    display: "grid",
    gridTemplateColumns: "repeat(auto-fill, minmax(300px, 1fr))",
    gap: "1rem",
  },
};
