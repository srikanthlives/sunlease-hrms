import MasterPage from "../components/MasterPage";

export default function Shifts() {
  return (
    <MasterPage
      title="Shifts"
      description="Shift master — start/end time, grace period, and day-length definitions used by Roster and Attendance."
      resource="/attendance/shifts"
      allowDeactivate={false}
      fields={[
        { name: "code", label: "Code", type: "text", required: true },
        { name: "name", label: "Name", type: "text", required: true },
        { name: "start_time", label: "Start Time", type: "time", required: true },
        { name: "end_time", label: "End Time", type: "time", required: true },
        { name: "break_minutes", label: "Break (min)", type: "number", default: 0 },
        { name: "grace_minutes", label: "Grace (min)", type: "number", default: 0 },
        { name: "half_day_hours", label: "Half-Day Hrs", type: "number" },
        { name: "full_day_hours", label: "Full-Day Hrs", type: "number" },
        { name: "is_night_shift", label: "Night Shift", type: "checkbox" },
      ]}
    />
  );
}
