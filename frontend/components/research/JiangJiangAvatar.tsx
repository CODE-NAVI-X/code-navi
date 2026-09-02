"use client";

import { User } from "lucide-react";

interface JiangJiangAvatarProps {
  size?: "sm" | "md" | "lg";
  isThinking?: boolean;
}

export function JiangJiangAvatar({
  size = "md",
  isThinking = false,
}: JiangJiangAvatarProps) {
  const sizeClass = {
    sm: "h-7 w-7",
    md: "h-9 w-9",
    lg: "h-11 w-11",
  }[size];

  return (
    <div
      className={`relative ${sizeClass} shrink-0 rounded-2xl p-0.5 shadow-sm transition-transform duration-300 ${
        isThinking ? "scale-105 animate-pulse" : "hover:scale-105"
      }`}
      style={{
        background:
          "linear-gradient(135deg, #6366f1 0%, #a855f7 50%, #ec4899 100%)",
      }}
    >
      <div className="flex h-full w-full items-center justify-center rounded-[14px] bg-slate-900 text-white overflow-hidden">
        {/* Cartoon Stylized Jiang Jiang SVG */}
        <svg
          viewBox="0 0 48 48"
          fill="none"
          xmlns="http://www.w3.org/2000/svg"
          className="h-full w-full"
          aria-hidden="true"
        >
          {/* Background Aura */}
          <circle cx="24" cy="24" r="24" fill="#1e1b4b" />
          
          {/* Hair back */}
          <path
            d="M12 26C12 15 17 8 24 8C31 8 36 15 36 26C36 34 33 38 31 40C27 40 21 40 17 40C15 38 12 34 12 26Z"
            fill="#312e81"
          />

          {/* Cute Cap / Beret */}
          <path
            d="M14 15C14 11 18 8 24 8C30 8 34 11 34 15C34 18 30 19 24 19C18 19 14 18 14 15Z"
            fill="#4f46e5"
          />
          <circle cx="24" cy="7" r="2" fill="#fbbf24" />

          {/* Face */}
          <circle cx="24" cy="24" r="11" fill="#fde68a" />

          {/* Cute Hair Bangs */}
          <path
            d="M15 20C17 22 20 22 22 20C24 22 27 22 29 20C31 22 33 21 34 19C33 16 29 14 24 14C19 14 15 16 14 19C14 19.5 14.5 20 15 20Z"
            fill="#3730a3"
          />

          {/* Cheerful Eyes / Glasses */}
          {/* Glasses Frame */}
          <rect
            x="16.5"
            y="21"
            width="6"
            height="5"
            rx="2"
            stroke="#1e1b4b"
            strokeWidth="1.5"
            fill="#ffffff"
            fillOpacity="0.4"
          />
          <rect
            x="25.5"
            y="21"
            width="6"
            height="5"
            rx="2"
            stroke="#1e1b4b"
            strokeWidth="1.5"
            fill="#ffffff"
            fillOpacity="0.4"
          />
          <line
            x1="22.5"
            y1="23.5"
            x2="25.5"
            y2="23.5"
            stroke="#1e1b4b"
            strokeWidth="1.5"
          />

          {/* Pupils */}
          <circle cx="19.5" cy="23.5" r="1.2" fill="#1e1b4b" />
          <circle cx="28.5" cy="23.5" r="1.2" fill="#1e1b4b" />
          <circle cx="19" cy="23" r="0.4" fill="#ffffff" />
          <circle cx="28" cy="23" r="0.4" fill="#ffffff" />

          {/* Blush */}
          <ellipse cx="16" cy="27" rx="1.5" ry="0.8" fill="#f43f5e" opacity="0.6" />
          <ellipse cx="32" cy="27" rx="1.5" ry="0.8" fill="#f43f5e" opacity="0.6" />

          {/* Cute Smile */}
          <path
            d="M22 28C22.5 29.5 25.5 29.5 26 28"
            stroke="#881337"
            strokeWidth="1.2"
            strokeLinecap="round"
          />

          {/* Collar / Ribbon */}
          <path
            d="M20 35L24 38L28 35L24 33Z"
            fill="#ec4899"
          />
        </svg>
      </div>
    </div>
  );
}

export function UserAvatar({ size = "md" }: { size?: "sm" | "md" | "lg" }) {
  const sizeClass = {
    sm: "h-7 w-7",
    md: "h-9 w-9",
    lg: "h-11 w-11",
  }[size];

  return (
    <div
      className={`${sizeClass} shrink-0 rounded-2xl border border-slate-200 dark:border-zinc-700 bg-gradient-to-b from-slate-100 to-slate-200 dark:from-zinc-800 dark:to-zinc-900 flex items-center justify-center text-slate-600 dark:text-zinc-300 shadow-sm`}
    >
      <User className="h-4 w-4" />
    </div>
  );
}
