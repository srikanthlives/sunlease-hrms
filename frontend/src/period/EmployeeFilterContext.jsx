import { createContext, useContext, useState, useCallback } from 'react'

const EmployeeFilterContext = createContext(null)
const STORAGE_KEY = 'sunlease_employee_filters'

const DEFAULTS = { sortBy: 'default', deptFilter: '', locFilter: '' }

function loadStored() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (raw) {
      const parsed = JSON.parse(raw)
      return { ...DEFAULTS, ...parsed }
    }
  } catch {
    // ignore malformed storage
  }
  return DEFAULTS
}

export function EmployeeFilterProvider({ children }) {
  const [filters, setFilters] = useState(loadStored)

  const persist = useCallback((next) => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(next))
    setFilters(next)
  }, [])

  const setSortBy = useCallback((sortBy) => {
    setFilters((prev) => {
      const next = { ...prev, sortBy }
      localStorage.setItem(STORAGE_KEY, JSON.stringify(next))
      return next
    })
  }, [])

  const setDeptFilter = useCallback((deptFilter) => {
    setFilters((prev) => {
      const next = { ...prev, deptFilter }
      localStorage.setItem(STORAGE_KEY, JSON.stringify(next))
      return next
    })
  }, [])

  const setLocFilter = useCallback((locFilter) => {
    setFilters((prev) => {
      const next = { ...prev, locFilter }
      localStorage.setItem(STORAGE_KEY, JSON.stringify(next))
      return next
    })
  }, [])

  const resetFilters = useCallback(() => persist(DEFAULTS), [persist])

  return (
    <EmployeeFilterContext.Provider
      value={{
        sortBy: filters.sortBy, deptFilter: filters.deptFilter, locFilter: filters.locFilter,
        setSortBy, setDeptFilter, setLocFilter, resetFilters,
      }}
    >
      {children}
    </EmployeeFilterContext.Provider>
  )
}

export function useEmployeeFilters() {
  return useContext(EmployeeFilterContext)
}

/**
 * Shared filter+sort logic so every page applies the app-level department/location/sort
 * selection identically. `getEmployee(item)` maps a list item (payslip, payment, grid row,
 * employee record itself, etc.) to its associated employee object (or the employee object
 * itself, if the list already IS a list of employees).
 */
export function applyEmployeeFilters(items, filters, getEmployee) {
  const { deptFilter, locFilter, sortBy } = filters
  let result = items.filter((item) => {
    const emp = getEmployee(item)
    if (deptFilter && emp?.department !== deptFilter) return false
    if (locFilter && emp?.location !== locFilter) return false
    return true
  })

  if (sortBy && sortBy !== 'default') {
    result = [...result].sort((a, b) => {
      const ea = getEmployee(a)
      const eb = getEmployee(b)
      if (sortBy === 'code_asc' || sortBy === 'code_desc') {
        const ca = ea?.employee_code || ''
        const cb = eb?.employee_code || ''
        return sortBy === 'code_asc' ? ca.localeCompare(cb) : cb.localeCompare(ca)
      }
      const na = ea ? `${ea.first_name} ${ea.last_name}` : ''
      const nb = eb ? `${eb.first_name} ${eb.last_name}` : ''
      return sortBy === 'name_asc' ? na.localeCompare(nb) : nb.localeCompare(na)
    })
  }

  return result
}

export function distinctDepartmentsAndLocations(employees) {
  return {
    departments: [...new Set(employees.map((e) => e.department).filter(Boolean))].sort(),
    locations: [...new Set(employees.map((e) => e.location).filter(Boolean))].sort(),
  }
}
