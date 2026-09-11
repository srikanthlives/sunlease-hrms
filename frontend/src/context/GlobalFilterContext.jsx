import { createContext, useContext, useEffect, useState } from "react";

const STORAGE_KEY = "hrms_global_filter";

function loadInitial() {
  const now = new Date();
  const defaults = { year: now.getFullYear(), month: now.getMonth() + 1, costCenterId: null };
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) return { ...defaults, ...JSON.parse(raw) };
  } catch {
    // fall through to defaults
  }
  return defaults;
}

const GlobalFilterContext = createContext(null);

export function GlobalFilterProvider({ children }) {
  const [state, setState] = useState(loadInitial);

  useEffect(() => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  }, [state]);

  function setYear(year) {
    setState((s) => ({ ...s, year }));
  }

  function setMonth(month) {
    setState((s) => ({ ...s, month }));
  }

  function setCostCenterId(costCenterId) {
    setState((s) => ({ ...s, costCenterId }));
  }

  return (
    <GlobalFilterContext.Provider value={{ ...state, setYear, setMonth, setCostCenterId }}>
      {children}
    </GlobalFilterContext.Provider>
  );
}

export function useGlobalFilter() {
  return useContext(GlobalFilterContext);
}
