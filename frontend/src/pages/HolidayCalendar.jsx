import MasterPage from "../components/MasterPage";

export default function HolidayCalendar() {
  return (
    <MasterPage
      title="Holiday Calendar"
      description="Holidays block Leave Applications on that date. Leave Cost Center blank for a global (all Cost Centers) holiday."
      resource="/leave/holiday-calendar"
      allowDeactivate={false}
      allowEdit={false}
      fields={[
        { name: "name", label: "Name", type: "text", required: true },
        { name: "date", label: "Date", type: "date", required: true },
        { name: "cost_center_id", label: "Cost Center (blank = global)", type: "select", optionsResource: "/cost-centers", optionLabel: "name" },
        { name: "is_optional", label: "Optional", type: "checkbox" },
      ]}
    />
  );
}
