import { Icon } from "@/components/Icon";

const steps = [
  { status: "DRAFT", label: "Bản nháp" },
  { status: "PENDING_APPROVAL", label: "Phê duyệt" },
  { status: "APPROVED", label: "Sẵn sàng ký" },
  { status: "SIGNED", label: "Đã phát hành" },
];

export function PaymentProgress({ status }: { status: string }) {
  const current = steps.findIndex((step) => step.status === status);
  if (current < 0) return null;
  return (
    <ol aria-label="Tiến trình yêu cầu" className="card mb-5 grid grid-cols-4 !px-3 !py-5 sm:!px-6">
      {steps.map((step, index) => (
        <li
          key={step.status}
          aria-current={index === current ? "step" : undefined}
          className="relative text-center"
        >
          {index > 0 && (
            <span
              aria-hidden="true"
              className={
                "absolute right-1/2 top-4 h-0.5 w-full " +
                (index <= current ? "bg-teal-300" : "bg-slate-100")
              }
            />
          )}
          <span
            className={
              "relative mx-auto grid h-8 w-8 place-items-center rounded-full text-xs font-bold " +
              (index < current
                ? "bg-teal-600 text-white"
                : index === current
                  ? "bg-teal-50 text-teal-800 ring-2 ring-teal-500 ring-offset-2"
                  : "bg-slate-100 text-slate-400")
            }
          >
            {index < current ? <Icon name="check" size={16} /> : index + 1}
          </span>
          <span
            className={
              "relative mt-3 block px-1 text-[11px] font-semibold sm:text-xs " +
              (index <= current ? "text-teal-800" : "text-slate-400")
            }
          >
            {step.label}
          </span>
        </li>
      ))}
    </ol>
  );
}
