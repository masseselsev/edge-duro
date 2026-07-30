import React from 'react';
import { Info } from 'lucide-react';

interface FieldLabelProps {
  children: React.ReactNode;
  hint?: string;
  /** Extra non-color utilities, e.g. spacing ("pt-2"). Appended, never conflicts. */
  className?: string;
  /** Overrides the default text-zinc-400. Kept separate from className so a
   *  caller-supplied color class can't lose a Tailwind specificity tie against
   *  the built-in one (utility order in the compiled stylesheet decides ties,
   *  not the order classes appear in the attribute). */
  colorClassName?: string;
}

// Uppercase field label with an optional (i) hover hint explaining exact
// input format (newline vs comma separated, what the value affects at build
// time, etc). Uses the native title attribute rather than a custom tooltip
// so it stays correct inside modals with backdrop-blur / z-index stacking
// without extra positioning logic.
export default function FieldLabel({ children, hint, className, colorClassName }: FieldLabelProps) {
  return (
    <label
      className={`flex items-center gap-1.5 text-xs font-bold uppercase tracking-wider ${
        colorClassName || 'text-zinc-400'
      } ${className || ''}`}
    >
      {children}
      {hint && (
        <span
          title={hint}
          className="inline-flex items-center justify-center w-3.5 h-3.5 rounded-full border border-zinc-700 text-zinc-500 hover:text-zinc-300 hover:border-zinc-500 cursor-help normal-case font-normal tracking-normal shrink-0"
        >
          <Info className="w-2.5 h-2.5" />
        </span>
      )}
    </label>
  );
}
