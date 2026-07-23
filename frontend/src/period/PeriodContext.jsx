import { createContext, useContext, useState, useCallback } from 'react'

const PeriodContext = createContext(null)
const STORAGE_KEY = 'sunlease_period'

function loadStored() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (raw) {
      const parsed = JSON.parse(raw)
      if (parsed?.month && parsed?.year) return parsed
    }
  } catch {
    // ignore malformed storage
  }
  const now = new Date()
  return { month: now.getMonth() + 1, year: now.getFullYear() }
}

export function PeriodProvider({ children }) {
  const [period, setPeriod] = useState(loadStored)

  const setMonth = useCallback((month) => {
    setPeriod((prev) => {
      const next = { ...prev, month: Number(month) }
      localStorage.setItem(STORAGE_KEY, JSON.stringify(next))
      return next
    })
  }, [])

  const setYear = useCallback((year) => {
    setPeriod((prev) => {
      const next = { ...prev, year: Number(year) }
      localStorage.setItem(STORAGE_KEY, JSON.stringify(next))
      return next
    })
  }, [])

  return (
    <PeriodContext.Provider value={{ month: period.month, year: period.year, setMonth, setYear }}>
      {children}
    </PeriodContext.Provider>
  )
}

export function usePeriod() {
  return useContext(PeriodContext)
}
