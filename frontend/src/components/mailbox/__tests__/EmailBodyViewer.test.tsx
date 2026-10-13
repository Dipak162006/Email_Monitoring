import { describe, it, expect } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { EmailBodyViewer } from "../EmailBodyViewer";

describe("EmailBodyViewer - Industry Standard Implementation", () => {
  const sampleHtml = `
    <div>
      <h1>Dear Customer</h1>
      <p>Here is your promotional email offer.</p>
    </div>
  `;
  const sampleText = "Dear Customer\n\nHere is your promotional email offer.";

  it("renders sandboxed iframe with scrolling='no' to prevent inner scrollbars", () => {
    render(<EmailBodyViewer html={sampleHtml} text={sampleText} />);

    const iframe = screen.getByTitle("Email Message Body");
    expect(iframe).toBeTruthy();
    expect(iframe.getAttribute("scrolling")).toBe("no");
    expect(iframe.getAttribute("sandbox")).toBe(
      "allow-popups allow-popups-to-escape-sandbox allow-same-origin"
    );
  });

  it("injects overflow-y: hidden and height resets in iframe srcDoc to prevent vertical scrollbars and locked height", () => {
    render(<EmailBodyViewer html={sampleHtml} text={sampleText} />);

    const iframe = screen.getByTitle("Email Message Body") as HTMLIFrameElement;
    const srcDoc = iframe.getAttribute("srcdoc") || "";

    expect(srcDoc.includes("overflow-y: hidden !important;")).toBe(true);
    expect(srcDoc.includes("height: auto !important;")).toBe(true);
    expect(srcDoc.includes("min-height: 0 !important;")).toBe(true);
    expect(srcDoc.includes("::-webkit-scrollbar")).toBe(true);
    expect(srcDoc.includes("Dear Customer")).toBe(true);
  });

  it("renders a skeleton loading state with pulse animation while initial layout is resolving", () => {
    const { container } = render(<EmailBodyViewer html={sampleHtml} text={sampleText} />);

    const pulseSkeleton = container.querySelector(".animate-pulse");
    expect(pulseSkeleton).toBeTruthy();
  });

  it("allows switching between Formatted HTML and Plain Text views", () => {
    render(<EmailBodyViewer html={sampleHtml} text={sampleText} />);

    // Initially in Formatted view
    expect(screen.getByTitle("Email Message Body")).toBeTruthy();

    // Click Plain Text button
    const plainTextBtn = screen.getByRole("button", { name: /plain text/i });
    fireEvent.click(plainTextBtn);

    // Formatted iframe is removed, text is visible
    expect(screen.queryByTitle("Email Message Body")).toBeNull();
    expect(screen.getByText(/Here is your promotional email offer/i)).toBeTruthy();

    // Click Formatted button
    const formattedBtn = screen.getByRole("button", { name: /formatted/i });
    fireEvent.click(formattedBtn);

    expect(screen.getByTitle("Email Message Body")).toBeTruthy();
  });

  it("preserves email head style tags and media queries so responsive desktop/mobile alternate images are not duplicated", () => {
    const responsiveEmailHtml = `
      <!doctype html>
      <html>
      <head>
        <style type="text/css">
          @media only screen and (min-width: 720px) {
            .desktop-hide { display: none !important; }
          }
          @media only screen and (max-width: 719px) {
            .m-hide { display: none !important; }
          }
        </style>
      </head>
      <body>
        <img src="https://example.com/mobile-banner.png" class="desktop-hide" alt="Mobile Banner">
        <img src="https://example.com/desktop-banner.png" class="m-hide" alt="Desktop Banner">
      </body>
      </html>
    `;

    render(<EmailBodyViewer html={responsiveEmailHtml} />);

    const iframe = screen.getByTitle("Email Message Body") as HTMLIFrameElement;
    const srcDoc = iframe.getAttribute("srcdoc") || "";

    // Verify original style rules and media queries are preserved inside srcDoc
    expect(srcDoc.includes(".desktop-hide { display: none !important; }")).toBe(true);
    expect(srcDoc.includes(".m-hide { display: none !important; }")).toBe(true);
    expect(srcDoc.includes("@media only screen and (min-width: 720px)")).toBe(true);
    expect(srcDoc.includes("@media only screen and (max-width: 719px)")).toBe(true);
  });

  it("renders formatted plain text directly when only text content is provided", () => {
    render(<EmailBodyViewer text={sampleText} />);

    expect(screen.queryByTitle("Email Message Body")).toBeNull();
    expect(screen.getByText(/Here is your promotional email offer/i)).toBeTruthy();
  });
});
