// DESIGN.md §6.3 双层雷达呼吸状态灯：外环 animate-ping + 内芯光点。
// 必须伴随文字标签使用，不得仅以颜色传达状态；prefers-reduced-motion 下停用呼吸动效。
const TONES = {
  emerald: {
    ring: "bg-emerald-400/75 dark:bg-emerald-400/80",
    core: "bg-emerald-500 dark:bg-emerald-400",
  },
  amber: {
    ring: "bg-amber-400/75 dark:bg-amber-400/80",
    core: "bg-amber-500 dark:bg-amber-400",
  },
  red: {
    ring: "bg-red-400/75 dark:bg-red-400/80",
    core: "bg-red-500 dark:bg-red-400",
  },
  neutral: {
    ring: "bg-slate-400/60 dark:bg-zinc-500/60",
    core: "bg-slate-500 dark:bg-zinc-400",
  },
} as const;

export type TechPulseDotTone = keyof typeof TONES;

export function TechPulseDot({
  tone,
  label,
}: {
  tone: TechPulseDotTone;
  label: string;
}) {
  const palette = TONES[tone];
  return (
    <span
      className="relative inline-flex h-2.5 w-2.5 shrink-0"
      role="status"
      aria-label={label}
    >
      <span
        className={`absolute inline-flex h-full w-full animate-ping rounded-full motion-reduce:animate-none ${palette.ring}`}
      />
      <span className={`relative inline-flex h-2.5 w-2.5 rounded-full ${palette.core}`} />
    </span>
  );
}
