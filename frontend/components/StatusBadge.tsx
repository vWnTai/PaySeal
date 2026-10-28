import { paymentStatuses } from "@/lib/payment";

export function StatusBadge({ status }: { status: string }) {
  const state = paymentStatuses.find((item) => item.value === status) ?? {
    label: status.replaceAll("_", " "),
    classes: "border-slate-200 bg-slate-100 text-slate-700",
  };
  return (
    <span className={"badge " + state.classes}>
      <span className="h-1.5 w-1.5 rounded-full bg-current" aria-hidden="true" />
      {state.label}
    </span>
  );
}
