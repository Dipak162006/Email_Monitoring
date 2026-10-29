import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { SendingWindowCard } from "../SendingWindowCard";
import type { SendingWindowConfig } from "../../../types/campaign";

describe("SendingWindowCard Component (M6 UI Verification)", () => {
  it("renders disabled state by default with 24/7 notice", () => {
    const handleChange = vi.fn();
    render(<SendingWindowCard value={null} onChange={handleChange} />);

    expect(screen.getByText(/Sending Window & Timezone Governance/i)).toBeDefined();
    expect(screen.getByText(/Window is disabled/i)).toBeDefined();
    expect(screen.getByText(/24\/7/i)).toBeDefined();

    const checkbox = screen.getByRole("checkbox", { name: /enable sending window/i }) as HTMLInputElement;
    expect(checkbox.checked).toBe(false);
  });

  it("toggles enabled state and initializes with default business window", () => {
    const handleChange = vi.fn();
    render(<SendingWindowCard value={null} onChange={handleChange} />);

    const checkbox = screen.getByRole("checkbox", { name: /enable sending window/i });
    fireEvent.click(checkbox);

    expect(handleChange).toHaveBeenCalledWith(
      expect.objectContaining({
        enabled: true,
        start_time: "09:00",
        end_time: "17:00",
        days: [1, 2, 3, 4, 5],
      })
    );
  });

  it("renders full controls when enabled and updates timezone and times", () => {
    const handleChange = vi.fn();
    const config: SendingWindowConfig = {
      enabled: true,
      timezone: "America/New_York",
      days: [1, 2, 3, 4, 5],
      start_time: "09:00",
      end_time: "17:00",
    };

    render(<SendingWindowCard value={config} onChange={handleChange} />);

    // Timezone select
    const tzSelect = screen.getByLabelText(/Target Timezone/i) as HTMLSelectElement;
    expect(tzSelect.value).toBe("America/New_York");

    fireEvent.change(tzSelect, { target: { value: "Europe/London" } });
    expect(handleChange).toHaveBeenCalledWith(
      expect.objectContaining({
        timezone: "Europe/London",
      })
    );

    // Opening and closing time inputs
    const startInput = screen.getByLabelText(/Opening Time/i) as HTMLInputElement;
    const endInput = screen.getByLabelText(/Closing Time/i) as HTMLInputElement;
    expect(startInput.value).toBe("09:00");
    expect(endInput.value).toBe("17:00");

    fireEvent.change(startInput, { target: { value: "08:30" } });
    expect(handleChange).toHaveBeenCalledWith(
      expect.objectContaining({
        start_time: "08:30",
      })
    );
  });

  it("displays validation warning if opening time is later than closing time", () => {
    const handleChange = vi.fn();
    const invalidConfig: SendingWindowConfig = {
      enabled: true,
      timezone: "UTC",
      days: [1, 2, 3, 4, 5],
      start_time: "18:00",
      end_time: "09:00",
    };

    render(<SendingWindowCard value={invalidConfig} onChange={handleChange} />);
    expect(
      screen.getByText(/Opening time must be strictly earlier than closing time/i)
    ).toBeDefined();
  });

  it("toggles weekdays accurately", () => {
    const handleChange = vi.fn();
    const config: SendingWindowConfig = {
      enabled: true,
      timezone: "UTC",
      days: [1, 2, 3, 4, 5],
      start_time: "09:00",
      end_time: "17:00",
    };

    render(<SendingWindowCard value={config} onChange={handleChange} />);

    // Click Mon to toggle it off
    const monBtn = screen.getByRole("button", { name: "Mon" });
    fireEvent.click(monBtn);

    expect(handleChange).toHaveBeenCalledWith(
      expect.objectContaining({
        days: [2, 3, 4, 5],
      })
    );
  });
});
