import axios from "axios";

// In dev (`npm run dev`), frontend and backend run on different ports
// (5173 vs 8010), so default to the backend's own origin. In a built
// production bundle, frontend and backend are served same-origin (FastAPI
// mounts the built frontend directly), so default to a relative "" instead
// of hardcoding localhost.
export const BASE_URL = import.meta.env.VITE_API_URL || (import.meta.env.DEV ? "http://localhost:8010" : "");

const client = axios.create({ baseURL: `${BASE_URL}/api/v1` });

client.interceptors.request.use((config) => {
  const token = localStorage.getItem("hrms_token");
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

client.interceptors.response.use(
  (res) => res,
  (err) => {
    if (err.response?.status === 401) {
      localStorage.removeItem("hrms_token");
      localStorage.removeItem("hrms_user");
      window.location.href = "/login";
    }
    return Promise.reject(err);
  }
);

export default client;

export function apiErrorMessage(err) {
  const detail = err?.response?.data?.detail;
  // FastAPI 422 validation errors come back as a list of {loc, msg, ...}
  // objects rather than a plain string - flatten those into one readable line.
  if (Array.isArray(detail)) {
    return detail
      .map((d) => {
        const field = Array.isArray(d.loc) ? d.loc[d.loc.length - 1] : null;
        const msg = (d.msg || "").replace(/^Value error,\s*/, "");
        return field ? `${field}: ${msg}` : msg;
      })
      .join("; ");
  }
  return detail || err?.message || "Something went wrong";
}
