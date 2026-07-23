import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import App from './App.jsx'
import { AuthProvider } from './auth/AuthContext.jsx'
import { PeriodProvider } from './period/PeriodContext.jsx'
import { EmployeeFilterProvider } from './period/EmployeeFilterContext.jsx'
import './index.css'

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <BrowserRouter>
      <AuthProvider>
        <PeriodProvider>
          <EmployeeFilterProvider>
            <App />
          </EmployeeFilterProvider>
        </PeriodProvider>
      </AuthProvider>
    </BrowserRouter>
  </React.StrictMode>,
)
