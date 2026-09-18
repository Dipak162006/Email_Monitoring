import React, { useState, type KeyboardEvent } from "react";
import { X } from "lucide-react";

interface RecipientInputProps {
  label: string;
  recipients: string[];
  onChange: (recipients: string[]) => void;
  placeholder?: string;
  autoFocus?: boolean;
  rightAction?: React.ReactNode;
}

const EMAIL_REGEX = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export const RecipientInput: React.FC<RecipientInputProps> = ({
  label,
  recipients,
  onChange,
  placeholder = "Add recipients...",
  autoFocus = false,
  rightAction,
}) => {
  const [inputValue, setInputValue] = useState("");
  const [error, setError] = useState<string | null>(null);

  const addRecipient = (raw: string) => {
    const trimmed = raw.trim().replace(/[,;]+$/, "").trim();
    if (!trimmed) return;

    if (!EMAIL_REGEX.test(trimmed)) {
      setError(`"${trimmed}" is not a valid email`);
      return;
    }

    if (recipients.includes(trimmed)) {
      setInputValue("");
      setError(null);
      return;
    }

    onChange([...recipients, trimmed]);
    setInputValue("");
    setError(null);
  };

  const removeRecipient = (index: number) => {
    onChange(recipients.filter((_, i) => i !== index));
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter" || e.key === "," || e.key === ";") {
      e.preventDefault();
      addRecipient(inputValue);
    } else if (e.key === "Backspace" && !inputValue && recipients.length > 0) {
      e.preventDefault();
      removeRecipient(recipients.length - 1);
    } else if (error) {
      setError(null);
    }
  };

  const handleBlur = () => {
    if (inputValue) {
      addRecipient(inputValue);
    }
  };

  return (
    <div className="py-2.5 flex items-start text-sm border-b border-slate-100 last:border-b-0">
      <span className="w-16 pt-1 text-slate-500 font-medium select-none text-xs sm:text-sm">
        {label}
      </span>

      <div className="flex-1 flex flex-col min-w-0">
        <div className="flex flex-wrap items-center gap-1.5 min-h-[32px]">
          {recipients.map((email, idx) => (
            <div
              key={idx}
              className="bg-slate-100 hover:bg-slate-200/80 text-slate-800 border border-slate-200/80 rounded-lg px-2.5 py-1 flex items-center gap-1.5 text-xs font-medium transition-colors"
            >
              <span className="truncate max-w-[220px]">{email}</span>
              <button
                type="button"
                onClick={() => removeRecipient(idx)}
                className="text-slate-400 hover:text-slate-700 p-0.5 rounded transition-colors"
                title={`Remove ${email}`}
                aria-label={`Remove ${email}`}
              >
                <X className="h-3 w-3" />
              </button>
            </div>
          ))}

          <input
            type="email"
            value={inputValue}
            autoFocus={autoFocus}
            onChange={(e) => {
              setInputValue(e.target.value);
              if (error) setError(null);
            }}
            onKeyDown={handleKeyDown}
            onBlur={handleBlur}
            placeholder={recipients.length === 0 ? placeholder : ""}
            className="flex-1 min-w-[140px] bg-transparent outline-none text-xs sm:text-sm text-slate-900 placeholder-slate-400 py-1"
          />
        </div>

        {error && <span className="text-[11px] text-rose-600 mt-1">{error}</span>}
      </div>

      {rightAction && <div className="ml-2 shrink-0 pt-0.5">{rightAction}</div>}
    </div>
  );
};
